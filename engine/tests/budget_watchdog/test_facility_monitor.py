from datetime import UTC, datetime

from ops.harness.budget_watchdog_facility_monitor import (
    _validation_failure_report,
    facility_failure_report,
)

from engine.budget_watchdog.acquisition import AcquisitionError

NOW = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)


def test_expected_official_source_block_is_reported_without_false_publication() -> None:
    report, code = facility_failure_report(
        AcquisitionError("blocked", http_status=403),
        NOW,
    )

    assert code == 0
    assert report["source_state"] == "blocked"
    assert report["release_state"] == "source_blocked"
    assert report["http_status"] == 403
    assert report["validated_facilities"] == 0
    assert report["candidate_links"] == 0
    assert "blocked" in report["status_note"].casefold()


def test_publisher_maintenance_is_distinct_from_access_blocking() -> None:
    report, code = facility_failure_report(
        AcquisitionError(
            "maintenance",
            http_status=403,
            response_body=b'<img src="maintenance.png">',
        ),
        NOW,
    )

    assert code == 0
    assert report["source_state"] == "unavailable"
    assert report["release_state"] == "source_unavailable"
    assert report["failure_kind"] == "publisher_maintenance"
    assert report["freshness_state"] == "unknown"
    assert report["consecutive_failures"] == 1
    assert report["next_check_at"] == "2026-11-04T20:00:00+00:00"
    assert "maintenance" in report["status_note"].casefold()


def test_missing_or_failed_source_requires_operator_attention() -> None:
    missing, missing_code = facility_failure_report(
        AcquisitionError("missing", http_status=404),
        NOW,
    )
    unavailable, unavailable_code = facility_failure_report(
        AcquisitionError("network failure"),
        NOW,
    )

    assert missing_code == 2
    assert missing["source_state"] == "unavailable"
    assert missing["release_state"] == "source_unavailable"
    assert unavailable_code == 3
    assert unavailable["source_state"] == "acquisition_failure"
    assert unavailable["release_state"] == "acquisition_failed"


def test_validation_failure_preserves_prior_source_health() -> None:
    report = _validation_failure_report(
        ValueError("schema changed"),
        NOW,
        {
            "last_success_at": "2026-11-04T08:00:00+00:00",
            "consecutive_failures": 1,
        },
    )

    assert report["failure_kind"] == "validation_error"
    assert report["last_success_at"] == "2026-11-04T08:00:00+00:00"
    assert report["consecutive_failures"] == 2
    assert report["freshness_state"] == "degraded"
