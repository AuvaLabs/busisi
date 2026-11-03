"""Exact currency normalization for source-system boundaries."""

from decimal import Decimal, InvalidOperation
from typing import Any


class MoneyValidationError(ValueError):
    """Raised when an amount cannot be represented as exact centavos."""


def _decimal_from_string(value: str) -> Decimal:
    cleaned = value.strip()
    if not cleaned:
        raise MoneyValidationError("amount must not be empty")

    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.removeprefix("₱").strip()
    if cleaned.upper().startswith("PHP"):
        cleaned = cleaned[3:].strip()
    cleaned = cleaned.replace(",", "")

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise MoneyValidationError("amount is not a valid decimal") from exc
    return -amount if negative else amount


def parse_centavos(value: Any) -> int:
    """Convert pesos to integer centavos without accepting binary floats."""

    if isinstance(value, bool) or value is None or isinstance(value, float):
        raise MoneyValidationError("amount must be an integer, decimal, or string")

    if isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, Decimal):
        amount = value
    elif isinstance(value, str):
        amount = _decimal_from_string(value)
    else:
        raise MoneyValidationError("unsupported amount type")

    if not amount.is_finite():
        raise MoneyValidationError("amount must be finite")

    centavos = amount * 100
    integral_centavos = centavos.to_integral_value()
    if centavos != integral_centavos:
        raise MoneyValidationError("amount has more than two decimal places")
    return int(integral_centavos)
