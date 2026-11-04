"""Build and locally verify the contractor accountability D1 bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.contractor_accountability import AccountabilitySnapshot

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0029_contractor_accountability.sql"
)


@dataclass(frozen=True, slots=True)
class AccountabilityBundleResult:
    output_dir: Path
    blacklist_events: int
    cpes_events: int
    award_signals: int
    manifest_sha256: str


def _sql(value: str | int | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return f"'{value.replace("'", "''")}'"


def _values(values: tuple[str | int | None, ...]) -> str:
    return ", ".join(_sql(value) for value in values)


def _blacklist_sql(snapshot: AccountabilitySnapshot) -> list[str]:
    return [
        "INSERT INTO contractor_blacklist_events VALUES "  # noqa: S608
        + f"({_values((item.order_id, item.contractor_key, item.contractor_name, item.pcab_id, item.reported_name, item.identity_state, item.procuring_entity, item.project_title, item.start_date, item.end_date, item.status, item.source_sha256))});"
        for item in snapshot.blacklist_events
    ]


def _cpes_sql(snapshot: AccountabilitySnapshot) -> list[str]:
    return [
        "INSERT INTO contractor_cpes_events VALUES "  # noqa: S608
        + f"({_values((item.rating_id, item.contractor_key, item.contractor_name, item.pcab_id, item.reported_name, item.identity_state, item.project_title, item.evaluation_date, item.implementing_agency, item.visit_rating_bps, item.final_rating_bps, item.qualitative_rating, item.page_number, item.release_label, item.source_sha256, item.source_url))});"
        for item in snapshot.cpes_events
    ]


def _signal_sql(snapshot: AccountabilitySnapshot) -> list[str]:
    return [
        "INSERT INTO contractor_award_timing_signals VALUES "  # noqa: S608
        + f"({_values((item.signal_id, item.signal_type, item.contractor_key, item.contractor_name, item.pcab_id, item.evidence_event_id, item.contract_id, item.relationship, item.match_basis, item.awardee_name, item.award_date, item.contract_amount_centavos, item.award_row_sha256))});"
        for item in snapshot.award_signals
    ]


def _metadata(snapshot: AccountabilitySnapshot) -> dict[str, str]:
    active = sum(item.status == "active" for item in snapshot.blacklist_events)
    return {
        "award_signals": str(len(snapshot.award_signals)),
        "award_source_revision": snapshot.award_source_revision,
        "award_source_sha256": snapshot.award_source_sha256,
        "blacklist_active": str(active),
        "blacklist_events": str(len(snapshot.blacklist_events)),
        "blacklist_index_sha256": json.dumps(snapshot.blacklist_index_sha256),
        "checked_on": snapshot.checked_on,
        "cpes_events": str(len(snapshot.cpes_events)),
        "schema_version": "1",
        **{key: str(value) for key, value in snapshot.quarantine_counts.items()},
    }


def _validate_relationships(snapshot: AccountabilitySnapshot) -> None:
    blacklists = {item.order_id: item for item in snapshot.blacklist_events}
    ratings = {item.rating_id: item for item in snapshot.cpes_events}
    if len(blacklists) != len(snapshot.blacklist_events) or len(ratings) != len(
        snapshot.cpes_events
    ):
        raise ValueError("accountability event identifiers must be unique")
    for signal in snapshot.award_signals:
        events = blacklists if signal.signal_type == "award_during_blacklist" else ratings
        event = events.get(signal.evidence_event_id)
        if event is None or event.contractor_key != signal.contractor_key:
            raise ValueError("accountability award signal has no matching evidence event")


def _document(snapshot: AccountabilitySnapshot) -> str:
    lines = [
        "DELETE FROM contractor_award_timing_signals;",
        "DELETE FROM contractor_cpes_events;",
        "DELETE FROM contractor_blacklist_events;",
        "DELETE FROM accountability_metadata;",
    ]
    lines.extend(
        f"INSERT INTO accountability_metadata VALUES ({_values((key, value))});"  # noqa: S608
        for key, value in sorted(_metadata(snapshot).items())
    )
    lines.extend(_blacklist_sql(snapshot))
    lines.extend(_cpes_sql(snapshot))
    lines.extend(_signal_sql(snapshot))
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: tuple[int, int, int]) -> None:
    with sqlite3.connect(":memory:") as database:
        database.executescript(MIGRATION.read_text(encoding="utf-8"))
        database.executescript(sql)
        actual = tuple(
            database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "contractor_blacklist_events",
                "contractor_cpes_events",
                "contractor_award_timing_signals",
            )
        )
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    if actual != expected or integrity != "ok":
        raise ValueError("contractor accountability bundle verification failed")


def _manifest(snapshot: AccountabilitySnapshot, sql_sha256: str) -> dict[str, Any]:
    return {
        **_metadata(snapshot),
        "blacklist_events": len(snapshot.blacklist_events),
        "cpes_events": len(snapshot.cpes_events),
        "award_signals": len(snapshot.award_signals),
        "quarantine_counts": snapshot.quarantine_counts,
        "sql_sha256": sql_sha256,
    }


def build_accountability_bundle(
    snapshot: AccountabilitySnapshot, output_dir: Path
) -> AccountabilityBundleResult:
    """Create deterministic public SQL while retaining only quarantine totals."""

    _validate_relationships(snapshot)
    sql = _document(snapshot)
    expected = (
        len(snapshot.blacklist_events),
        len(snapshot.cpes_events),
        len(snapshot.award_signals),
    )
    _verify(sql, expected)
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    sql_path = building / "contractor-accountability.sql"
    sql_path.write_text(sql, encoding="utf-8")
    manifest = _manifest(snapshot, hashlib.sha256(sql.encode()).hexdigest())
    manifest_path = building / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return AccountabilityBundleResult(output_dir, *expected, digest)
