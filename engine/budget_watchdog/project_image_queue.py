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
_SCHEMA_VERSION = "3"
_CONFLICT_RECHECK_SECONDS = 86_400
_BLOCKED_RECHECK_SECONDS = 604_800
_MAX_CONFLICT_ATTEMPTS = 2
_RECHECK_LIMIT = 250
_OUTCOME_CODES = frozenset(
    {
        "verified_exact",
        "source_reports_no_images",
        "source_count_mismatch",
        "duplicate_image_payload",
        "source_rate_limited",
        "source_access_denied",
        "source_not_found",
        "source_server_error",
        "source_network_error",
        "source_client_error",
        "evidence_validation",
    }
)
_FAILURE_OUTCOME_CODES = frozenset(
    {
        "source_rate_limited",
        "source_access_denied",
        "source_not_found",
        "source_server_error",
        "source_network_error",
        "source_client_error",
        "evidence_validation",
    }
)
_OUTCOME_STAGES = frozenset({"evidence", "metadata", "media", "unknown"})
_RECOVERABLE_BLOCKED_CODES = (
    "source_rate_limited",
    "source_access_denied",
    "source_server_error",
    "source_network_error",
)
_REQUEUE_CONFLICT_SQL = (
    "SELECT contract_id FROM image_tasks WHERE status = 'count_conflict' "
    "AND attempts < ? AND updated_at <= ? ORDER BY priority, contract_id LIMIT ?"
)
_REQUEUE_BLOCKED_SQL = (
    "SELECT contract_id FROM image_tasks WHERE status = 'blocked' AND updated_at <= ? "
    "AND contract_id IN (SELECT contract_id FROM image_task_outcomes WHERE outcome_code "
    "IN (?, ?, ?, ?)) ORDER BY priority, contract_id LIMIT ?"
)


def _connect(path: Path) -> sqlite3.Connection:
    """Open the private queue with a bounded wait for transient lock contention."""
    connection = sqlite3.connect(
        path,
        timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
    )
    connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
    connection.execute("PRAGMA foreign_keys = ON")
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
CREATE TABLE image_task_outcomes (
    contract_id TEXT PRIMARY KEY REFERENCES image_tasks(contract_id),
    outcome_code TEXT NOT NULL,
    outcome_stage TEXT NOT NULL,
    recorded_at TEXT NOT NULL
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
        "schema_version": _SCHEMA_VERSION,
        "seed_count": str(len(seeds)),
        "seed_sha256": _seed_digest(seeds),
        "source_sha256": source_sha256,
    }


