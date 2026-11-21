"""Build a verified D1 bundle for Senate committee-stage changes."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.senate_committee import (
    ChangeControl,
    CommitteeChange,
    SenateCommitteeRelease,
    load_senate_committee_release,
    reconcile_senate_committee_release,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0034_senate_committee_changes.sql"
)


@dataclass(frozen=True, slots=True)
class SenateCommitteeBundleResult:
    output_dir: Path
    state: str
    item_count: int
    source_sha256: str
    bundle_sha256: str


def _sql_text(value: str | None) -> str:
    if value is None:
        return "NULL"
    return f"'{value.replace("'", "''")}'"


def _sql_integer(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _release_statement(release: SenateCommitteeRelease) -> str:
    summary = reconcile_senate_committee_release(release)
    document = release.official_document
    values = (
        _sql_text(release.release_id),
        str(release.fiscal_year),
        _sql_text(release.report_number),
        _sql_text(release.related_bill),
        _sql_text(release.state),
        _sql_text(release.checked_at),
        _sql_text(document.source_url if document else None),
        _sql_text(document.publication_date if document else None),
        _sql_text(document.artifact_sha256 if document else None),
        _sql_integer(document.byte_size if document else None),
        str(summary.item_count),
        _sql_integer(summary.total_previous_centavos),
        _sql_integer(summary.total_senate_centavos),
        _sql_integer(summary.total_change_centavos),
        _sql_text(release.public_note),
    )
    return f"INSERT INTO senate_committee_releases VALUES ({', '.join(values)});"  # noqa: S608


def _change_values(release_id: str, item: CommitteeChange) -> tuple[str, ...]:
    return (
        _sql_text(item.change_id),
        _sql_text(release_id),
        _sql_text(item.group_code),
        _sql_text(item.origin_stage),
        _sql_text(item.source_project_id),
        _sql_text(item.title),
        _sql_text(item.project_type),
        _sql_text(item.region),
        _sql_text(item.province),
        _sql_text(item.city_or_municipality),
        _sql_text(item.district),
        str(item.previous_centavos),
        str(item.senate_centavos),
        str(item.change_centavos),
        _sql_text(item.reason),
        str(item.source_page),
        _sql_text(item.match_state),
        _sql_text(item.linked_project_slug),
        _sql_text(item.public_note),
    )


def _control_statement(release_id: str, control: ChangeControl) -> str:
    return (
        "INSERT INTO senate_committee_controls VALUES "  # noqa: S608
        f"({_sql_text(release_id)}, {_sql_text(control.group_code)}, "
        f"{_sql_text(control.label)}, {control.project_count}, {control.previous_centavos}, "
        f"{control.senate_centavos}, {control.change_centavos});"
    )


def _render_bundle(release: SenateCommitteeRelease) -> str:
    lines = [
        "DELETE FROM senate_committee_changes;",
        "DELETE FROM senate_committee_controls;",
        "DELETE FROM senate_committee_releases;",
        _release_statement(release),
    ]
    lines.extend(_control_statement(release.release_id, control) for control in release.controls)
    lines.extend(
        f"INSERT INTO senate_committee_changes VALUES ({', '.join(_change_values(release.release_id, item))});"  # noqa: S608
        for item in release.items
    )
    return "\n".join(lines) + "\n"


def _verify_bundle(sql: str, expected_items: int) -> None:
    database = sqlite3.connect(":memory:")
    database.execute("PRAGMA foreign_keys = ON")
    try:
        database.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        database.executescript(sql)
        releases = database.execute("SELECT COUNT(*) FROM senate_committee_releases").fetchone()[0]
        items = database.execute("SELECT COUNT(*) FROM senate_committee_changes").fetchone()[0]
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        database.close()
    if releases != 1 or items != expected_items or integrity != "ok":
        raise ValueError("Senate committee D1 bundle verification failed")


def build_senate_committee_bundle(
    release_path: Path, output_dir: Path
) -> SenateCommitteeBundleResult:
    """Validate, reconcile and atomically write the committee-stage D1 bundle."""

    payload = release_path.read_bytes()
    release = load_senate_committee_release(payload)
    summary = reconcile_senate_committee_release(release)
    sql = _render_bundle(release)
    _verify_bundle(sql, summary.item_count)
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle_path = building / "senate-committee.sql"
    bundle_path.write_text(sql, encoding="utf-8")
    source_sha256 = hashlib.sha256(payload).hexdigest()
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "release_id": release.release_id,
                "state": release.state,
                "item_count": summary.item_count,
                "source_sha256": source_sha256,
                "bundle_sha256": bundle_sha256,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return SenateCommitteeBundleResult(
        output_dir, release.state, summary.item_count, source_sha256, bundle_sha256
    )
