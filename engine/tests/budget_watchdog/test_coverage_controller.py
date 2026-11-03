from __future__ import annotations

import json

import pytest

from engine.budget_watchdog.coverage_controller import (
    CoverageControllerState,
    CoverageCycleMetrics,
    advance_controller,
    load_controller,
    save_controller,
    should_halt_cycle,
)


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
