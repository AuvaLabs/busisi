import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.facility_status_bundle import build_facility_status_sql

MIGRATION = Path("cloudflare/busisi/migrations/0028_facility_registry_status.sql")
RESILIENCE_MIGRATION = Path("cloudflare/busisi/migrations/0030_facility_source_resilience.sql")


def _report() -> dict[str, object]:
    return {
        "checked_at": "2026-11-04T14:00:00+00:00",
        "source_url": "https://www.deped.gov.ph/wp-content/uploads/List-of-PSIP-III-Sites.xlsx",
        "source_state": "blocked",
        "release_state": "source_blocked",
        "http_status": 403,
        "source_artifact_sha256": None,
        "expected_facilities": 1095,
        "validated_facilities": 0,
        "candidate_links": 0,
        "reviewed_cases": 0,
        "precision_bps": None,
        "agreement_bps": None,
        "critical_failures": 0,
        "status_note": "The official source blocked unattended acquisition.",
        "failure_kind": "access_denied",
        "last_success_at": None,
        "consecutive_failures": 1,
        "next_check_at": "2026-11-04T20:00:00+00:00",
        "freshness_state": "unknown",
        "response_sha256": None,
        "source_version": "legacy-xlsx-1095",
        "candidate_source_url": (
            "https://www.deped.gov.ph/wp-content/uploads/"
            "Deped-Announcement-on-PPP-Indicative-List-of-Schools-Annex-A-2025-12-08_1.pdf"
        ),
        "candidate_state": "discovered_unarchived",
    }


def test_builds_replayable_facility_status_upsert() -> None:
    sql, digest = build_facility_status_sql(_report())
    database = sqlite3.connect(":memory:")
    database.executescript(MIGRATION.read_text())
    database.executescript(RESILIENCE_MIGRATION.read_text())
    database.executescript(sql)
    row = database.execute(
        "SELECT source_state, release_state, http_status, failure_kind, "
        "freshness_state, consecutive_failures, status_sha256 "
        "FROM facility_registry_status WHERE singleton_id = 1"
    ).fetchone()

    assert row == (
        "blocked",
        "source_blocked",
        403,
        "access_denied",
        "unknown",
        1,
        digest,
    )
    assert len(digest) == 64


def test_rejects_invalid_facility_status_shapes() -> None:
    for update in (
        {"checked_at": "today"},
        {"source_url": "https://example.test/list.xlsx"},
        {"source_state": "ready"},
        {"release_state": "open"},
        {"http_status": 999},
        {"validated_facilities": 1096},
        {"precision_bps": 10001},
        {"source_artifact_sha256": "short"},
        {"failure_kind": "mystery"},
        {"freshness_state": "new"},
        {"consecutive_failures": -1},
        {"next_check_at": "later"},
        {"response_sha256": "short"},
        {"source_version": "unknown"},
        {"candidate_source_url": "https://example.test/list.pdf"},
        {"candidate_state": "trusted"},
        {
            "source_state": "validated",
            "release_state": "source_blocked",
            "source_artifact_sha256": "a" * 64,
            "validated_facilities": 1095,
        },
        {
            "source_state": "validated",
            "release_state": "ready_for_publication",
            "source_artifact_sha256": "a" * 64,
            "validated_facilities": 1095,
        },
    ):
        with pytest.raises(ValueError, match="facility status"):
            build_facility_status_sql({**_report(), **update})


def test_status_digest_is_stable_for_equivalent_reports() -> None:
    first_sql, first_digest = build_facility_status_sql(_report())
    second_sql, second_digest = build_facility_status_sql(json.loads(json.dumps(_report())))

    assert first_digest == second_digest
    assert first_sql == second_sql
