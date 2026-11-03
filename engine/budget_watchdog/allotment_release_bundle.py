"""Build a verified D1 publication bundle for official allotment releases."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.allotment_releases import (
    AS_OF_DATE,
    FISCAL_YEAR,
    AllotmentReleaseControls,
    AllotmentReleaseRecord,
    parse_release_rows,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0020_allotment_releases.sql"
)


@dataclass(frozen=True, slots=True)
class AllotmentReleaseBundleResult:
    output_dir: Path
    record_count: int
    department_count: int
    attached_count: int
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_value(value: str | int | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return _sql_text(value)


def _statement(record: AllotmentReleaseRecord) -> str:
    values: tuple[str | int | None, ...] = (
        record.record_id,
        record.fiscal_year,
        record.as_of_date,
        record.source_row,
        record.level,
        record.parent_id,
        record.code,
        record.name,
        record.program_centavos,
        record.adjustment_centavos,
        record.adjusted_program_centavos,
        record.release_centavos,
        record.balance_centavos,
        record.release_bps,
        record.source_url,
        record.source_sha256,
        "DBM workbook values are published in thousand pesos and normalized to centavos.",
    )
    return f"INSERT INTO allotment_release_items VALUES ({', '.join(_sql_value(value) for value in values)});"  # noqa: S608


def _metadata(
    records: tuple[AllotmentReleaseRecord, ...], controls: AllotmentReleaseControls
) -> dict[str, str]:
    return {
        "fiscal_year": str(FISCAL_YEAR),
        "as_of_date": AS_OF_DATE,
        "record_count": str(len(records)),
        "department_count": str(sum(record.level == "department" for record in records)),
        "attached_agency_count": str(
            sum(record.level in {"attached_agency", "subunit"} for record in records)
        ),
        "special_purpose_fund_count": str(
            sum(record.level == "special_purpose_fund" for record in records)
        ),
        "current_gaa_adjusted_centavos": str(controls.current_gaa_adjusted_centavos),
        "current_gaa_releases_centavos": str(controls.current_gaa_releases_centavos),
        "current_gaa_balance_centavos": str(controls.current_gaa_balance_centavos),
        "total_program_centavos": str(controls.total_program_centavos),
        "total_releases_centavos": str(controls.total_releases_centavos),
        "total_balance_centavos": str(controls.total_balance_centavos),
        "source_sha256": records[0].source_sha256,
        "source_url": records[0].source_url,
    }


def _load_snapshot(
    snapshot_dir: Path,
) -> tuple[tuple[AllotmentReleaseRecord, ...], AllotmentReleaseControls, dict[str, Any]]:
    manifest_path = snapshot_dir / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("fiscal_year") != FISCAL_YEAR or manifest.get("as_of_date") != AS_OF_DATE:
        raise ValueError("allotment-release snapshot fiscal boundary is invalid")
    rows_path = snapshot_dir / str(manifest.get("rows_path", ""))
    if not rows_path.is_file():
        raise ValueError("allotment-release rows are unavailable")
    rows_digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    if rows_digest != manifest.get("rows_sha256"):
        raise ValueError("allotment-release rows digest mismatch")
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("allotment-release rows must be a JSON array of objects")
    records, controls = parse_release_rows(
        tuple(payload), str(manifest.get("source_url", "")), str(manifest.get("source_sha256", ""))
    )
    return records, controls, manifest


def _verify(sql_path: Path, expected_records: int) -> None:
    database = sqlite3.connect(":memory:")
    try:
        database.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        database.executescript(sql_path.read_text(encoding="utf-8"))
        actual = database.execute("SELECT COUNT(*) FROM allotment_release_items").fetchone()[0]
        metadata = database.execute(
            "SELECT value FROM allotment_release_metadata WHERE key = 'record_count'"
        ).fetchone()
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        database.close()
    if actual != expected_records or metadata != (str(expected_records),) or integrity != "ok":
        raise ValueError("allotment-release D1 bundle verification failed")


def build_allotment_release_bundle(
    snapshot_dir: Path, output_dir: Path
) -> AllotmentReleaseBundleResult:
    records, controls, source_manifest = _load_snapshot(snapshot_dir)
    metadata = _metadata(records, controls)
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    sql_path = building / "allotment-releases.sql"
    lines = ["DELETE FROM allotment_release_items;", "DELETE FROM allotment_release_metadata;"]
    lines.extend(
        f"INSERT INTO allotment_release_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    lines.extend(_statement(record) for record in records)
    sql_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _verify(sql_path, len(records))
    manifest = {
        **metadata,
        "source_manifest_sha256": hashlib.sha256(
            (snapshot_dir / "snapshot-manifest.json").read_bytes()
        ).hexdigest(),
        "source_retrieved_at": source_manifest.get("retrieved_at"),
        "sql_sha256": hashlib.sha256(sql_path.read_bytes()).hexdigest(),
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    department_count = sum(record.level == "department" for record in records)
    attached_count = sum(
        record.level in {"attached_agency", "subunit"} for record in records
    )
    return AllotmentReleaseBundleResult(
        output_dir, len(records), department_count, attached_count, manifest_sha256
    )
