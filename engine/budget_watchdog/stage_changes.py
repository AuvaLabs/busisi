"""Validated FY2027 NEP-to-House project change records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

ALLOWED_DATASETS = frozenset({"dpwh", "fmr", "hfep", "nia"})
HGAB_FISCAL_YEAR = 2027
ALLOWED_CHANGE_TYPES = frozenset(
    {"house_only", "nep_only", "unchanged", "increased", "decreased", "scope_review"}
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class StageChangeSchemaError(ValueError):
    """Raised when a stage comparison violates its source or arithmetic contract."""


@dataclass(frozen=True, slots=True)
class StageChange:
    record_id: str
    fiscal_year: int
    dataset: str
    title: str
    program: str
    pap: str
    region: str
    office: str
    change_type: str
    change_label: str
    review_status: str
    held: bool
    confidence: float
    nep_centavos: int
    house_centavos: int
    difference_centavos: int
    source_url: str
    nep_pdf_url: str
    house_pdf_url: str
    nep_page: int | None
    house_page: int | None
    source_commit: str
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class StageChangePage:
    records: tuple[StageChange, ...]
    total: int
    next_offset: int | None
    source_commit: str


@dataclass(frozen=True, slots=True)
class StageChangeSummary:
    record_count: int
    quarantine_count: int
    nep_total_centavos: int
    house_total_centavos: int
    net_difference_centavos: int


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StageChangeSchemaError(f"{field} must be an object")
    return value


def _text(value: Any, field: str, *, optional: bool = False) -> str:
    if value is None and optional:
        return ""
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise StageChangeSchemaError(f"{field} must be non-empty text")
    return value.strip()


def _integer(value: Any, field: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise StageChangeSchemaError(f"{field} must be an integer")
    return value


def _centavos(value: Any, field: str) -> int:
    if value is None:
        return 0
    amount = _integer(value, field)
    if amount is None or amount < 0:
        raise StageChangeSchemaError(f"{field} must be a non-negative integer peso amount")
    return amount * 100


def _https_url(value: Any, field: str) -> str:
    url = _text(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise StageChangeSchemaError(f"{field} must use HTTPS")
    return url


def _optional_https_url(value: Any, field: str) -> str:
    return "" if value is None else _https_url(value, field)


def _decode(payload: bytes) -> dict[str, Any]:
    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StageChangeSchemaError("source page must be valid JSON") from exc
    return _mapping(body, "source page")


def _confidence(row: dict[str, Any], change_type: str) -> float:
    confidence = row.get("confidence")
    if confidence is None:
        confidence = 0 if change_type in {"house_only", "nep_only", "scope_review"} else 1
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise StageChangeSchemaError("confidence must be numeric")
    if not 0 <= confidence <= 1:
        raise StageChangeSchemaError("confidence must be between zero and one")
    return float(confidence)


def _amounts(row: dict[str, Any], change_type: str) -> tuple[int, int, int]:
    nep_centavos = _centavos(row.get("nep_php"), "nep_php")
    house_centavos = _centavos(row.get("house_php"), "house_php")
    difference = _integer(row.get("delta_php"), "delta_php", optional=True)
    if difference is None and change_type in {"house_only", "nep_only"}:
        difference_centavos = house_centavos - nep_centavos
    elif difference is None:
        raise StageChangeSchemaError("delta_php must be an integer")
    else:
        difference_centavos = difference * 100
    if change_type != "scope_review" and difference_centavos != house_centavos - nep_centavos:
        raise StageChangeSchemaError("recorded difference does not match the stage amounts")
    return nep_centavos, house_centavos, difference_centavos


def _pdf_urls(row: dict[str, Any], change_type: str, house_stage: str) -> tuple[str, str]:
    pdf_urls = _mapping(row.get("pdf_url"), "pdf_url")
    nep_pdf_url = _optional_https_url(pdf_urls.get("nep"), "NEP PDF URL")
    house_pdf_url = _optional_https_url(
        pdf_urls.get(house_stage) or pdf_urls.get("house"), "House PDF URL"
    )
    if change_type != "house_only" and not nep_pdf_url:
        raise StageChangeSchemaError("NEP PDF URL is required for this change type")
    if change_type != "nep_only" and not house_pdf_url:
        raise StageChangeSchemaError("House PDF URL is required for this change type")
    return nep_pdf_url, house_pdf_url


def _parse_record(
    raw: Any,
    *,
    dataset: str,
    fiscal_year: int,
    house_stage: str,
    source_commit: str,
    artifact_sha256: str,
) -> StageChange:
    row = _mapping(raw, "data.rows[]")
    if row.get("dataset") != dataset:
        raise StageChangeSchemaError("row dataset does not match page dataset")
    change_type = _text(row.get("bridge_group"), "change type")
    if change_type not in ALLOWED_CHANGE_TYPES:
        raise StageChangeSchemaError("change type is not supported")
    held = row.get("held")
    if not isinstance(held, bool):
        raise StageChangeSchemaError("held must be boolean")
    confidence = _confidence(row, change_type)
    nep_centavos, house_centavos, difference_centavos = _amounts(row, change_type)
    nep_pdf_url, house_pdf_url = _pdf_urls(row, change_type, house_stage)
    return StageChange(
        record_id=f"{dataset}:{_text(row.get('id'), 'id')}",
        fiscal_year=fiscal_year,
        dataset=dataset,
        title=_text(row.get("title"), "title"),
        program=_text(row.get("program"), "program", optional=True),
        pap=_text(row.get("pap"), "pap", optional=True),
        region=_text(row.get("region"), "region", optional=True),
        office=_text(row.get("office"), "office", optional=True),
        change_type=change_type,
        change_label=_text(row.get("group_label"), "group_label"),
        review_status="quarantine" if held or change_type == "scope_review" else "candidate",
        held=held,
        confidence=confidence,
        nep_centavos=nep_centavos,
        house_centavos=house_centavos,
        difference_centavos=difference_centavos,
        source_url=_https_url(row.get("url"), "source URL"),
        nep_pdf_url=nep_pdf_url,
        house_pdf_url=house_pdf_url,
        nep_page=_integer(row.get("nep_page"), "nep_page", optional=True),
        house_page=_integer(row.get(f"{house_stage}_page"), "house_page", optional=True),
        source_commit=source_commit,
        artifact_sha256=artifact_sha256,
    )


def parse_hgab_page(payload: bytes, *, artifact_sha256: str) -> StageChangePage:
    """Validate one BetterGov HGAB comparison page without trusting its labels blindly."""

    if not SHA256_PATTERN.fullmatch(artifact_sha256):
        raise StageChangeSchemaError("artifact_sha256 must be a SHA-256 digest")
    body = _decode(payload)
    meta = _mapping(body.get("meta"), "meta")
    if meta.get("dataset") != "hgab" or meta.get("currency") != "PHP":
        raise StageChangeSchemaError("source page must be the PHP HGAB dataset")
    if meta.get("scale") != "pesos":
        raise StageChangeSchemaError("source page scale must be pesos")
    fiscal_year = _integer(meta.get("fiscal_year"), "fiscal_year")
    if fiscal_year != HGAB_FISCAL_YEAR:
        raise StageChangeSchemaError("fiscal_year must be 2027")
    dataset = _text(meta.get("dataset_key"), "dataset_key")
    if dataset not in ALLOWED_DATASETS:
        raise StageChangeSchemaError("dataset_key is not supported")
    source_commit = _text(meta.get("source_commit"), "source_commit")
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise StageChangeSchemaError("source_commit must be a Git commit digest")
    house_stage = _text(meta.get("house_stage"), "house_stage")
    if house_stage not in {"hgab2", "hgab3"}:
        raise StageChangeSchemaError("house_stage is not supported")
    data = _mapping(body.get("data"), "data")
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise StageChangeSchemaError("data.rows must be an array")
    records = tuple(
        _parse_record(
            row,
            dataset=dataset,
            fiscal_year=fiscal_year,
            house_stage=house_stage,
            source_commit=source_commit,
            artifact_sha256=artifact_sha256,
        )
        for row in rows
    )
    total = _integer(data.get("total"), "data.total")
    next_offset = _integer(data.get("next_offset"), "data.next_offset", optional=True)
    return StageChangePage(records, total or 0, next_offset, source_commit)


def reconcile_hgab_dataset(
    records: tuple[StageChange, ...],
    *,
    expected_count: int,
    expected_nep_centavos: int,
    expected_house_centavos: int,
    expected_quarantine_count: int,
) -> StageChangeSummary:
    """Require record counts and both stage totals to match published controls exactly."""

    if len(records) != expected_count:
        raise StageChangeSchemaError("record count does not match the source control")
    nep_total = sum(record.nep_centavos for record in records)
    house_total = sum(record.house_centavos for record in records)
    quarantine_count = sum(record.review_status == "quarantine" for record in records)
    if nep_total != expected_nep_centavos:
        raise StageChangeSchemaError("NEP control total does not reconcile")
    if house_total != expected_house_centavos:
        raise StageChangeSchemaError("House control total does not reconcile")
    if quarantine_count != expected_quarantine_count:
        raise StageChangeSchemaError("quarantine count does not reconcile")
    return StageChangeSummary(
        record_count=len(records),
        quarantine_count=quarantine_count,
        nep_total_centavos=nep_total,
        house_total_centavos=house_total,
        net_difference_centavos=house_total - nep_total,
    )
