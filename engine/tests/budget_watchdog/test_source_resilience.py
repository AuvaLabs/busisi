from datetime import UTC, datetime

from engine.budget_watchdog.source_resilience import (
    classify_source_failure,
    source_check_due,
    source_health_after_failure,
    source_health_after_success,
)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def test_classifies_observed_publisher_and_challenge_responses() -> None:
    assert classify_source_failure(403, b'<img src="maintenance.png">') == ("publisher_maintenance")
    assert (
        classify_source_failure(
            200,
            b"Performing security verification. Enable JavaScript and cookies. cdn-cgi/challenge-platform",
        )
        == "bot_challenge"
    )
    assert classify_source_failure(429, b"") == "rate_limited"
    assert classify_source_failure(503, b"") == "server_error"
    assert classify_source_failure(None, b"") == "transport_error"


def test_failure_health_uses_bounded_backoff_and_preserves_last_success() -> None:
    previous = {
        "last_success_at": "2026-11-09T08:00:00+00:00",
        "consecutive_failures": 1,
    }

    health = source_health_after_failure(
        previous,
        checked_at=NOW,
        failure_kind="bot_challenge",
        response_body=b"challenge",
    )

    assert health == {
        "failure_kind": "bot_challenge",
        "last_success_at": "2026-11-09T08:00:00+00:00",
        "consecutive_failures": 2,
        "next_check_at": "2026-11-09T14:00:00+00:00",
        "freshness_state": "degraded",
        "response_sha256": ("2dd00bd77e0222ced882665481a9c1d9f907309d16e05ed007a1ea63928477a9"),
    }


def test_failure_health_becomes_stale_and_caps_retry_delay() -> None:
    health = source_health_after_failure(
        {
            "last_success_at": "2026-11-07T08:00:00+00:00",
            "consecutive_failures": 7,
        },
        checked_at=NOW,
        failure_kind="publisher_maintenance",
        response_body=b"maintenance",
    )

    assert health["freshness_state"] == "stale"
    assert health["consecutive_failures"] == 8
    assert health["next_check_at"] == "2026-11-09T18:00:00+00:00"


def test_success_health_resets_failures_and_records_next_regular_check() -> None:
    health = source_health_after_success(NOW, response_body=b"official bytes")

    assert health["failure_kind"] is None
    assert health["last_success_at"] == NOW.isoformat()
    assert health["consecutive_failures"] == 0
    assert health["next_check_at"] == "2026-11-09T18:00:00+00:00"
    assert health["freshness_state"] == "fresh"
    assert len(health["response_sha256"]) == 64


def test_source_check_due_honors_persisted_retry_time() -> None:
    state = {"next_check_at": "2026-11-09T14:00:00+00:00"}

    assert source_check_due(state, at=NOW) is False
    assert source_check_due(state, at=datetime(2026, 11, 9, 14, 0, tzinfo=UTC)) is True
    assert source_check_due({"next_check_at": "invalid"}, at=NOW) is True
