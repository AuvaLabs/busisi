"""Deterministic FY2027 public-value indicators from official DBM BESF tables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

FISCAL_YEAR = 2027
BASELINE_YEAR = 2026
REQUIRED_DOCUMENTS = frozenset({"besf-a1", "besf-a2"})
EXPECTED_YEAR_CELLS = 5


@dataclass(frozen=True, slots=True)
class PublicValueIndicator:
    indicator_id: str
    category: str
    label: str
    unit: str
    value_2026: int
    value_2027: int
    lower_2026: int | None
    upper_2026: int | None
    lower_2027: int | None
    upper_2027: int | None
    change: int
    direction: str
    rule: str
    source_document: str
    source_page: int
    note: str


@dataclass(frozen=True, slots=True)
class _IndicatorSpec:
    indicator_id: str
    category: str
    label: str
    document: str
    row_label: str
    unit: str
    better_when: str
    source_page: int
    after: str | None = None
    note: str = ""


_SPECS = (
    _IndicatorSpec("real_gdp_growth", "economy", "Real GDP growth forecast", "besf-a1", "Real GDP Growth (%)", "range_basis_points", "higher", 1, note="Forecast range, not an observed outcome."),
    _IndicatorSpec("population", "context", "Mid-year population projection", "besf-a1", "Population (in Millions)", "people", "context", 1),
    _IndicatorSpec("unemployment", "economy", "Unemployment target", "besf-a1", "Unemployment Rate (%)", "range_basis_points", "lower", 1, note="PDP target range, not an observed outcome."),
    _IndicatorSpec("revenues", "fiscal_space", "Revenues", "besf-a2", "REVENUES", "centavos", "context", 2),
    _IndicatorSpec("revenue_gdp", "fiscal_space", "Revenues as share of GDP", "besf-a2", "Percent of GDP", "basis_points", "higher", 2, after="REVENUES"),
    _IndicatorSpec("disbursements", "fiscal_space", "Disbursements", "besf-a2", "DISBURSEMENTS", "centavos", "context", 2),
    _IndicatorSpec("disbursement_gdp", "fiscal_space", "Disbursements as share of GDP", "besf-a2", "Percent of GDP", "basis_points", "context", 2, after="DISBURSEMENTS"),
    _IndicatorSpec("interest_payments", "fiscal_space", "Interest payments", "besf-a2", "Interest Payments", "centavos", "context", 2),
    _IndicatorSpec("interest_share", "fiscal_space", "Interest share of disbursements", "besf-a2", "Percent Share to Total Disbursements", "basis_points", "lower", 2),
    _IndicatorSpec("capital_outlays", "composition", "Capital outlays", "besf-a2", "Capital Outlays", "centavos", "context", 2),
    _IndicatorSpec("capital_gdp", "composition", "Capital outlays as share of GDP", "besf-a2", "Percent of GDP", "basis_points", "higher", 2, after="Capital Outlays"),
    _IndicatorSpec("deficit", "fiscal_space", "Fiscal deficit", "besf-a2", "DEFICIT", "centavos", "lower", 2, note="Stored as the absolute size of the deficit."),
    _IndicatorSpec("deficit_gdp", "fiscal_space", "Fiscal deficit as share of GDP", "besf-a2", "Percent of GDP", "basis_points", "lower", 2, after="DEFICIT", note="Stored as the absolute share of GDP."),
    _IndicatorSpec("gross_borrowings", "fiscal_space", "Gross borrowings", "besf-a2", "Gross Borrowings", "centavos", "lower", 2),
    _IndicatorSpec("total_expenditure", "composition", "Total expenditure program", "besf-a2", "Total Expenditure Program", "centavos", "context", 2),
    _IndicatorSpec("infrastructure_program", "composition", "Infrastructure program", "besf-a2", "Infrastructure Program (Disbursements)", "centavos", "context", 2),
    _IndicatorSpec("infrastructure_gdp", "composition", "Infrastructure program as share of GDP", "besf-a2", "Percent of GDP", "basis_points", "higher", 2, after="Infrastructure Program (Disbursements)"),
    _IndicatorSpec("ng_infrastructure", "composition", "National government infrastructure", "besf-a2", "NG Infrastructure", "centavos", "context", 2),
    _IndicatorSpec("lgu_infrastructure_transfers", "composition", "Infrastructure transfers to LGUs", "besf-a2", "Infrastructure Transfers to LGUs", "centavos", "context", 2),
)

_NUMBER = re.compile(r"\(?\d[\d,]*(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\)?")


def _label_pattern(label: str) -> re.Pattern[str]:
    words = re.escape(label).replace(r"\ ", r"\s+")
    return re.compile(rf"^\s*{words}(?:\s+\d+/)?\s+(?P<values>.+)$", re.IGNORECASE)


def _row_cells(text: str, label: str, *, after: str | None = None) -> tuple[str, ...]:
    lines = text.splitlines()
    search_lines = lines
    if after is not None:
        anchor = _label_pattern(after)
        anchor_indexes = [index for index, line in enumerate(lines) if anchor.match(line)]
        if len(anchor_indexes) != 1:
            qualifier = "missing" if not anchor_indexes else "ambiguous"
            raise ValueError(f"required source row is {qualifier}: {after}")
        search_lines = lines[anchor_indexes[0] + 1 : anchor_indexes[0] + 9]
    pattern = _label_pattern(label)
    matches = [
        (index, match)
        for index, line in enumerate(search_lines)
        if (match := pattern.match(line))
    ]
    if after is not None and matches:
        matches = matches[:1]
    if len(matches) != 1:
        qualifier = "missing" if not matches else "ambiguous"
        raise ValueError(f"required source row is {qualifier}: {label}")
    row_index, row_match = matches[0]
    cells = tuple(_NUMBER.findall(row_match.group("values")))
    continuation = row_index + 1
    while len(cells) < EXPECTED_YEAR_CELLS and continuation < len(search_lines):
        next_cells = tuple(_NUMBER.findall(search_lines[continuation]))
        if next_cells:
            cells += next_cells
        continuation += 1
    if len(cells) != EXPECTED_YEAR_CELLS:
        raise ValueError(f"required source row has an invalid year boundary: {label}")
    return cells


def _decimal(cell: str) -> Decimal:
    normalized = cell.replace(",", "").strip("()")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric source cell: {cell}") from exc


def _scaled(cell: str, multiplier: int) -> int:
    value = _decimal(cell) * multiplier
    if value != value.to_integral_value():
        raise ValueError(f"source cell cannot be represented exactly: {cell}")
    return int(value)


def _range(cell: str) -> tuple[int, int, int]:
    if "-" not in cell:
        raise ValueError(f"expected a source range: {cell}")
    lower_cell, upper_cell = cell.split("-", maxsplit=1)
    lower = _scaled(lower_cell, 100)
    upper = _scaled(upper_cell, 100)
    if lower > upper:
        raise ValueError(f"source range is reversed: {cell}")
    return (lower + upper) // 2, lower, upper


def _values(unit: str, cell_2026: str, cell_2027: str) -> tuple[int, int, int | None, int | None, int | None, int | None]:
    if unit == "range_basis_points":
        value_2026, lower_2026, upper_2026 = _range(cell_2026)
        value_2027, lower_2027, upper_2027 = _range(cell_2027)
        return value_2026, value_2027, lower_2026, upper_2026, lower_2027, upper_2027
    multiplier = {"centavos": 100_000_000_000, "basis_points": 100, "people": 1_000_000}[unit]
    return _scaled(cell_2026, multiplier), _scaled(cell_2027, multiplier), None, None, None, None


def _direction(value_2026: int, value_2027: int, better_when: str) -> str:
    if better_when == "context" or value_2026 == value_2027:
        return "context"
    improved = value_2027 > value_2026 if better_when == "higher" else value_2027 < value_2026
    return "improving" if improved else "pressure"


def parse_public_value_documents(documents: dict[str, str]) -> tuple[PublicValueIndicator, ...]:
    """Parse exact FY2026 and FY2027 cells from the declared DBM tables."""
    if set(documents) != REQUIRED_DOCUMENTS:
        raise ValueError("public-value document set is incomplete")
    records = []
    for spec in _SPECS:
        cells = _row_cells(documents[spec.document], spec.row_label, after=spec.after)
        values = _values(spec.unit, cells[1], cells[2])
        value_2026, value_2027 = values[:2]
        direction = _direction(value_2026, value_2027, spec.better_when)
        rule = (
            "Context only; direction is not inherently favorable."
            if spec.better_when == "context"
            else f"{spec.better_when.capitalize()} is treated as favorable for this indicator."
        )
        records.append(
            PublicValueIndicator(
                spec.indicator_id,
                spec.category,
                spec.label,
                spec.unit,
                value_2026,
                value_2027,
                values[2],
                values[3],
                values[4],
                values[5],
                value_2027 - value_2026,
                direction,
                rule,
                spec.document,
                spec.source_page,
                spec.note,
            )
        )
    return tuple(records)


def _rounded_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("public-value ratio denominator must be positive")
    return (numerator + denominator // 2) // denominator


def summarize_public_value(records: tuple[PublicValueIndicator, ...]) -> MappingProxyType[str, int | str]:
    by_id = {record.indicator_id: record for record in records}
    if len(by_id) != len(_SPECS) or set(by_id) != {spec.indicator_id for spec in _SPECS}:
        raise ValueError("public-value indicator set is incomplete")
    improving = sum(record.direction == "improving" for record in records)
    pressure = sum(record.direction == "pressure" for record in records)
    context = sum(record.direction == "context" for record in records)
    reading = "mixed" if improving and pressure else "improving" if improving else "pressure"
    revenue_coverage = _rounded_ratio(
        by_id["revenues"].value_2027 * 10_000,
        by_id["disbursements"].value_2027,
    )
    expenditure_per_capita = _rounded_ratio(
        by_id["total_expenditure"].value_2027,
        by_id["population"].value_2027,
    )
    return MappingProxyType(
        {
            "reading": reading,
            "indicator_count": len(records),
            "improving_count": improving,
            "pressure_count": pressure,
            "context_count": context,
            "revenue_coverage_bps": revenue_coverage,
            "expenditure_per_capita_centavos": expenditure_per_capita,
        }
    )
