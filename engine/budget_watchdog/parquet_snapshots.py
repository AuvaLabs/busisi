"""Stable Parquet baseline adapters for BetterGov GAA and DPWH snapshots."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from engine.budget_watchdog.identity import BudgetProject, DeliveryProject
from engine.budget_watchdog.models import validate_fiscal_year
from engine.budget_watchdog.money import MoneyValidationError, parse_centavos

NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
GAA_SOURCE_PESO_MULTIPLIER = 1000


class SnapshotSchemaError(ValueError):
    """Raised when a Parquet baseline violates its expected schema."""


@dataclass(frozen=True, slots=True)
class SnapshotIssue:
    row_number: int
    code: str
    detail: str
    source_identifier: str
    amount_centavos: int | None


@dataclass(frozen=True, slots=True)
class SnapshotLoadResult:
    records: tuple[BudgetProject | DeliveryProject, ...]
    issues: tuple[SnapshotIssue, ...]
    source_rows: int


def _canonical_description(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotSchemaError("description must be non-empty text")
    description = value.strip()
    normalized = unicodedata.normalize("NFKD", description.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    canonical = " ".join(NON_ALPHANUMERIC.sub(" ", ascii_text).split())
    if not canonical:
        raise SnapshotSchemaError("description has no canonical text")
    return description, canonical


def _centavos(value: Any, field: str) -> int:
    normalized = Decimal(str(value)) if isinstance(value, float) else value
    try:
        return parse_centavos(normalized)
    except MoneyValidationError as exc:
        raise SnapshotSchemaError(f"{field} is not an exact peso amount") from exc


def _gaa_centavos(value: Any) -> int:
    return _centavos(value, "amt") * GAA_SOURCE_PESO_MULTIPLIER


def _validate_years(fiscal_years: tuple[int, ...]) -> None:
    if not fiscal_years:
        raise ValueError("fiscal_years must not be empty")
    if len(fiscal_years) != len(set(fiscal_years)):
        raise ValueError("fiscal_years must be unique")
    for fiscal_year in fiscal_years:
        validate_fiscal_year(fiscal_year)


def load_gaa_snapshot(
    path: Path,
    *,
    department_id: str,
    fiscal_years: tuple[int, ...],
) -> SnapshotLoadResult:
    """Aggregate UACS object rows into department program-description families."""

    _validate_years(fiscal_years)
    if not department_id.isdigit():
        raise ValueError("department_id must be numeric")
    try:
        table = pq.read_table(
            path,
            columns=["department", "agency", "dsc", "amt", "year"],
            filters=[
                ("department", "=", department_id),
                ("year", "in", list(fiscal_years)),
            ],
        )
    except Exception as exc:
        raise SnapshotSchemaError("cannot read the GAA Parquet schema") from exc

    grouped: dict[tuple[str, str, int], tuple[str, int]] = {}
    issues: list[SnapshotIssue] = []
    for row_number, row in enumerate(table.to_pylist()):
        amount: int | None = None
        try:
            agency = row.get("agency")
            year = row.get("year")
            if not isinstance(agency, str) or not agency.strip():
                raise SnapshotSchemaError("agency must be non-empty text")
            if isinstance(year, bool) or not isinstance(year, int):
                raise SnapshotSchemaError("year must be an integer")
            amount = _gaa_centavos(row.get("amt"))
            description, canonical = _canonical_description(row.get("dsc"))
            key = (agency.strip(), canonical, year)
            existing = grouped.get(key)
            grouped[key] = (
                existing[0] if existing is not None else description,
                (existing[1] if existing is not None else 0) + amount,
            )
        except (SnapshotSchemaError, ValueError) as exc:
            issues.append(
                SnapshotIssue(
                    row_number=row_number,
                    code="invalid_gaa_row",
                    detail=str(exc),
                    source_identifier=repr(row.get("dsc")),
                    amount_centavos=amount,
                )
            )

    projects = []
    for (agency, canonical, year), (description, amount) in sorted(grouped.items()):
        if amount <= 0:
            continue
        projects.append(
            BudgetProject(
                budget_line_id=f"{department_id}-{agency}|{canonical}",
                fiscal_year=year,
                description=description,
                amount_centavos=amount,
                location="",
            )
        )
    return SnapshotLoadResult(tuple(projects), tuple(issues), table.num_rows)


def load_dpwh_snapshot(
    path: Path,
    *,
    fiscal_years: tuple[int, ...],
) -> SnapshotLoadResult:
    _validate_years(fiscal_years)
    year_values = [str(year) for year in fiscal_years]
    try:
        table = pq.read_table(
            path,
            columns=[
                "contractId",
                "description",
                "budget",
                "infraYear",
                "location",
                "sourceOfFunds",
            ],
            filters=[("infraYear", "in", year_values)],
        )
    except Exception as exc:
        raise SnapshotSchemaError("cannot read the DPWH Parquet schema") from exc

    projects: dict[str, DeliveryProject] = {}
    issues: list[SnapshotIssue] = []
    for row_number, row in enumerate(table.to_pylist()):
        try:
            contract_id = row.get("contractId")
            if not isinstance(contract_id, str) or not contract_id.strip():
                raise SnapshotSchemaError("contractId must be non-empty text")
            description, _ = _canonical_description(row.get("description"))
            year_value = row.get("infraYear")
            if not isinstance(year_value, str) or not year_value.isdigit():
                raise SnapshotSchemaError("infraYear must be a numeric string")
            location = row.get("location")
            if not isinstance(location, dict):
                raise SnapshotSchemaError("location must be an object")
            location_text = ", ".join(
                value.strip()
                for value in (location.get("province"), location.get("region"))
                if isinstance(value, str) and value.strip()
            )
            source_of_funds = row.get("sourceOfFunds")
            if source_of_funds is None:
                source_of_funds = ""
            if not isinstance(source_of_funds, str):
                raise SnapshotSchemaError("sourceOfFunds must be text or null")
            project = DeliveryProject(
                contract_id=contract_id.strip(),
                fiscal_year=int(year_value),
                description=description,
                budget_centavos=_centavos(row.get("budget"), "budget"),
                location=location_text,
                source_of_funds=source_of_funds.strip(),
            )
            existing = projects.get(project.contract_id)
            if existing is not None and existing != project:
                raise SnapshotSchemaError(f"conflicting contractId: {project.contract_id}")
            projects[project.contract_id] = project
        except (SnapshotSchemaError, ValueError) as exc:
            issues.append(
                SnapshotIssue(
                    row_number=row_number,
                    code="invalid_dpwh_row",
                    detail=str(exc),
                    source_identifier=repr(row.get("contractId")),
                    amount_centavos=None,
                )
            )
    records = tuple(projects[key] for key in sorted(projects))
    return SnapshotLoadResult(records, tuple(issues), table.num_rows)
