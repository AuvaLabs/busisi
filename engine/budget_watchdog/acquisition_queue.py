"""Durable, bounded lifecycle acquisition queue."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from engine.budget_watchdog.acquisition_universe import AcquisitionUniverseSnapshot
from engine.budget_watchdog.contract_evidence import STAGES, ContractEvidenceCatalog

SHA256 = re.compile(r"[0-9a-f]{64}")
HTTP_ERROR_MINIMUM = 400
HTTP_ERROR_MAXIMUM = 599
RESULT_STATUSES = frozenset(
    {"verified_archived", "retry", "blocked", "not_located", "quarantined"}
)
READY_QUERY = (
    "SELECT task_id, contract_id, stage, status, attempts, source_url "
    "FROM acquisition_tasks WHERE "
    "(status = 'pending' OR (status = 'retry' AND next_attempt_at <= ?) "
    "OR (status = 'in_progress' AND lease_until <= ?)) "
    "ORDER BY stage_order, contract_id LIMIT ?"
)
READY_SOURCE_QUERY = (
    "SELECT task_id, contract_id, stage, status, attempts, source_url "
    "FROM acquisition_tasks WHERE "
    "(status = 'pending' OR (status = 'retry' AND next_attempt_at <= ?) "
    "OR (status = 'in_progress' AND lease_until <= ?)) "
    "AND source_url IS NOT NULL ORDER BY stage_order, contract_id LIMIT ?"
)


@dataclass(frozen=True, slots=True)
class AcquisitionTask:
    task_id: str
    contract_id: str
    stage: str
    status: str
    attempts: int
    source_url: str | None


@dataclass(frozen=True, slots=True)
class QueueResult:
    status: str
    source_url: str | None = None
    artifact_sha256: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class QueueSummary:
    total_tasks: int
    status_counts: dict[str, int]


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE queue_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE queue_contracts (
    contract_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    budget_centavos INTEGER NOT NULL,
    province TEXT NOT NULL,
    region TEXT NOT NULL,
    identifier_status TEXT NOT NULL,
    year_alignment TEXT NOT NULL,
    match_state TEXT NOT NULL,
    accepted_match_rows INTEGER NOT NULL,
    quarantined_match_rows INTEGER NOT NULL
);
CREATE TABLE acquisition_tasks (
    task_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES queue_contracts(contract_id),
    stage TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    lease_until TEXT,
    source_url TEXT,
    artifact_sha256 TEXT,
    http_status INTEGER,
    last_note TEXT,
    updated_at TEXT,
    UNIQUE (contract_id, stage)
);
CREATE TABLE acquisition_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES acquisition_tasks(task_id),
    attempted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_url TEXT,
    artifact_sha256 TEXT,
    http_status INTEGER,
    note TEXT
);
CREATE INDEX acquisition_tasks_ready
ON acquisition_tasks (status, next_attempt_at, lease_until, stage_order, contract_id);
"""


def _initial_status(match_state: str, identifier_status: str, stage: str) -> str:
    if identifier_status != "valid":
        return "quarantined"
    if stage == "award_notice" and match_state == "conflict_review":
        return "quarantined"
    if stage == "award_notice" and match_state in {
        "structured_exact", "title_exact", "multiple_exact_rows",
    }:
        return "secondary_exact"
    return "pending"


def _metadata(snapshot: AcquisitionUniverseSnapshot) -> dict[str, str]:
    return {
        "award_revision": snapshot.award_revision,
        "award_sha256": snapshot.award_sha256,
        "checked_on": snapshot.checked_on.isoformat(),
        "contract_count": str(snapshot.summary.contract_count),
        "delivery_sha256": snapshot.delivery_sha256,
        "lifecycle_task_count": str(snapshot.summary.lifecycle_task_count),
        "schema_version": "1",
    }


def _insert_snapshot(connection: sqlite3.Connection, snapshot: AcquisitionUniverseSnapshot) -> None:
    connection.executemany(
        "INSERT INTO queue_metadata VALUES (?, ?)", sorted(_metadata(snapshot).items())
    )
    connection.executemany(
        "INSERT INTO queue_contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                item.contract_id, item.fiscal_year, item.description, item.category,
                item.delivery_status, item.budget_centavos, item.province, item.region,
                item.identifier_status, item.year_alignment, item.match_state,
                item.accepted_match_rows, item.quarantined_match_rows,
            )
            for item in snapshot.contracts
        ],
    )
    tasks = []
    for item in snapshot.contracts:
        for stage_order, stage in enumerate(STAGES):
            tasks.append((
                f"{item.contract_id}:{stage}", item.contract_id, stage, stage_order,
                _initial_status(item.match_state, item.identifier_status, stage),
            ))
    connection.executemany(
        "INSERT INTO acquisition_tasks "
        "(task_id, contract_id, stage, stage_order, status) VALUES (?, ?, ?, ?, ?)",
        tasks,
    )


def _verify_existing(path: Path, snapshot: AcquisitionUniverseSnapshot) -> None:
    connection = sqlite3.connect(path)
    try:
        observed = dict(connection.execute("SELECT key, value FROM queue_metadata"))
    finally:
        connection.close()
    expected = _metadata(snapshot)
    if any(observed.get(key) != value for key, value in expected.items()):
        raise ValueError("existing queue belongs to a different source snapshot")


