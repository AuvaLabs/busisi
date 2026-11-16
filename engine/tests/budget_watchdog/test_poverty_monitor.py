from datetime import UTC, datetime

from ops.harness.budget_watchdog_poverty_monitor import (
    _validation_failure_report,
    poverty_failure_report,
)

from engine.budget_watchdog.acquisition import AcquisitionError

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


def test_bot_challenge_is_reported_without_publishing_estimates() -> None:
    report, code = poverty_failure_report(
        AcquisitionError(
            "blocked",
            http_status=403,
            response_body=b"<title>Just a moment...</title>",
        ),
        NOW,
    )

    assert code == 0
    assert report["source_state"] == "blocked"
    assert report["publication_state"] == "not_published"
    assert report["failure_kind"] == "bot_challenge"
    assert report["validated_records"] == 0
    assert report["next_check_at"] == "2026-11-16T14:00:00+00:00"
    assert "No poverty estimates were published" in report["status_note"]


def test_validation_failure_stays_unpublished_and_preserves_health() -> None:
    report = _validation_failure_report(
        ValueError("schema changed"),
        NOW,
        {
            "last_success_at": "2026-11-16T02:00:00+00:00",
            "consecutive_failures": 1,
        },
    )

    assert report["source_state"] == "validation_failure"
    assert report["publication_state"] == "not_published"
    assert report["failure_kind"] == "validation_error"
    assert report["last_success_at"] == "2026-11-16T02:00:00+00:00"
    assert report["consecutive_failures"] == 2
