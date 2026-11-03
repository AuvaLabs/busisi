"""Local canonical store for resumable, immutable source ingestion."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType

from engine.budget_watchdog.family import build_family_identity
from engine.budget_watchdog.identity import BudgetProject, DeliveryProject
from engine.budget_watchdog.parquet_snapshots import SnapshotIssue

SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_projects (
    budget_line_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount_centavos INTEGER NOT NULL,
    location TEXT NOT NULL,
    source_references TEXT NOT NULL,
    project_family_id TEXT NOT NULL,
    family_canonical_text TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    PRIMARY KEY (budget_line_id, fiscal_year, artifact_sha256)
);

CREATE INDEX IF NOT EXISTS ix_budget_projects_year
ON budget_projects (fiscal_year);

CREATE INDEX IF NOT EXISTS ix_budget_projects_family
ON budget_projects (project_family_id);

CREATE TABLE IF NOT EXISTS delivery_projects (
    contract_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    budget_centavos INTEGER NOT NULL,
    location TEXT NOT NULL,
    source_of_funds TEXT NOT NULL,
    source_references TEXT NOT NULL,
    project_family_id TEXT NOT NULL,
    family_canonical_text TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    PRIMARY KEY (contract_id, artifact_sha256)
);

CREATE INDEX IF NOT EXISTS ix_delivery_projects_year
ON delivery_projects (fiscal_year);

CREATE INDEX IF NOT EXISTS ix_delivery_projects_family
ON delivery_projects (project_family_id);

CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    source_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    position TEXT NOT NULL,
    completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_id, stream_id)
);

CREATE TABLE IF NOT EXISTS quarantine_records (
    artifact_sha256 TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    code TEXT NOT NULL,
    detail TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    amount_centavos INTEGER,
    PRIMARY KEY (artifact_sha256, row_number, code)
);

PRAGMA user_version = 2;
"""

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REFERENCE_SEPARATOR = "\x1f"


class StorageConflictError(RuntimeError):
    """Raised when immutable snapshot identity maps to different content."""


@dataclass(frozen=True, slots=True)
class IngestionCheckpoint:
    source_id: str
    stream_id: str
    position: str
    completed: bool
    updated_at: datetime


