"""Deterministic source-failure classification, freshness, and retry state."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

REGULAR_CHECK_DELAY = timedelta(hours=6)
DEGRADED_AFTER = timedelta(hours=24)
FAILURE_DELAYS = (timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_MIN = 500

_MAINTENANCE_MARKERS = (
    b"maintenance.png",
    b"site is under maintenance",
    b"temporarily down for maintenance",
)
_CHALLENGE_MARKERS = (
    b"just a moment",
    b"performing security verification",
    b"enable javascript and cookies",
    b"sorry, you have been blocked",
    b"cdn-cgi/challenge-platform",
    b"cf-chl-",
    b"captcha",
)


def classify_source_failure(status: int | None, response_body: bytes) -> str:
    """Classify an unavailable source without treating its response as evidence."""

    lowered = response_body[:65_536].lower()
    if any(marker in lowered for marker in _MAINTENANCE_MARKERS):
        return "publisher_maintenance"
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        return "bot_challenge"
    failure_kind = "unexpected_response"
    if status == HTTP_TOO_MANY_REQUESTS:
        failure_kind = "rate_limited"
    elif status in {404, 410}:
        failure_kind = "not_found"
    elif status is not None and status >= HTTP_SERVER_ERROR_MIN:
        failure_kind = "server_error"
    elif status in {401, 403}:
        failure_kind = "access_denied"
    elif status is None:
        failure_kind = "transport_error"
    return failure_kind


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _digest(response_body: bytes) -> str | None:
    return hashlib.sha256(response_body).hexdigest() if response_body else None


def _freshness(checked_at: datetime, last_success_at: datetime | None) -> str:
    if last_success_at is None:
        return "unknown"
    return "degraded" if checked_at - last_success_at <= DEGRADED_AFTER else "stale"


def source_health_after_failure(
    previous: dict[str, Any] | None,
    *,
    checked_at: datetime,
    failure_kind: str,
    response_body: bytes = b"",
    baseline_last_success_at: str | None = None,
    retry_delays: tuple[timedelta, ...] = FAILURE_DELAYS,
) -> dict[str, Any]:
    """Advance persistent health state after one failed source check."""

    prior = previous or {}
    previous_count = prior.get("consecutive_failures", 0)
    count = previous_count + 1 if isinstance(previous_count, int) else 1
    last_success = _timestamp(prior.get("last_success_at")) or _timestamp(baseline_last_success_at)
    if not retry_delays:
        raise ValueError("retry delays must not be empty")
    delay = retry_delays[min(count - 1, len(retry_delays) - 1)]
    return {
        "failure_kind": failure_kind,
        "last_success_at": last_success.isoformat() if last_success else None,
        "consecutive_failures": count,
        "next_check_at": (checked_at + delay).isoformat(),
        "freshness_state": _freshness(checked_at, last_success),
        "response_sha256": _digest(response_body),
    }


def source_health_after_success(
    checked_at: datetime,
    *,
    response_body: bytes = b"",
) -> dict[str, Any]:
    """Reset persistent health state after a validated source check."""

    return {
        "failure_kind": None,
        "last_success_at": checked_at.isoformat(),
        "consecutive_failures": 0,
        "next_check_at": (checked_at + REGULAR_CHECK_DELAY).isoformat(),
        "freshness_state": "fresh",
        "response_sha256": _digest(response_body),
    }


def source_check_due(previous: dict[str, Any] | None, *, at: datetime) -> bool:
    """Return whether a scheduled monitor may make its next source request."""

    if previous is None:
        return True
    next_check = _timestamp(previous.get("next_check_at"))
    return next_check is None or at >= next_check
