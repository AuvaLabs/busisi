"""Validated contract-lifecycle evidence checklists."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from urllib.parse import urlparse

STAGES = (
    "procurement_plan",
    "bid_notice",
    "procurement_monitoring_report",
    "award_notice",
    "signed_contract",
    "notice_to_proceed",
    "completion_certificate",
    "inspection_acceptance",
    "payment_record",
)
STATUSES = frozenset(
    {"verified_archived", "indexed_unarchived", "blocked", "secondary", "not_located"}
)
EVIDENCE_CLASSES = frozenset(
    {"official_artifact", "official_report", "secondary_mirror", "unavailable"}
)
DATE_KINDS = frozenset({"planned", "actual"})
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MINIMUM_FISCAL_YEAR = 2000
MAXIMUM_FISCAL_YEAR = 2100
HTTP_MINIMUM = 100
HTTP_SUCCESS = 200
HTTP_ERROR_MINIMUM = 400
HTTP_MAXIMUM = 599


class ContractEvidenceError(ValueError):
    """Raised when lifecycle evidence overstates the acquired material."""


@dataclass(frozen=True, slots=True)
class ContractEvidenceItem:
    evidence_id: str
    case_id: str
    contract_id: str
    fiscal_year: int
    stage: str
    status: str
    evidence_class: str
    title: str
    reported_date: str | None
    date_kind: str | None
    source_title: str | None
    source_url: str | None
    source_row_id: str | None
    artifact_sha256: str | None
    source_revision: str | None
    last_checked_at: str
    http_status: int | None
    retry_eligible: bool
    limitation: str


@dataclass(frozen=True, slots=True)
class ContractEvidenceCatalog:
    checked_at: str
    stage_order: tuple[str, ...]
    items: tuple[ContractEvidenceItem, ...]


@dataclass(frozen=True, slots=True)
class ContractEvidenceSummary:
    contract_count: int
    item_count: int
    retry_item_count: int
    status_counts: MappingProxyType[str, int]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractEvidenceError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _date(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ContractEvidenceError(f"{field} must be ISO formatted") from exc
    return text


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContractEvidenceError(f"{field} must be ISO formatted") from exc
    if parsed.tzinfo is None:
        raise ContractEvidenceError(f"{field} must be timezone-aware")
    return text


def _https(value: object, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ContractEvidenceError(f"{field} must use HTTPS without credentials")
    return text


def _year(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MINIMUM_FISCAL_YEAR <= value <= MAXIMUM_FISCAL_YEAR
    ):
        raise ContractEvidenceError("fiscal_year is outside the supported range")
    return value


def _http_status(value: object) -> int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not HTTP_MINIMUM <= value <= HTTP_MAXIMUM
    ):
        raise ContractEvidenceError("http_status must be a valid HTTP status")
    return value


def _validate_source_pair(title: str | None, url: str | None) -> None:
    if (title is None) != (url is None):
        raise ContractEvidenceError("source_title and source_url must be supplied together")


def _validate_status(item: ContractEvidenceItem) -> None:
    has_sha = item.artifact_sha256 is not None and SHA256.fullmatch(item.artifact_sha256) is not None
    if item.status == "verified_archived":
        if (
            item.evidence_class != "official_artifact"
            or item.source_url is None
            or not has_sha
            or item.http_status != HTTP_SUCCESS
            or item.retry_eligible
        ):
            raise ContractEvidenceError("archived evidence requires verified official bytes")
    elif item.status == "blocked":
        if (
            item.evidence_class != "official_artifact"
            or item.source_url is None
            or item.http_status is None
            or item.http_status < HTTP_ERROR_MINIMUM
            or not item.retry_eligible
            or item.artifact_sha256 is not None
        ):
            raise ContractEvidenceError("blocked evidence requires a retryable HTTP failure")
    elif item.status == "secondary":
        if (
            item.evidence_class != "secondary_mirror"
            or item.source_url is None
            or not has_sha
            or item.source_revision is None
            or REVISION.fullmatch(item.source_revision) is None
            or item.source_row_id is None
            or item.retry_eligible
        ):
            raise ContractEvidenceError("secondary evidence requires a revision and row hash")
    elif item.status == "indexed_unarchived":
        if item.source_url is None or item.evidence_class == "unavailable" or has_sha:
            raise ContractEvidenceError("indexed evidence cannot claim archived bytes")
    elif item.status == "not_located" and (
        item.artifact_sha256 is not None or item.source_revision is not None or item.retry_eligible
    ):
        raise ContractEvidenceError("unlocated evidence cannot claim acquisition provenance")


def _item(raw: object) -> ContractEvidenceItem:
    if not isinstance(raw, dict):
        raise ContractEvidenceError("item entries must be objects")
    evidence_id = _text(raw.get("evidence_id"), "evidence_id")
    if IDENTIFIER.fullmatch(evidence_id) is None:
        raise ContractEvidenceError("evidence_id must be a lowercase slug")
    stage = _text(raw.get("stage"), "stage")
    status = _text(raw.get("status"), "status")
    evidence_class = _text(raw.get("evidence_class"), "evidence_class")
    if stage not in STAGES or status not in STATUSES or evidence_class not in EVIDENCE_CLASSES:
        raise ContractEvidenceError("stage, status or evidence_class is invalid")
    reported_date = raw.get("reported_date")
    date_kind = _optional_text(raw.get("date_kind"), "date_kind")
    if (reported_date is None) != (date_kind is None) or (date_kind and date_kind not in DATE_KINDS):
        raise ContractEvidenceError("reported_date and valid date_kind must be supplied together")
    source_title = _optional_text(raw.get("source_title"), "source_title")
    source_url = None if raw.get("source_url") is None else _https(raw.get("source_url"), "source_url")
    _validate_source_pair(source_title, source_url)
    retry_eligible = raw.get("retry_eligible")
    if not isinstance(retry_eligible, bool):
        raise ContractEvidenceError("retry_eligible must be boolean")
    item = ContractEvidenceItem(
        evidence_id=evidence_id,
        case_id=_text(raw.get("case_id"), "case_id"),
        contract_id=_text(raw.get("contract_id"), "contract_id"),
        fiscal_year=_year(raw.get("fiscal_year")),
        stage=stage,
        status=status,
        evidence_class=evidence_class,
        title=_text(raw.get("title"), "title"),
        reported_date=_date(reported_date, "reported_date") if reported_date else None,
        date_kind=date_kind,
        source_title=source_title,
        source_url=source_url,
        source_row_id=_optional_text(raw.get("source_row_id"), "source_row_id"),
        artifact_sha256=_optional_text(raw.get("artifact_sha256"), "artifact_sha256"),
        source_revision=_optional_text(raw.get("source_revision"), "source_revision"),
        last_checked_at=_date(raw.get("last_checked_at"), "last_checked_at"),
        http_status=_http_status(raw.get("http_status")),
        retry_eligible=retry_eligible,
        limitation=_text(raw.get("limitation"), "limitation"),
    )
    _validate_status(item)
    return item


def _validate_complete(items: tuple[ContractEvidenceItem, ...]) -> None:
    grouped: dict[str, list[ContractEvidenceItem]] = {}
    for item in items:
        grouped.setdefault(item.contract_id, []).append(item)
    for contract_items in grouped.values():
        stages = [item.stage for item in contract_items]
        cases = {(item.case_id, item.fiscal_year) for item in contract_items}
        if stages != list(STAGES) or len(cases) != 1:
            raise ContractEvidenceError("each contract requires one complete lifecycle checklist")


def load_contract_evidence_catalog(payload: bytes) -> ContractEvidenceCatalog:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractEvidenceError("contract evidence JSON is invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ContractEvidenceError("unsupported contract evidence schema version")
    stage_order = raw.get("stage_order")
    if stage_order != list(STAGES):
        raise ContractEvidenceError("stage_order must match the lifecycle contract")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise ContractEvidenceError("items must be a non-empty array")
    items = tuple(_item(item) for item in items_raw)
    evidence_ids = [item.evidence_id for item in items]
    contract_stages = [(item.contract_id, item.stage) for item in items]
    if len(evidence_ids) != len(set(evidence_ids)) or len(contract_stages) != len(set(contract_stages)):
        raise ContractEvidenceError("evidence identities must be unique")
    _validate_complete(items)
    return ContractEvidenceCatalog(
        checked_at=_timestamp(raw.get("checked_at"), "checked_at"),
        stage_order=tuple(stage_order),
        items=items,
    )


def summarize_contract_evidence(catalog: ContractEvidenceCatalog) -> ContractEvidenceSummary:
    counts = Counter(item.status for item in catalog.items)
    return ContractEvidenceSummary(
        contract_count=len({item.contract_id for item in catalog.items}),
        item_count=len(catalog.items),
        retry_item_count=sum(item.retry_eligible for item in catalog.items),
        status_counts=MappingProxyType(dict(sorted(counts.items()))),
    )
