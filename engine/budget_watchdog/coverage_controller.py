"""Adaptive safety controller for project-image coverage expansion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

INITIAL_BATCH_LIMIT = 1000
MAX_BATCH_LIMIT = 2000
MIN_BATCH_LIMIT = 250
INITIAL_WORKERS = 4
MAX_WORKERS = 4
HEALTHY_CYCLES_TO_RAMP = 8
HEALTHY_FAILURE_RATIO = 0.02
HALT_FAILURE_RATIO = 0.10
HALT_FAILURE_MINIMUM = 10
HALT_RATE_LIMITS = 2


@dataclass(frozen=True, slots=True)
class CoverageControllerState:
    schema_version: int
    healthy_streak: int
    batch_limit: int
    workers: int

    @classmethod
    def initial(cls) -> CoverageControllerState:
        return cls(1, 0, INITIAL_BATCH_LIMIT, INITIAL_WORKERS)


@dataclass(frozen=True, slots=True)
class CoverageCycleMetrics:
    claimed: int
    failures: int
    rate_limited: int

    @property
    def failure_ratio(self) -> float:
        return self.failures / self.claimed if self.claimed else 0.0


def should_halt_cycle(metrics: CoverageCycleMetrics) -> bool:
    if metrics.rate_limited >= HALT_RATE_LIMITS:
        return True
    return metrics.claimed >= HALT_FAILURE_MINIMUM and metrics.failure_ratio > HALT_FAILURE_RATIO


def advance_controller(
    state: CoverageControllerState, metrics: CoverageCycleMetrics
) -> CoverageControllerState:
    healthy = (
        metrics.claimed > 0
        and metrics.rate_limited == 0
        and metrics.failure_ratio <= HEALTHY_FAILURE_RATIO
    )
    if healthy:
        streak = state.healthy_streak + 1
        recovered_limit = min(
            INITIAL_BATCH_LIMIT,
            max(state.batch_limit, state.batch_limit * 2),
        )
        batch_limit = MAX_BATCH_LIMIT if streak >= HEALTHY_CYCLES_TO_RAMP else recovered_limit
        return CoverageControllerState(
            schema_version=1,
            healthy_streak=streak,
            batch_limit=batch_limit,
            workers=min(MAX_WORKERS, state.workers + 1),
        )
    return CoverageControllerState(
        schema_version=1,
        healthy_streak=0,
        batch_limit=max(MIN_BATCH_LIMIT, state.batch_limit // 2),
        workers=max(1, state.workers // 2) if metrics.rate_limited else state.workers,
    )


def load_controller(path: Path) -> CoverageControllerState:
    if not path.is_file():
        return CoverageControllerState.initial()
    value = json.loads(path.read_text(encoding="utf-8"))
    state = CoverageControllerState(**value)
    if (
        state.schema_version != 1
        or state.healthy_streak < 0
        or not MIN_BATCH_LIMIT <= state.batch_limit <= MAX_BATCH_LIMIT
        or not 1 <= state.workers <= MAX_WORKERS
    ):
        raise ValueError("coverage controller state is invalid")
    return state


def save_controller(path: Path, state: CoverageControllerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    building = path.with_suffix(".building")
    building.write_text(
        json.dumps(asdict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    building.replace(path)