def _migrate_queue_schema(path: Path) -> None:
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS image_task_outcomes ("
            "contract_id TEXT PRIMARY KEY REFERENCES image_tasks(contract_id), "
            "outcome_code TEXT NOT NULL, outcome_stage TEXT NOT NULL, "
            "recorded_at TEXT NOT NULL)"
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO image_task_outcomes
                (contract_id, outcome_code, outcome_stage, recorded_at)
            SELECT contract_id,
                CASE
                    WHEN status = 'verified_exact' THEN 'verified_exact'
                    WHEN status = 'no_images' THEN 'source_reports_no_images'
                    WHEN status = 'count_conflict' AND last_note LIKE '%duplicate JPEG content%'
                        THEN 'duplicate_image_payload'
                    WHEN status = 'count_conflict' THEN 'source_count_mismatch'
                    WHEN last_note LIKE '%HTTP 429%' THEN 'source_rate_limited'
                    WHEN last_note LIKE '%HTTP 401%' OR last_note LIKE '%HTTP 403%'
                        THEN 'source_access_denied'
                    WHEN last_note LIKE '%HTTP 404%' OR last_note LIKE '%HTTP 410%'
                        THEN 'source_not_found'
                    WHEN last_note GLOB '*HTTP 5[0-9][0-9]*' THEN 'source_server_error'
                    WHEN last_note LIKE 'Evidence validation failed%' THEN 'evidence_validation'
                    ELSE 'source_network_error'
                END,
                'unknown',
                COALESCE(updated_at, '1970-01-01T00:00:00+00:00')
            FROM image_tasks
            WHERE status IN (
                'verified_exact', 'no_images', 'count_conflict', 'retry', 'blocked'
            )
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
        priorities_changed = observed.get("seed_sha256") != metadata["seed_sha256"]
        if priorities_changed:
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
        if priorities_changed:
            connection.executemany(
                "UPDATE image_tasks SET priority = ? WHERE contract_id = ?",
                [(seed.priority, seed.contract_id) for seed in seeds],
            )
        connection.execute("DELETE FROM queue_metadata")
        connection.executemany(
            "INSERT INTO queue_metadata VALUES (?, ?)", sorted(metadata.items())
        )
        if priorities_changed and connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("image coverage queue integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("image coverage queue foreign keys are invalid")
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
        _migrate_queue_schema(path)
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
        0 if row["status"] == "retry" else 1,
        row["priority"],
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

    def requeue_count_conflicts(
        self,
        *,
        now: datetime,
        cooldown_seconds: int = _CONFLICT_RECHECK_SECONDS,
        limit: int = _RECHECK_LIMIT,
        max_attempts: int = _MAX_CONFLICT_ATTEMPTS,
    ) -> int:
        """Schedule one delayed second look at conflicting source representations."""
        if min(cooldown_seconds, limit, max_attempts) <= 0:
            raise ValueError("conflict recheck limits must be positive")
        cutoff = _iso(now - timedelta(seconds=cooldown_seconds))
        return self._requeue_matching(
            query=_REQUEUE_CONFLICT_SQL,
            parameters=(max_attempts, cutoff),
            now=now,
            limit=limit,
            note="Source disagreement scheduled for one delayed recheck.",
        )

    def requeue_recoverable_blocked(
        self,
        *,
        now: datetime,
        cooldown_seconds: int = _BLOCKED_RECHECK_SECONDS,
        limit: int = _RECHECK_LIMIT,
    ) -> int:
        """Retry blocked source conditions that may recover, never permanent absence."""
        if min(cooldown_seconds, limit) <= 0:
            raise ValueError("blocked recheck limits must be positive")
        cutoff = _iso(now - timedelta(seconds=cooldown_seconds))
        return self._requeue_matching(
            query=_REQUEUE_BLOCKED_SQL,
            parameters=(cutoff, *_RECOVERABLE_BLOCKED_CODES),
            now=now,
            limit=limit,
            note="Recoverable source failure scheduled for a delayed recheck.",
        )

    def _requeue_matching(
        self,
        *,
        query: str,
        parameters: tuple[object, ...],
        now: datetime,
        limit: int,
        note: str,
    ) -> int:
        timestamp = _iso(now)
        connection = _connect(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                query,
                (*parameters, limit),
            ).fetchall()
            connection.executemany(
                "UPDATE image_tasks SET status = 'retry', lease_until = NULL, "
                "next_attempt_at = ?, last_note = ? WHERE contract_id = ?",
                [(timestamp, note, row[0]) for row in rows],
            )
            connection.commit()
            return len(rows)
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
            previous_keys = {
                (row[0], row[1]): row[2]
                for row in connection.execute(
                    "SELECT image_id, artifact_sha256, archive_key FROM image_records "
                    "WHERE contract_id = ?",
                    (contract_id,),
                )
            }
            connection.execute("DELETE FROM image_records WHERE contract_id = ?", (contract_id,))
            connection.executemany(
                "INSERT INTO image_records VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [self._image_values(item, previous_keys) for item in images],
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
            self._record_outcome(
                connection,
                contract_id,
                self._evidence_outcome(coverage, images),
                "evidence",
                timestamp,
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
        previous_keys: dict[tuple[str, str], str],
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
            previous_keys.get((record.image_id, inspection.sha256), archive_key),
            source_path,
        )

    def record_failure(
        self,
        contract_id: str,
        *,
        status: str,
        reason_code: str,
        reason_stage: str,
        note: str,
        now: datetime,
        retry_after_seconds: int | None = None,
    ) -> None:
        if status not in _FAILURE_STATES:
            raise ValueError("unsupported image acquisition failure state")
        if not note.strip():
            raise ValueError("image acquisition failure requires a note")
        if reason_code not in _FAILURE_OUTCOME_CODES:
            raise ValueError("unsupported image acquisition failure reason")
        if reason_stage not in _OUTCOME_STAGES:
            raise ValueError("unsupported image acquisition failure stage")
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
            self._record_outcome(
                connection, contract_id, reason_code, reason_stage, timestamp
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
    def _record_outcome(
        connection: sqlite3.Connection,
        contract_id: str,
        outcome_code: str,
        outcome_stage: str,
        recorded_at: str,
    ) -> None:
        if outcome_code not in _OUTCOME_CODES:
            raise ValueError("unsupported project-image outcome code")
        if outcome_stage not in _OUTCOME_STAGES:
            raise ValueError("unsupported project-image outcome stage")
        connection.execute(
            "INSERT INTO image_task_outcomes VALUES (?, ?, ?, ?) "
            "ON CONFLICT(contract_id) DO UPDATE SET "
            "outcome_code = excluded.outcome_code, "
            "outcome_stage = excluded.outcome_stage, recorded_at = excluded.recorded_at",
            (contract_id, outcome_code, outcome_stage, recorded_at),
        )

    @staticmethod
    def _evidence_outcome(
        coverage: ProjectImageCoverage,
        images: tuple[tuple[ProjectImageRecord, ImageInspection, str, str], ...],
    ) -> str:
        if coverage.state == "verified_exact":
            return "verified_exact"
        if coverage.state == "no_images":
            return "source_reports_no_images"
        unique_payloads = len({inspection.sha256 for _, inspection, _, _ in images})
        return (
            "duplicate_image_payload"
            if unique_payloads < len(images)
            else "source_count_mismatch"
        )

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

    def outcome_counts(self) -> dict[str, int]:
        connection = _connect(self._path)
        try:
            rows = connection.execute(
                "SELECT outcome_code, COUNT(*) FROM image_task_outcomes "
                "GROUP BY outcome_code ORDER BY outcome_code"
            ).fetchall()
        finally:
            connection.close()
        return dict(rows)

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
                "SELECT image_records.* FROM image_records "
                "JOIN image_tasks USING (contract_id) WHERE image_tasks.status IN "
                "('verified_exact', 'no_images', 'count_conflict') ORDER BY image_id"
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
