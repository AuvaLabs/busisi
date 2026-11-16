import json
import sqlite3
from datetime import UTC, datetime

import pytest

from engine.budget_watchdog.poverty_status_bundle import build_poverty_status_sql


def _report() -> dict[str, object]:
    return {
        "checked_at": datetime(2026, 11, 16, 8, 0, tzinfo=UTC).isoformat(),
        "source_url": "https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx",
        "source_state": "blocked",
        "publication_state": "not_published",
        "http_status": 403,
        "source_sha256": None,
        "expected_records": 1611,
        "validated_records": 0,
        "failure_kind": "bot_challenge",
        "last_success_at": None,
        "consecutive_failures": 1,
        "next_check_at": "2026-11-16T14:00:00+00:00",
        "freshness_state": "unknown",
        "response_sha256": "a" * 64,
        "status_note": "PSA blocked the automatic download. No poverty estimates were published.",
    }


def test_builds_checked_sql_for_a_blocked_source() -> None:
    sql, digest = build_poverty_status_sql(_report())

    assert len(digest) == 64
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE community_poverty_status (
              singleton_id INTEGER PRIMARY KEY,
              checked_at TEXT NOT NULL, source_url TEXT NOT NULL,
              source_state TEXT NOT NULL, publication_state TEXT NOT NULL,
              http_status INTEGER, source_sha256 TEXT,
              expected_records INTEGER NOT NULL, validated_records INTEGER NOT NULL,
              failure_kind TEXT, last_success_at TEXT,
              consecutive_failures INTEGER NOT NULL, next_check_at TEXT,
              freshness_state TEXT NOT NULL, response_sha256 TEXT,
              status_note TEXT NOT NULL, status_sha256 TEXT NOT NULL
            );
            """
        )
        connection.executescript(sql)
        row = connection.execute(
            "SELECT source_state, validated_records, status_sha256 FROM community_poverty_status"
        ).fetchone()
    finally:
        connection.close()
    assert row == ("blocked", 0, digest)


def test_rejects_a_failed_source_that_claims_validated_rows() -> None:
    report = _report()
    report["validated_records"] = 1

    with pytest.raises(ValueError, match="failed source"):
        build_poverty_status_sql(report)


def test_status_digest_is_stable_for_the_same_report() -> None:
    first_sql, first_digest = build_poverty_status_sql(_report())
    second_sql, second_digest = build_poverty_status_sql(json.loads(json.dumps(_report())))

    assert first_sql == second_sql
    assert first_digest == second_digest
