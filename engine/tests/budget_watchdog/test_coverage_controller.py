from __future__ import annotations

import json

import pytest
from ops.harness import budget_watchdog_project_image_automation as automation
from ops.harness.budget_watchdog_project_image_automation import (
    _metrics,
    _recheck_limit,
    run_cycle,
)

from engine.budget_watchdog.coverage_controller import (
    CoverageControllerState,
    CoverageCycleMetrics,
    advance_controller,
    load_controller,
    save_controller,
    should_halt_cycle,
)
from engine.budget_watchdog.project_image_runner import ProjectImageBatchResult


def test_controller_ramps_to_two_thousand_after_eight_healthy_cycles() -> None:
    state = CoverageControllerState.initial()
    metrics = CoverageCycleMetrics(claimed=1000, failures=0, rate_limited=0)

    for _ in range(8):
        state = advance_controller(state, metrics)

    assert state.healthy_streak == 8
    assert state.batch_limit == 2000
    assert state.workers == 4


def test_controller_reduces_load_after_rate_limit_and_recovers_workers() -> None:
    state = CoverageControllerState.initial()
    limited = CoverageCycleMetrics(claimed=25, failures=2, rate_limited=2)

    reduced = advance_controller(state, limited)

    assert reduced.healthy_streak == 0
    assert reduced.batch_limit == 500
    assert reduced.workers == 2
    recovered = advance_controller(
        reduced, CoverageCycleMetrics(claimed=500, failures=0, rate_limited=0)
    )
    assert recovered.workers == 3
    assert recovered.batch_limit == 1000


def test_cycle_halts_on_repeated_rate_limits_or_ten_percent_failures() -> None:
    assert should_halt_cycle(CoverageCycleMetrics(25, 0, 2))
    assert should_halt_cycle(CoverageCycleMetrics(100, 11, 0))
    assert not should_halt_cycle(CoverageCycleMetrics(100, 10, 0))
    assert not should_halt_cycle(CoverageCycleMetrics(9, 9, 0))


def test_controller_state_round_trips_atomically(tmp_path) -> None:
    path = tmp_path / "state" / "controller.json"
    assert load_controller(path) == CoverageControllerState.initial()
    state = CoverageControllerState(1, 4, 500, 2)

    save_controller(path, state)

    assert load_controller(path) == state
    assert not path.with_suffix(".building").exists()


@pytest.mark.parametrize(
    "value",
    [
        {"schema_version": 2, "healthy_streak": 0, "batch_limit": 1000, "workers": 4},
        {"schema_version": 1, "healthy_streak": -1, "batch_limit": 1000, "workers": 4},
        {"schema_version": 1, "healthy_streak": 0, "batch_limit": 100, "workers": 4},
        {"schema_version": 1, "healthy_streak": 0, "batch_limit": 1000, "workers": 5},
    ],
)
def test_controller_rejects_invalid_persisted_state(tmp_path, value) -> None:
    path = tmp_path / "controller.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid"):
        load_controller(path)


def test_automation_controller_uses_every_health_failure() -> None:
    batch = ProjectImageBatchResult(
        claimed=25,
        verified_exact=0,
        no_images=0,
        count_conflict=0,
        retry=0,
        blocked=10,
        images_archived=0,
        rate_limited=0,
        source_failure=10,
        server_failure=0,
        validation_failure=0,
        controller_failures=10,
    )

    metrics = _metrics(batch)

    assert metrics.failures == 10
    assert should_halt_cycle(metrics)


def test_rechecks_never_consume_more_than_half_of_a_cycle() -> None:
    assert _recheck_limit(1) == 0
    assert _recheck_limit(25) == 6
    assert _recheck_limit(1_000) == 250


def test_coverage_cycle_defers_cleanly_when_an_audit_owns_the_lock(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "cycle.lock"
    monkeypatch.setattr(automation, "LOCK", lock_path)

    def busy(_file, _mode) -> None:
        raise BlockingIOError("operational audit owns the lock")

    monkeypatch.setattr(automation.fcntl, "flock", busy)

    result = run_cycle(limit=1, workers=1, publish=True)

    assert result == {
        "passed": True,
        "deferred": True,
        "reason": "another Busisi maintenance cycle is running",
    }
