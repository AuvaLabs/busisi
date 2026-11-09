"""Durable private queue for deterministic project-image coverage expansion."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from engine.budget_watchdog.project_image_bundle import AcquiredProjectImage
from engine.budget_watchdog.project_images import (
    ImageInspection,
    ProjectImageCoverage,
    ProjectImageRecord,
)

_CONTRACT_ID = re.compile(r"^[A-Z0-9-]{4,40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_STATES = frozenset({"verified_exact", "no_images", "count_conflict"})
_FAILURE_STATES = frozenset({"retry", "blocked"})
_MIN_FISCAL_YEAR = 2000
_MAX_FISCAL_YEAR = 2100
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 30_000


def _connect(path: Path) -> sqlite3.Connection:
    """Open the private queue with a bounded wait for transient lock contention."""
    connection = sqlite3.connect(
        path,
        timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
    )
    connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
    return connection


@dataclass(frozen=True, slots=True)
class ImageCoverageSeed:
    contract_id: str
    fiscal_year: int
    source_image_hint: bool
    priority: int = 100


@dataclass(frozen=True, slots=True)
class ImageCoverageTask:
    contract_id: str
    fiscal_year: int
    source_image_hint: bool
    status: str
    attempts: int


@dataclass(frozen=True, slots=True)
class ImageCoverageSummary:
    total_tasks: int
    status_counts: dict[str, int]


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE queue_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE image_tasks (
    contract_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    source_image_hint INTEGER NOT NULL CHECK (source_image_hint IN (0, 1)),
    priority INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'in_progress', 'verified_exact', 'no_images',
        'count_conflict', 'retry', 'blocked'
    )),
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    next_attempt_at TEXT,
    last_note TEXT,
    updated_at TEXT,
    summary_count INTEGER,
    endpoint_count INTEGER,
    has_images INTEGER,
    detail_sha256 TEXT,
    list_sha256 TEXT
);
CREATE TABLE image_records (
    image_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES image_tasks(contract_id),
    component_id TEXT NOT NULL,
    photo_number INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    source_status TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    fiscal_year TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    coordinate_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    thumbnail_source_url TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    archive_key TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    UNIQUE (contract_id, source_url)
);
CREATE TABLE image_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL REFERENCES image_tasks(contract_id),
    attempted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX image_tasks_ready
ON image_tasks (status, next_attempt_at, lease_until, priority, contract_id);
CREATE INDEX image_records_contract ON image_records (contract_id, photo_number, image_id);
"""


def _seed_digest(seeds: tuple[ImageCoverageSeed, ...]) -> str:
    rows = [
        [seed.contract_id, seed.fiscal_year, seed.source_image_hint, seed.priority]
        for seed in seeds
    ]
    return hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _validated_seeds(seeds: Iterable[ImageCoverageSeed]) -> tuple[ImageCoverageSeed, ...]:
    ordered = tuple(sorted(seeds, key=lambda item: (item.priority, item.contract_id)))
    identifiers = [item.contract_id for item in ordered]
    if not ordered or len(identifiers) != len(set(identifiers)):
        raise ValueError("image coverage seeds must be non-empty and unique")
    if any(
        _CONTRACT_ID.fullmatch(item.contract_id) is None
        or not _MIN_FISCAL_YEAR <= item.fiscal_year <= _MAX_FISCAL_YEAR
        or item.priority < 0
        for item in ordered
    ):
        raise ValueError("image coverage seed is invalid")
    return ordered


def _expected_metadata(seeds: tuple[ImageCoverageSeed, ...], source_sha256: str) -> dict[str, str]:
    if _SHA256.fullmatch(source_sha256) is None:
        raise ValueError("source snapshot digest must be SHA-256")
    return {
        "schema_version": "2",
        "seed_count": str(len(seeds)),
        "seed_sha256": _seed_digest(seeds),
        "source_sha256": source_sha256,
    }


