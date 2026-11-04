from __future__ import annotations

from datetime import UTC, datetime, timedelta

from engine.budget_watchdog.operations_audit import (
    OperationalFacts,
    audit_operational_facts,
)

NOW = datetime(2026, 11, 4, tzinfo=UTC)


def _facts(**updates: object) -> OperationalFacts:
    values = {
        "queue_total": 100,
        "queue_statuses": {"pending": 90, "verified_exact": 5, "no_images": 3, "count_conflict": 2},
        "expired_leases": 0,
        "latest_queue_update": NOW - timedelta(hours=2),
        "release_completed": 10,
        "publication_marker_exists": True,
        "source_monitor_checked_at": NOW - timedelta(hours=2),
        "source_monitor_passed": True,
        "timer_states": {
            "busisi-project-image-coverage.timer": ("active", NOW + timedelta(hours=3)),
            "busisi-acquisition-retry.timer": ("active", NOW + timedelta(hours=4)),
            "busisi-weekly-coverage-audit.timer": ("active", NOW + timedelta(days=5)),
            "busisi-monthly-reconciliation.timer": ("active", NOW + timedelta(days=20)),
        },
    }
    values.update(updates)
    return OperationalFacts(**values)  # type: ignore[arg-type]


def test_accepts_a_current_reconciled_operational_state() -> None:
    assert audit_operational_facts(_facts(), now=NOW) == ()


def test_reports_each_fail_closed_operational_gap() -> None:
    facts = _facts(
        queue_statuses={"pending": 80, "verified_exact": 5},
        expired_leases=2,
        latest_queue_update=NOW - timedelta(hours=40),
        release_completed=12,
        publication_marker_exists=False,
        source_monitor_checked_at=NOW - timedelta(hours=10),
        source_monitor_passed=False,
        timer_states={
            "busisi-project-image-coverage.timer": ("failed", None),
            "busisi-acquisition-retry.timer": ("active", NOW + timedelta(hours=30)),
            "busisi-weekly-coverage-audit.timer": ("missing", None),
            "busisi-monthly-reconciliation.timer": ("active", NOW + timedelta(days=40)),
        },
    )

    issues = audit_operational_facts(facts, now=NOW)

    assert "queue status counts do not reconcile" in issues
    assert "queue has expired in-progress leases" in issues
    assert "queue has not recorded progress within 36 hours" in issues
    assert "public release exceeds completed private queue evidence" in issues
    assert "latest public release has no successful publication marker" in issues
    assert "latest source monitor did not pass" in issues
    assert "source monitor evidence is older than 8 hours" in issues
    assert any("project-image-coverage.timer is not active" in item for item in issues)
    assert any("acquisition-retry.timer next run is too far away" in item for item in issues)
    assert any("weekly-coverage-audit.timer is not active" in item for item in issues)
    assert any("monthly-reconciliation.timer next run is too far away" in item for item in issues)
