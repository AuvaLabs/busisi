"""Build an atomic D1 release from checked PSA poverty estimates."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from engine.budget_watchdog.poverty_estimates import PovertyEstimate
from engine.budget_watchdog.poverty_status_bundle import build_poverty_status_sql

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0033_community_poverty.sql"
)


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _record_sql(record: PovertyEstimate) -> str:
    values = (
        _sql_text(record.psgc_code),
        _sql_text(record.name),
        "2023",
        str(record.poverty_incidence_bps),
        str(record.standard_error_bps),
        str(record.coefficient_variation_bps),
        str(record.confidence_lower_bps),
        str(record.confidence_upper_bps),
        str(record.source_row),
        _sql_text(record.source_url),
        _sql_text(record.source_sha256),
    )
    return f"INSERT INTO community_poverty_estimates VALUES ({', '.join(values)});"  # noqa: S608


def _validate_records(records: tuple[PovertyEstimate, ...], report: dict[str, Any]) -> None:
    validated = report.get("validated_records")
    if not isinstance(validated, int) or len(records) != validated:
        raise ValueError("poverty release row count does not match the validated status")
    if len({record.psgc_code for record in records}) != len(records):
        raise ValueError("poverty release PSGC identities are duplicated")
    source_sha256 = report.get("source_sha256")
    if any(record.source_sha256 != source_sha256 for record in records):
        raise ValueError("poverty release rows do not match the checked source")


def _verify(sql: str, expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))
        connection.executescript(sql)
        count = connection.execute("SELECT COUNT(*) FROM community_poverty_estimates").fetchone()[0]
        status = connection.execute(
            "SELECT validated_records FROM community_poverty_status WHERE singleton_id = 1"
        ).fetchone()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if count != expected or status != (expected,) or integrity != "ok":
        raise ValueError("poverty D1 release verification failed")


def build_poverty_release_sql(
    records: tuple[PovertyEstimate, ...], report: dict[str, Any]
) -> tuple[str, str]:
    """Return a verified replace-all SQL release and its SHA-256 digest."""

    _validate_records(records, report)
    status_sql, _ = build_poverty_status_sql(report)
    rows = "\n".join(_record_sql(record) for record in records)
    sql = f"DELETE FROM community_poverty_estimates;\n{status_sql}{rows}\n"  # noqa: S608
    _verify(sql, len(records))
    return sql, hashlib.sha256(sql.encode()).hexdigest()
