"""Pure operational invariants for the unattended Busisi evidence pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

_QUEUE_STALE_AFTER = timedelta(hours=36)
_SOURCE_STALE_AFTER = timedelta(hours=8)
_TIMER_MAX_DELAY = timedelta(hours=26)


@dataclass(frozen=True, slots=True)
class OperationalFacts:
    queue_total: int
    queue_statuses: dict[str, int]
    expired_leases: int
    latest_queue_update: datetime | None
    release_completed: int
    publication_marker_exists: bool
    source_monitor_checked_at: datetime | None
    source_monitor_passed: bool
    timer_states: dict[str, tuple[str, datetime | None]]


def audit_operational_facts(facts: OperationalFacts, *, now: datetime) -> tuple[str, ...]:
    """Return every invariant failure without mutating operational state."""
    if now.tzinfo is None:
        raise ValueError("operational audit time must be timezone-aware")
    issues: list[str] = []
    if sum(facts.queue_statuses.values()) != facts.queue_total:
        issues.append("queue status counts do not reconcile")
    if facts.expired_leases:
        issues.append("queue has expired in-progress leases")
    if facts.latest_queue_update is None or now - facts.latest_queue_update > _QUEUE_STALE_AFTER:
        issues.append("queue has not recorded progress within 36 hours")
    completed = sum(
        facts.queue_statuses.get(state, 0)
        for state in ("verified_exact", "no_images", "count_conflict")
    )
    if facts.release_completed > completed:
        issues.append("public release exceeds completed private queue evidence")
    if not facts.publication_marker_exists:
        issues.append("latest public release has no successful publication marker")
    if not facts.source_monitor_passed:
        issues.append("latest source monitor did not pass")
    if (
        facts.source_monitor_checked_at is None
        or now - facts.source_monitor_checked_at > _SOURCE_STALE_AFTER
    ):
        issues.append("source monitor evidence is older than 8 hours")
    for timer in (
        "busisi-project-image-coverage.timer",
        "busisi-acquisition-retry.timer",
    ):
        state, next_run = facts.timer_states.get(timer, ("missing", None))
        if state != "active":
            issues.append(f"{timer} is not active")
        elif next_run is None or next_run - now > _TIMER_MAX_DELAY:
            issues.append(f"{timer} next run is too far away")
    return tuple(issues)
