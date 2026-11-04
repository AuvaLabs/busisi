"""Load the public school-record universe for deterministic facility matching."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from engine.budget_watchdog.facility_identity import FacilityTitleRecord

ROOT = Path(__file__).resolve().parents[2]
HGAB_MIGRATIONS = (
    ROOT / "cloudflare/busisi/migrations/0002_public_explorer.sql",
    ROOT / "cloudflare/busisi/migrations/0003_stage_changes.sql",
    ROOT / "cloudflare/busisi/migrations/0004_review_signals.sql",
)


def _school_title(value: str) -> bool:
    title = value.casefold()
    return "school" in title or "classroom" in title


def _delivery_records(canonical_database: Path) -> tuple[FacilityTitleRecord, ...]:
    connection = sqlite3.connect(f"{canonical_database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT contract_id, description, location FROM delivery_projects ORDER BY contract_id"
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        FacilityTitleRecord("delivery", record_id, title, location)
        for record_id, title, location in rows
        if _school_title(title)
    )


def _budget_records(bundle_dir: Path) -> tuple[FacilityTitleRecord, ...]:
    chunks = sorted((bundle_dir / "chunks").glob("*.sql"))
    if not chunks:
        raise ValueError("HGAB bundle SQL chunks are unavailable")
    connection = sqlite3.connect(":memory:")
    try:
        for migration in HGAB_MIGRATIONS:
            connection.executescript(migration.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        rows = connection.execute(
            "SELECT record_id, title, region, office FROM stage_change_items ORDER BY record_id"
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        FacilityTitleRecord("budget", record_id, title, f"{office}, {region}".strip(", "))
        for record_id, title, region, office in rows
        if _school_title(title)
    )


def load_public_school_records(
    canonical_database: Path,
    hgab_bundle_dir: Path,
) -> tuple[FacilityTitleRecord, ...]:
    """Load stage-change and delivery records while retaining source separation."""

    if not canonical_database.is_file() or not hgab_bundle_dir.is_dir():
        raise ValueError("canonical database and HGAB bundle must exist")
    records = (*_budget_records(hgab_bundle_dir), *_delivery_records(canonical_database))
    identities = {(record.source_type, record.record_id) for record in records}
    if len(identities) != len(records):
        raise ValueError("public school record identities are duplicated")
    return tuple(records)