class CanonicalStore:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)

    def __enter__(self) -> "CanonicalStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def store_budget_projects(
        self,
        projects: tuple[BudgetProject, ...],
        artifact_sha256: str,
    ) -> int:
        self._validate_sha256(artifact_sha256)
        inserted = 0
        with self._connection:
            for project in projects:
                family = build_family_identity(project.description)
                values = (
                    project.budget_line_id,
                    project.fiscal_year,
                    project.description,
                    project.amount_centavos,
                    project.location,
                    REFERENCE_SEPARATOR.join(project.source_references),
                    family.family_id,
                    family.canonical_text,
                    artifact_sha256,
                )
                inserted += self._insert_immutable_budget(values)
        return inserted

    def _insert_immutable_budget(self, values: tuple[object, ...]) -> int:
        key = (values[0], values[1], values[8])
        existing = self._connection.execute(
            """
            SELECT budget_line_id, fiscal_year, description, amount_centavos,
                   location, source_references, project_family_id,
                   family_canonical_text, artifact_sha256
            FROM budget_projects
            WHERE budget_line_id = ? AND fiscal_year = ? AND artifact_sha256 = ?
            """,
            key,
        ).fetchone()
        if existing is not None:
            existing_values = tuple(existing)
            existing_source = existing_values[:6] + (existing_values[8],)
            incoming_source = values[:6] + (values[8],)
            if existing_source != incoming_source:
                raise StorageConflictError("immutable budget snapshot conflicts")
            if existing_values[6:8] != values[6:8]:
                self._connection.execute(
                    """
                    UPDATE budget_projects
                    SET project_family_id = ?, family_canonical_text = ?
                    WHERE budget_line_id = ? AND fiscal_year = ? AND artifact_sha256 = ?
                    """,
                    (values[6], values[7], *key),
                )
            return 0
        self._connection.execute(
            """
            INSERT INTO budget_projects (
                budget_line_id, fiscal_year, description, amount_centavos,
                location, source_references, project_family_id,
                family_canonical_text, artifact_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return 1

    def store_delivery_projects(
        self,
        projects: tuple[DeliveryProject, ...],
        artifact_sha256: str,
    ) -> int:
        self._validate_sha256(artifact_sha256)
        inserted = 0
        with self._connection:
            for project in projects:
                family = build_family_identity(project.description)
                values = (
                    project.contract_id,
                    project.fiscal_year,
                    project.description,
                    project.budget_centavos,
                    project.location,
                    project.source_of_funds,
                    REFERENCE_SEPARATOR.join(project.source_references),
                    family.family_id,
                    family.canonical_text,
                    artifact_sha256,
                )
                inserted += self._insert_immutable_delivery(values)
        return inserted

    def _insert_immutable_delivery(self, values: tuple[object, ...]) -> int:
        key = (values[0], values[9])
        existing = self._connection.execute(
            """
            SELECT contract_id, fiscal_year, description, budget_centavos,
                   location, source_of_funds, source_references,
                   project_family_id, family_canonical_text, artifact_sha256
            FROM delivery_projects
            WHERE contract_id = ? AND artifact_sha256 = ?
            """,
            key,
        ).fetchone()
        if existing is not None:
            existing_values = tuple(existing)
            existing_source = existing_values[:7] + (existing_values[9],)
            incoming_source = values[:7] + (values[9],)
            if existing_source != incoming_source:
                raise StorageConflictError("immutable delivery snapshot conflicts")
            if existing_values[7:9] != values[7:9]:
                self._connection.execute(
                    """
                    UPDATE delivery_projects
                    SET project_family_id = ?, family_canonical_text = ?
                    WHERE contract_id = ? AND artifact_sha256 = ?
                    """,
                    (values[7], values[8], *key),
                )
            return 0
        self._connection.execute(
            """
            INSERT INTO delivery_projects (
                contract_id, fiscal_year, description, budget_centavos,
                location, source_of_funds, source_references,
                project_family_id, family_canonical_text, artifact_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return 1

    def list_budget_projects(self, *, fiscal_year: int) -> tuple[BudgetProject, ...]:
        rows = self._connection.execute(
            """
            SELECT budget_line_id, fiscal_year, description, amount_centavos,
                   location, source_references
            FROM budget_projects
            WHERE fiscal_year = ?
            ORDER BY budget_line_id, artifact_sha256
            """,
            (fiscal_year,),
        ).fetchall()
        return tuple(
            BudgetProject(
                budget_line_id=row["budget_line_id"],
                fiscal_year=row["fiscal_year"],
                description=row["description"],
                amount_centavos=row["amount_centavos"],
                location=row["location"],
                source_references=self._decode_references(row["source_references"]),
            )
            for row in rows
        )

    def list_delivery_projects(self, *, fiscal_year: int) -> tuple[DeliveryProject, ...]:
        rows = self._connection.execute(
            """
            SELECT contract_id, fiscal_year, description, budget_centavos,
                   location, source_of_funds, source_references
            FROM delivery_projects
            WHERE fiscal_year = ?
            ORDER BY contract_id, artifact_sha256
            """,
            (fiscal_year,),
        ).fetchall()
        return tuple(
            DeliveryProject(
                contract_id=row["contract_id"],
                fiscal_year=row["fiscal_year"],
                description=row["description"],
                budget_centavos=row["budget_centavos"],
                location=row["location"],
                source_of_funds=row["source_of_funds"],
                source_references=self._decode_references(row["source_references"]),
            )
            for row in rows
        )

    def save_checkpoint(
        self,
        *,
        source_id: str,
        stream_id: str,
        position: str,
        completed: bool,
        updated_at: datetime,
    ) -> None:
        if updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO ingestion_checkpoints (
                    source_id, stream_id, position, completed, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, stream_id) DO UPDATE SET
                    position = excluded.position,
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (source_id, stream_id, position, int(completed), updated_at.isoformat()),
            )

    def store_quarantine_issues(
        self,
        issues: tuple[SnapshotIssue, ...],
        artifact_sha256: str,
    ) -> int:
        self._validate_sha256(artifact_sha256)
        inserted = 0
        with self._connection:
            for issue in issues:
                cursor = self._connection.execute(
                    """
                    INSERT OR IGNORE INTO quarantine_records (
                        artifact_sha256, row_number, code, detail,
                        source_identifier, amount_centavos
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_sha256,
                        issue.row_number,
                        issue.code,
                        issue.detail,
                        issue.source_identifier,
                        issue.amount_centavos,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def count_quarantine_issues(self, *, artifact_sha256: str) -> int:
        self._validate_sha256(artifact_sha256)
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS issue_count
            FROM quarantine_records
            WHERE artifact_sha256 = ?
            """,
            (artifact_sha256,),
        ).fetchone()
        assert row is not None
        return int(row["issue_count"])

    def get_checkpoint(
        self,
        *,
        source_id: str,
        stream_id: str,
    ) -> IngestionCheckpoint | None:
        row = self._connection.execute(
            """
            SELECT source_id, stream_id, position, completed, updated_at
            FROM ingestion_checkpoints
            WHERE source_id = ? AND stream_id = ?
            """,
            (source_id, stream_id),
        ).fetchone()
        if row is None:
            return None
        return IngestionCheckpoint(
            source_id=row["source_id"],
            stream_id=row["stream_id"],
            position=row["position"],
            completed=bool(row["completed"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _decode_references(value: str) -> tuple[str, ...]:
        return tuple(value.split(REFERENCE_SEPARATOR)) if value else ()

    @staticmethod
    def _validate_sha256(value: str) -> None:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("artifact_sha256 must be a lowercase SHA-256 digest")
