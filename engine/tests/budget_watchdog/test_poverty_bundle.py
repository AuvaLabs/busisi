import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.poverty_bundle import build_poverty_release_sql
from engine.budget_watchdog.poverty_estimates import PSA_POVERTY_SOURCE_URL, PovertyEstimate


def _record(code: str, name: str, incidence: int, row: int) -> PovertyEstimate:
    return PovertyEstimate(
        code,
        name,
        incidence,
        100,
        500,
        max(0, incidence - 200),
        min(10_000, incidence + 200),
        row,
        PSA_POVERTY_SOURCE_URL,
        "a" * 64,
    )


def _report() -> dict[str, object]:
    return {
        "checked_at": "2026-11-16T08:00:00+00:00",
        "source_url": PSA_POVERTY_SOURCE_URL,
        "source_state": "validated",
        "publication_state": "ready_for_review",
        "http_status": None,
        "source_sha256": "a" * 64,
        "expected_records": 2,
        "validated_records": 2,
        "failure_kind": None,
        "last_success_at": "2026-11-16T08:00:00+00:00",
        "consecutive_failures": 0,
        "next_check_at": "2026-11-16T14:00:00+00:00",
        "freshness_state": "fresh",
        "response_sha256": "a" * 64,
        "status_note": "The official PSA workbook passed all required checks.",
    }


def test_builds_one_atomic_checked_release() -> None:
    records = (
        _record("0102801000", "Adams", 1_550, 2),
        _record("0972015000", "Siayan", 6_780, 3),
    )

    sql, digest = build_poverty_release_sql(records, _report())

    assert len(digest) == 64
    connection = sqlite3.connect(":memory:")
    try:
        migration = Path(__file__).resolve().parents[3] / (
            "cloudflare/busisi/migrations/0033_community_poverty.sql"
        )
        connection.executescript(migration.read_text())
        connection.executescript(sql)
        assert (
            connection.execute("SELECT COUNT(*) FROM community_poverty_estimates").fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT poverty_incidence_bps FROM community_poverty_estimates WHERE psgc_code = '0972015000'"
            ).fetchone()[0]
            == 6_780
        )
        assert (
            connection.execute("SELECT publication_state FROM community_poverty_status").fetchone()[
                0
            ]
            == "ready_for_review"
        )
    finally:
        connection.close()


def test_rejects_release_rows_that_do_not_match_the_validated_status() -> None:
    report = _report()
    report["validated_records"] = 2

    with pytest.raises(ValueError, match="row count"):
        build_poverty_release_sql((_record("0102801000", "Adams", 1_550, 2),), report)