def _refresh_priorities(
    path: Path,
    seeds: tuple[ImageCoverageSeed, ...],
    metadata: dict[str, str],
) -> None:
    connection = _connect(path)
    try:
        observed = dict(connection.execute("SELECT key, value FROM queue_metadata"))
        if (
            observed.get("source_sha256") != metadata["source_sha256"]
            or observed.get("seed_count") != metadata["seed_count"]
        ):
            raise ValueError("existing image queue belongs to a different source snapshot")
        existing = tuple(
            connection.execute(
                "SELECT contract_id, fiscal_year, source_image_hint "
                "FROM image_tasks ORDER BY contract_id"
            )
        )
        expected = tuple(
            sorted(
                (
                    seed.contract_id,
                    seed.fiscal_year,
                    int(seed.source_image_hint),
                )
                for seed in seeds
            )
        )
        if existing != expected:
            raise ValueError("existing image queue belongs to a different source snapshot")
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "UPDATE image_tasks SET priority = ? WHERE contract_id = ?",
            [(seed.priority, seed.contract_id) for seed in seeds],
        )
        connection.execute("DELETE FROM queue_metadata")
        connection.executemany(
            "INSERT INTO queue_metadata VALUES (?, ?)", sorted(metadata.items())
        )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("image coverage queue integrity check failed")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_image_coverage_queue(
    path: Path,
    seeds: Iterable[ImageCoverageSeed],
    *,
    source_sha256: str,
) -> None:
    """Create a queue once, or verify that an existing queue has the same identity."""
    validated = _validated_seeds(seeds)
    metadata = _expected_metadata(validated, source_sha256)
    if path.exists():
        connection = _connect(path)
        try:
            observed = dict(connection.execute("SELECT key, value FROM queue_metadata"))
        finally:
            connection.close()
        if observed != metadata:
            _refresh_priorities(path, validated, metadata)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    building = path.with_name(f".{path.name}.building")
    building.unlink(missing_ok=True)
    connection = _connect(building)
    try:
        connection.executescript(SCHEMA)
        connection.executemany("INSERT INTO queue_metadata VALUES (?, ?)", sorted(metadata.items()))
        connection.executemany(
            "INSERT INTO image_tasks "
            "(contract_id, fiscal_year, source_image_hint, priority, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            [
                (
                    seed.contract_id,
                    seed.fiscal_year,
                    int(seed.source_image_hint),
                    seed.priority,
                )
                for seed in validated
            ],
        )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("image coverage queue integrity check failed")
        connection.commit()
    finally:
        connection.close()
    building.replace(path)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("queue timestamps must be timezone-aware")
    return value.isoformat()


def _task(row: sqlite3.Row) -> ImageCoverageTask:
    return ImageCoverageTask(
        contract_id=row["contract_id"],
        fiscal_year=row["fiscal_year"],
        source_image_hint=bool(row["source_image_hint"]),
        status=row["status"],
        attempts=row["attempts"],
    )


def _selection_key(row: sqlite3.Row) -> tuple[int, int, bytes]:
    identity = f"{row['fiscal_year']}:{row['source_image_hint']}:{row['contract_id']}".encode()
    return (
        row["priority"],
        0 if row["status"] == "retry" else 1,
        hashlib.sha256(identity).digest(),
    )


