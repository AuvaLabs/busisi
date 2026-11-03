"""Strict adapters for the BetterGov budget and DPWH response shapes."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from engine.budget_watchdog.delivery_flags import DeliverySnapshot
from engine.budget_watchdog.identity import BudgetProject, DeliveryProject
from engine.budget_watchdog.money import MoneyValidationError, parse_centavos


class SourceSchemaError(ValueError):
    """Raised when a source payload does not satisfy its observed contract."""


@dataclass(frozen=True, slots=True)
class DpwhPageInfo:
    page: int
    total_count: int
    has_next: bool


def _decode(payload: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(payload, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceSchemaError("source payload is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SourceSchemaError("source payload must be a JSON object")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SourceSchemaError(f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise SourceSchemaError(f"{field} must be an array")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceSchemaError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SourceSchemaError(f"{field} must be text or null")
    return value.strip()


def _centavos(value: Any, field: str) -> int:
    try:
        return parse_centavos(value)
    except MoneyValidationError as exc:
        raise SourceSchemaError(f"{field} must be an exact peso amount") from exc


def _optional_centavos(value: Any, field: str) -> int | None:
    return None if value is None else _centavos(value, field)


def parse_gaa_search(payload: bytes, *, fiscal_year: int) -> tuple[BudgetProject, ...]:
    body = _decode(payload)
    meta = _mapping(body.get("meta"), "meta")
    if meta.get("dataset") != "gaa":
        raise SourceSchemaError("dataset must be gaa")
    if meta.get("currency") != "PHP":
        raise SourceSchemaError("currency must be PHP")
    if meta.get("scale") != "pesos":
        raise SourceSchemaError("scale must be pesos")

    projects: list[BudgetProject] = []
    for index, raw_record in enumerate(_list(body.get("data"), "data")):
        record = _mapping(raw_record, f"data[{index}]")
        years = _mapping(record.get("years"), f"data[{index}].years")
        year_record_raw = years.get(str(fiscal_year))
        if year_record_raw is None:
            raise SourceSchemaError(f"data[{index}] is missing fiscal year {fiscal_year}")
        year_record = _mapping(year_record_raw, f"data[{index}].years[{fiscal_year}]")
        projects.append(
            BudgetProject(
                budget_line_id=_text(record.get("fam_key"), f"data[{index}].fam_key"),
                fiscal_year=fiscal_year,
                description=_text(record.get("name"), f"data[{index}].name"),
                amount_centavos=_centavos(
                    year_record.get("amount"),
                    f"data[{index}].years[{fiscal_year}].amount",
                ),
                location="",
            )
        )
    return tuple(projects)


def parse_dpwh_search(payload: bytes) -> tuple[DeliveryProject, ...]:
    body = _decode(payload)
    envelope = _mapping(body.get("data"), "data")
    projects: list[DeliveryProject] = []
    for index, raw_record in enumerate(_list(envelope.get("data"), "data.data")):
        record = _mapping(raw_record, f"data.data[{index}]")
        location = _mapping(record.get("location"), f"data.data[{index}].location")
        location_parts = [
            part.strip()
            for part in (location.get("province"), location.get("region"))
            if isinstance(part, str) and part.strip()
        ]
        try:
            fiscal_year = int(_text(record.get("infraYear"), "infraYear"))
        except ValueError as exc:
            raise SourceSchemaError("infraYear must be an integer year") from exc
        projects.append(
            DeliveryProject(
                contract_id=_text(record.get("contractId"), "contractId"),
                fiscal_year=fiscal_year,
                description=_text(record.get("description"), "description"),
                budget_centavos=_centavos(record.get("budget"), "budget"),
                location=", ".join(location_parts),
                source_of_funds=_optional_text(record.get("sourceOfFunds"), "sourceOfFunds"),
            )
        )
    return tuple(projects)


def parse_dpwh_detail(
    payload: bytes,
    *,
    appropriation_centavos: int,
) -> DeliverySnapshot:
    body = _decode(payload)
    record = _mapping(body.get("data", body), "data")
    procurement = _mapping(record.get("procurement"), "procurement")
    try:
        progress = Decimal(str(record.get("progress")))
    except Exception as exc:
        raise SourceSchemaError("progress must be a decimal percentage") from exc
    return DeliverySnapshot(
        contract_id=_text(record.get("contractId"), "contractId"),
        appropriation_centavos=appropriation_centavos,
        project_budget_centavos=_optional_centavos(record.get("budget"), "budget"),
        abc_centavos=_optional_centavos(procurement.get("abc"), "procurement.abc"),
        award_centavos=_optional_centavos(
            procurement.get("awardAmount"), "procurement.awardAmount"
        ),
        status=_text(record.get("status"), "status"),
        progress_percent=progress,
    )


def parse_next_cursor(payload: bytes) -> str | None:
    body = _decode(payload)
    cursor = body.get("next_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise SourceSchemaError("next_cursor must be non-empty text or null")
    return cursor


def parse_dpwh_page_info(payload: bytes) -> DpwhPageInfo:
    body = _decode(payload)
    envelope = _mapping(body.get("data"), "data")
    pagination = _mapping(envelope.get("pagination"), "data.pagination")
    page = pagination.get("page")
    total_count = pagination.get("totalCount")
    has_next = pagination.get("hasNext")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise SourceSchemaError("pagination.page must be a positive integer")
    if isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < 0:
        raise SourceSchemaError("pagination.totalCount must be a non-negative integer")
    if not isinstance(has_next, bool):
        raise SourceSchemaError("pagination.hasNext must be boolean")
    return DpwhPageInfo(page=page, total_count=total_count, has_next=has_next)
