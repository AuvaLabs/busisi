"""Control-total reconciliation that retains every difference."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ReconciliationStatus(StrEnum):
    EXACT = "exact"
    WITHIN_TOLERANCE = "within_tolerance"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    expected_centavos: int
    observed_centavos: int
    difference_centavos: int
    tolerance_centavos: int
    status: ReconciliationStatus


def reconcile_total(
    *,
    expected_centavos: int,
    observed_centavos: Iterable[int],
    tolerance_centavos: int = 0,
) -> ReconciliationResult:
    if expected_centavos < 0:
        raise ValueError("expected_centavos must not be negative")
    if tolerance_centavos < 0:
        raise ValueError("tolerance_centavos must not be negative")

    observed_values = tuple(observed_centavos)
    if any(isinstance(value, bool) or value < 0 for value in observed_values):
        raise ValueError("observed amounts must be non-negative integers")
    observed = sum(observed_values)
    difference = observed - expected_centavos

    if difference == 0:
        status = ReconciliationStatus.EXACT
    elif abs(difference) <= tolerance_centavos:
        status = ReconciliationStatus.WITHIN_TOLERANCE
    else:
        status = ReconciliationStatus.MISMATCH
    return ReconciliationResult(
        expected_centavos=expected_centavos,
        observed_centavos=observed,
        difference_centavos=difference,
        tolerance_centavos=tolerance_centavos,
        status=status,
    )