class ImageCoverageQueue:
    """Lease tasks and persist evidence without exposing the queue publicly."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise ValueError("image coverage queue does not exist")
        self._path = path

    def recover_interrupted_leases(self, *, now: datetime) -> int:
        """Return unfinished leases to pending while the caller holds the cycle lock."""
        timestamp = _iso(now)
        connection = _connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE image_tasks SET status = 'pending', lease_until = NULL, "
                "next_attempt_at = NULL, last_note = ?, updated_at = ? "
                "WHERE status = 'in_progress'",
                (
                    "The previous coverage cycle ended before recording a result; "
                    "the task was returned to the queue.",
                    timestamp,
                ),
            )
            connection.commit()
            return cursor.rowcount
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_batch(
        self, *, limit: int, now: datetime, lease_seconds: int
    ) -> tuple[ImageCoverageTask, ...]:
        if limit <= 0 or lease_seconds <= 0:
            raise ValueError("limit and lease_seconds must be positive")
        timestamp = _iso(now)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        connection = _connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            eligible = connection.execute(
                "SELECT contract_id, fiscal_year, source_image_hint, status, attempts, priority "
                "FROM image_tasks WHERE status = 'pending' "
                "OR (status = 'retry' AND next_attempt_at <= ?) "
                "OR (status = 'in_progress' AND lease_until <= ?) "
                "ORDER BY contract_id",
                (timestamp, timestamp),
            ).fetchall()
            rows = sorted(eligible, key=_selection_key)[:limit]
            connection.executemany(
                "UPDATE image_tasks SET status = 'in_progress', lease_until = ?, "
                "updated_at = ? WHERE contract_id = ?",
                [(lease_until, timestamp, row["contract_id"]) for row in rows],
            )
            connection.commit()
        finally:
            connection.close()
        return tuple(_task(row) for row in rows)

    def record_evidence(
        self,
        contract_id: str,
        coverage: ProjectImageCoverage,
        images: tuple[tuple[ProjectImageRecord, ImageInspection, str, str], ...],
        *,
        now: datetime,
    ) -> None:
        if contract_id != coverage.contract_id:
            raise ValueError("coverage contract does not match the leased contract")
        if coverage.state not in _TERMINAL_STATES:
            raise ValueError("unsupported image coverage state")
        if coverage.endpoint_count != len(images):
            raise ValueError("image records do not match the endpoint count")
        if any(record.contract_id != contract_id for record, _, _, _ in images):
            raise ValueError("image contract does not match the leased contract")
        timestamp = _iso(now)
        connection = _connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_lease(connection, contract_id)
            connection.execute("DELETE FROM image_records WHERE contract_id = ?", (contract_id,))
            connection.executemany(
                "INSERT INTO image_records VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [self._image_values(item) for item in images],
            )
            connection.execute(
                "UPDATE image_tasks SET status = ?, attempts = attempts + 1, "
                "lease_until = NULL, next_attempt_at = NULL, last_note = ?, updated_at = ?, "
                "summary_count = ?, endpoint_count = ?, has_images = ?, "
                "detail_sha256 = ?, list_sha256 = ? WHERE contract_id = ?",
                (
                    coverage.state,
                    coverage.note,
                    timestamp,
                    coverage.summary_count,
                    coverage.endpoint_count,
                    int(coverage.has_images),
                    coverage.detail_sha256,
                    coverage.list_sha256,
                    contract_id,
                ),
            )
            connection.execute(
                "INSERT INTO image_attempts (contract_id, attempted_at, status, note) "
                "VALUES (?, ?, ?, ?)",
                (contract_id, timestamp, coverage.state, coverage.note),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _image_values(
        item: tuple[ProjectImageRecord, ImageInspection, str, str],
    ) -> tuple[object, ...]:
        record, inspection, archive_key, source_path = item
        return (
            record.image_id,
            record.contract_id,
            record.component_id,
            record.photo_number,
            record.purpose,
            record.status,
            record.captured_at,
            record.fiscal_year,
            record.latitude,
            record.longitude,
            record.coordinate_status,
            record.source_url,
            record.thumbnail_source_url,
            inspection.sha256,
            inspection.content_type,
            inspection.byte_size,
            inspection.width,
            inspection.height,
            archive_key,
            source_path,
        )

    def record_failure(
        self,
        contract_id: str,
        *,
        status: str,
        note: str,
        now: datetime,
        retry_after_seconds: int | None = None,
    ) -> None:
        if status not in _FAILURE_STATES:
            raise ValueError("unsupported image acquisition failure state")
        if not note.strip():
            raise ValueError("image acquisition failure requires a note")
        if status == "retry" and (retry_after_seconds is None or retry_after_seconds <= 0):
            raise ValueError("retry requires a positive delay")
        timestamp = _iso(now)
        next_attempt = (
            (now + timedelta(seconds=retry_after_seconds or 0)).isoformat()
            if status == "retry"
            else None
        )
        connection = _connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_lease(connection, contract_id)
            connection.execute(
                "UPDATE image_tasks SET status = ?, attempts = attempts + 1, "
                "lease_until = NULL, next_attempt_at = ?, last_note = ?, updated_at = ? "
                "WHERE contract_id = ?",
                (status, next_attempt, note, timestamp, contract_id),
            )
            connection.execute(
                "INSERT INTO image_attempts (contract_id, attempted_at, status, note) "
                "VALUES (?, ?, ?, ?)",
                (contract_id, timestamp, status, note),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _require_lease(connection: sqlite3.Connection, contract_id: str) -> None:
        row = connection.execute(
            "SELECT status FROM image_tasks WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        if row is None or row[0] != "in_progress":
            raise ValueError("task must hold an active lease")

    def summary(self) -> ImageCoverageSummary:
        connection = _connect(self._path)
        try:
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM image_tasks GROUP BY status"
            ).fetchall()
        finally:
            connection.close()
        counts = Counter(dict(rows))
        return ImageCoverageSummary(sum(counts.values()), dict(sorted(counts.items())))

    def publication_records(
        self,
    ) -> tuple[tuple[ProjectImageCoverage, ...], tuple[AcquiredProjectImage, ...]]:
        connection = _connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            coverage_rows = connection.execute(
                "SELECT * FROM image_tasks WHERE status IN "
                "('verified_exact', 'no_images', 'count_conflict') ORDER BY contract_id"
            ).fetchall()
            image_rows = connection.execute(
                "SELECT * FROM image_records ORDER BY image_id"
            ).fetchall()
        finally:
            connection.close()
        coverage = tuple(self._coverage(row) for row in coverage_rows)
        images = tuple(self._acquired_image(row) for row in image_rows)
        return coverage, images

    @staticmethod
    def _coverage(row: sqlite3.Row) -> ProjectImageCoverage:
        return ProjectImageCoverage(
            contract_id=row["contract_id"],
            summary_count=row["summary_count"],
            endpoint_count=row["endpoint_count"],
            has_images=bool(row["has_images"]),
            state=row["status"],
            detail_sha256=row["detail_sha256"],
            list_sha256=row["list_sha256"],
            note=row["last_note"],
        )

    @staticmethod
    def _acquired_image(row: sqlite3.Row) -> AcquiredProjectImage:
        metadata = ProjectImageRecord(
            image_id=row["image_id"],
            contract_id=row["contract_id"],
            component_id=row["component_id"],
            source_url=row["source_url"],
            thumbnail_source_url=row["thumbnail_source_url"],
            purpose=row["purpose"],
            status=row["source_status"],
            captured_at=row["captured_at"],
            fiscal_year=row["fiscal_year"],
            photo_number=row["photo_number"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            coordinate_status=row["coordinate_status"],
        )
        inspection = ImageInspection(
            sha256=row["artifact_sha256"],
            byte_size=row["byte_size"],
            width=row["width"],
            height=row["height"],
            content_type=row["content_type"],
        )
        return AcquiredProjectImage(
            metadata=metadata,
            inspection=inspection,
            archive_key=row["archive_key"],
            source_path=Path(row["source_path"]),
        )
