from decimal import Decimal

import pytest

from engine.budget_watchdog.money import MoneyValidationError, parse_centavos


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        ("10,000,000", 1_000_000_000),
        ("PHP 9,603,000.00", 960_300_000),
        (Decimal("4944675.10"), 494_467_510),
        ("(1,250.25)", -125_025),
    ],
)
def test_parse_centavos_is_exact(value: object, expected: int) -> None:
    assert parse_centavos(value) == expected


@pytest.mark.parametrize("value", [1.1, "1.001", "NaN", "", True, None])
def test_parse_centavos_rejects_ambiguous_or_invalid_values(value: object) -> None:
    with pytest.raises(MoneyValidationError):
        parse_centavos(value)