def create_acquisition_queue(path: Path, snapshot: AcquisitionUniverseSnapshot) -> None:
    if path.exists():
        _verify_existing(path, snapshot)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    building = path.with_name(f".{path.name}.building")
    if building.exists():
        building.unlink()
    connection = sqlite3.connect(building)
    try:
        connection.executescript(SCHEMA)
        _insert_snapshot(connection, snapshot)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("acquisition queue integrity check failed")
        connection.commit()
    finally:
        connection.close()
    building.replace(path)


def _reviewed_status(status: str, retry_eligible: bool) -> str:
    if status == "secondary":
        return "secondary_exact"
    if status == "blocked" and retry_eligible:
        return "retry"
    if status in {"verified_archived", "not_located", "quarantined"}:
        return status
    return "pending"


def apply_reviewed_evidence(path: Path, catalog: ContractEvidenceCatalog) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for item in catalog.items:
            task_id = f"{item.contract_id}:{item.stage}"
            current = connection.execute(
                "SELECT status FROM acquisition_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None:
                raise ValueError(f"reviewed task is outside the acquisition universe: {task_id}")
            if current[0] == "quarantined":
                continue
            status = _reviewed_status(item.status, item.retry_eligible)
            next_attempt = (
                f"{item.last_checked_at}T00:00:00+00:00" if status == "retry" else None
            )
            connection.execute(
                "UPDATE acquisition_tasks SET status = ?, next_attempt_at = ?, "
                "source_url = ?, artifact_sha256 = ?, http_status = ?, last_note = ?, "
                "updated_at = ? WHERE task_id = ?",
                (
                    status, next_attempt, item.source_url, item.artifact_sha256,
                    item.http_status, item.limitation,
                    f"{item.last_checked_at}T00:00:00+00:00", task_id,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("queue timestamps must be timezone-aware")
    return value.isoformat()


class AcquisitionQueue:
    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("acquisition queue does not exist")
        self._path = path

    def claim_batch(
        self,
        *,
        limit: int,
        now: datetime,
        lease_seconds: int,
        require_source_url: bool = False,
    ) -> tuple[AcquisitionTask, ...]:
        if limit <= 0 or lease_seconds <= 0:
            raise ValueError("limit and lease_seconds must be positive")
        timestamp = _iso(now)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            query = READY_SOURCE_QUERY if require_source_url else READY_QUERY
            rows = connection.execute(
                query,
                (timestamp, timestamp, limit),
            ).fetchall()
            connection.executemany(
                "UPDATE acquisition_tasks SET status = 'in_progress', lease_until = ?, "
                "updated_at = ? WHERE task_id = ?",
                [(lease_until, timestamp, row["task_id"]) for row in rows],
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(AcquisitionTask(**dict(row)) for row in rows)

    def record_result(self, task_id: str, result: QueueResult, *, now: datetime) -> None:
        self._validate_result(result)
        timestamp = _iso(now)
        next_attempt = (
            (now + timedelta(seconds=result.retry_after_seconds or 0)).isoformat()
            if result.status == "retry" else None
        )
        connection = sqlite3.connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status FROM acquisition_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None or current[0] != "in_progress":
                raise ValueError("task must hold an active lease")
            values = (
                result.status, next_attempt, result.source_url, result.artifact_sha256,
                result.http_status, result.note, timestamp, task_id,
            )
            connection.execute(
                "UPDATE acquisition_tasks SET status = ?, attempts = attempts + 1, "
                "next_attempt_at = ?, lease_until = NULL, source_url = ?, "
                "artifact_sha256 = ?, http_status = ?, last_note = ?, updated_at = ? "
                "WHERE task_id = ?",
                values,
            )
            connection.execute(
                "INSERT INTO acquisition_attempts "
                "(task_id, attempted_at, status, source_url, artifact_sha256, http_status, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id, timestamp, result.status, result.source_url,
                    result.artifact_sha256, result.http_status, result.note,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _validate_result(result: QueueResult) -> None:
        if result.status not in RESULT_STATUSES:
            raise ValueError("unsupported queue result status")
        if result.status == "verified_archived" and (
            not result.source_url
            or not result.source_url.startswith("https://")
            or result.artifact_sha256 is None
            or SHA256.fullmatch(result.artifact_sha256) is None
        ):
            raise ValueError("verified result requires an HTTPS source and artifact hash")
        if result.status == "retry" and (
            result.http_status is None
            or not HTTP_ERROR_MINIMUM <= result.http_status <= HTTP_ERROR_MAXIMUM
            or result.retry_after_seconds is None
            or result.retry_after_seconds <= 0
        ):
            raise ValueError("retry result requires an HTTP failure and positive delay")

    def summary(self) -> QueueSummary:
        connection = sqlite3.connect(self._path)
        try:
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM acquisition_tasks GROUP BY status"
            ).fetchall()
        finally:
            connection.close()
        counts = Counter(dict(rows))
        return QueueSummary(sum(counts.values()), dict(sorted(counts.items())))
