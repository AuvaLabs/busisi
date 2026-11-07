"""Validated procurement evidence for reviewed project dossiers."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from urllib.parse import urlparse

DOCUMENT_TYPES = frozenset(
    {"annual_procurement_plan", "bid_notice", "procurement_monitoring_report"}
)
ACQUISITION_STATUSES = frozenset({"discovered", "verified_archived", "blocked", "not_located"})
EVIDENCE_TYPES = frozenset({"plan", "bid_notice", "monitoring_report"})
MATCH_BASES = frozenset({"exact_contract_id", "exact_solicitation_number"})
COVERAGE_STATUSES = frozenset(
    {
        "exact_evidence",
        "partial_evidence",
        "not_located",
        "current_year_not_yet_located",
        "quarantined",
    }
)
DATE_KINDS = frozenset({"planned", "actual"})
EVENT_STAGES = (
    "pre_procurement_conference",
    "advertisement",
    "pre_bid",
    "eligibility_check",
    "bid_opening",
    "bid_evaluation",
    "post_qualification",
    "bac_resolution",
    "notice_of_award",
    "contract_signing",
    "notice_to_proceed",
    "delivery_completion",
    "inspection_acceptance",
)
EVENT_ORDER = {stage: index for index, stage in enumerate(EVENT_STAGES)}
MINIMUM_FISCAL_YEAR = 2000
MAXIMUM_FISCAL_YEAR = 2100
SHA256_HEX_LENGTH = 64
SOURCE_EVIDENCE_TYPES = {
    "annual_procurement_plan": "plan",
    "bid_notice": "bid_notice",
    "procurement_monitoring_report": "monitoring_report",
}


class ProcurementCatalogError(ValueError):
    """Raised when procurement evidence makes an unsupported claim."""


@dataclass(frozen=True, slots=True)
class ProcurementSource:
    source_id: str
    title: str
    publisher: str
    document_type: str
    fiscal_year: int
    reporting_cutoff: str | None
    source_url: str
    acquisition_status: str
    artifact_sha256: str | None
    byte_size: int | None
    page_count: int | None
    evidence_note: str


@dataclass(frozen=True, slots=True)
class ProcurementEvent:
    stage: str
    event_date: str
    date_kind: str


@dataclass(frozen=True, slots=True)
class ProcurementRecord:
    evidence_id: str
    case_id: str
    contract_id: str
    fiscal_year: int
    source_id: str
    evidence_type: str
    match_basis: str
    project_title: str
    procuring_entity: str
    procurement_mode: str
    procurement_status: str
    page_number: int | None
    reference_number: str | None
    abc_centavos: int | None
    contract_cost_centavos: int | None
    savings_centavos: int | None
    observers: tuple[str, ...]
    events: tuple[ProcurementEvent, ...]
    reviewed_at: str
    boundary_note: str


@dataclass(frozen=True, slots=True)
class ProcurementCoverage:
    case_id: str
    contract_id: str
    fiscal_year: int
    status: str
    record_count: int
    review_note: str
    reviewed_at: str


@dataclass(frozen=True, slots=True)
class ProcurementCatalog:
    checked_at: str
    sources: tuple[ProcurementSource, ...]
    records: tuple[ProcurementRecord, ...]
    coverage: tuple[ProcurementCoverage, ...]


@dataclass(frozen=True, slots=True)
class ProcurementCatalogSummary:
    source_count: int
    archived_sources: int
    record_count: int
    exact_records: int
    checked_projects: int
    projects_with_evidence: int
    status_counts: MappingProxyType[str, int]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProcurementCatalogError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _iso_date(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ProcurementCatalogError(f"{field} must be ISO formatted") from exc
    return text


def _year(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MINIMUM_FISCAL_YEAR <= value <= MAXIMUM_FISCAL_YEAR
    ):
        raise ProcurementCatalogError("fiscal_year is outside the supported range")
    return value


def _nonnegative_int(value: object, field: str, *, optional: bool = True) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProcurementCatalogError(f"{field} must use non-negative integer centavos")
    return value


def _positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProcurementCatalogError(f"{field} must be a positive integer")
    return value


def _https(value: object, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ProcurementCatalogError(f"{field} must use HTTPS without credentials")
    return text


def _source(raw: object) -> ProcurementSource:
    if not isinstance(raw, dict):
        raise ProcurementCatalogError("source entries must be objects")
    document_type = _text(raw.get("document_type"), "document_type")
    acquisition = _text(raw.get("acquisition_status"), "acquisition_status")
    if document_type not in DOCUMENT_TYPES or acquisition not in ACQUISITION_STATUSES:
        raise ProcurementCatalogError("source document type or acquisition status is invalid")
    sha = _optional_text(raw.get("artifact_sha256"), "artifact_sha256")
    byte_size = _positive_int(raw.get("byte_size"), "byte_size")
    page_count = _positive_int(raw.get("page_count"), "page_count")
    if acquisition == "verified_archived":
        if (
            sha is None
            or re.fullmatch(rf"[0-9a-f]{{{SHA256_HEX_LENGTH}}}", sha) is None
            or byte_size is None
        ):
            raise ProcurementCatalogError(
                "verified source requires a lowercase hexadecimal SHA-256 and byte size"
            )
    elif any(value is not None for value in (sha, byte_size, page_count)):
        raise ProcurementCatalogError("unarchived source must not claim archive metadata")
    cutoff = raw.get("reporting_cutoff")
    return ProcurementSource(
        source_id=_text(raw.get("source_id"), "source_id"),
        title=_text(raw.get("title"), "source title"),
        publisher=_text(raw.get("publisher"), "publisher"),
        document_type=document_type,
        fiscal_year=_year(raw.get("fiscal_year")),
        reporting_cutoff=_iso_date(cutoff, "reporting_cutoff") if cutoff else None,
        source_url=_https(raw.get("source_url"), "source_url"),
        acquisition_status=acquisition,
        artifact_sha256=sha,
        byte_size=byte_size,
        page_count=page_count,
        evidence_note=_text(raw.get("evidence_note"), "evidence_note"),
    )


def _events(raw: object) -> tuple[ProcurementEvent, ...]:
    if not isinstance(raw, list):
        raise ProcurementCatalogError("events must be an array")
    events: list[ProcurementEvent] = []
    seen: set[tuple[str, str]] = set()
    prior: dict[str, tuple[int, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ProcurementCatalogError("event entries must be objects")
        stage = _text(item.get("stage"), "event stage")
        kind = _text(item.get("date_kind"), "date_kind")
        if stage not in EVENT_ORDER or kind not in DATE_KINDS or (stage, kind) in seen:
            raise ProcurementCatalogError("event stage, kind or uniqueness is invalid")
        event_date = _iso_date(item.get("event_date"), "event_date")
        previous = prior.get(kind)
        if previous and (EVENT_ORDER[stage] < previous[0] or event_date < previous[1]):
            raise ProcurementCatalogError("event order is inconsistent")
        seen.add((stage, kind))
        prior[kind] = (EVENT_ORDER[stage], event_date)
        events.append(ProcurementEvent(stage, event_date, kind))
    return tuple(events)


def _record(raw: object, source_ids: frozenset[str]) -> ProcurementRecord:
    if not isinstance(raw, dict):
        raise ProcurementCatalogError("record entries must be objects")
    source_id = _text(raw.get("source_id"), "source_id")
    if source_id not in source_ids:
        raise ProcurementCatalogError("record references an unknown source")
    evidence_type = _text(raw.get("evidence_type"), "evidence_type")
    match_basis = _text(raw.get("match_basis"), "match_basis")
    if evidence_type not in EVIDENCE_TYPES or match_basis not in MATCH_BASES:
        raise ProcurementCatalogError("evidence type or match basis is invalid")
    abc = _nonnegative_int(raw.get("abc_centavos"), "abc_centavos")
    contract = _nonnegative_int(raw.get("contract_cost_centavos"), "contract_cost_centavos")
    savings = _nonnegative_int(raw.get("savings_centavos"), "savings_centavos")
    if abc is not None and contract is not None:
        if contract > abc or savings != abc - contract:
            raise ProcurementCatalogError("savings must equal ABC less contract cost")
    elif savings is not None:
        raise ProcurementCatalogError("savings requires ABC and contract cost")
    observers = raw.get("observers")
    if not isinstance(observers, list) or any(
        not isinstance(item, str) or not item.strip() for item in observers
    ):
        raise ProcurementCatalogError("observers must be an array of non-empty strings")
    return ProcurementRecord(
        evidence_id=_text(raw.get("evidence_id"), "evidence_id"),
        case_id=_text(raw.get("case_id"), "case_id"),
        contract_id=_text(raw.get("contract_id"), "contract_id"),
        fiscal_year=_year(raw.get("fiscal_year")),
        source_id=source_id,
        evidence_type=evidence_type,
        match_basis=match_basis,
        project_title=_text(raw.get("project_title"), "project_title"),
        procuring_entity=_text(raw.get("procuring_entity"), "procuring_entity"),
        procurement_mode=_text(raw.get("procurement_mode"), "procurement_mode"),
        procurement_status=_text(raw.get("procurement_status"), "procurement_status"),
        page_number=_positive_int(raw.get("page_number"), "page_number"),
        reference_number=_optional_text(raw.get("reference_number"), "reference_number"),
        abc_centavos=abc,
        contract_cost_centavos=contract,
        savings_centavos=savings,
        observers=tuple(item.strip() for item in observers),
        events=_events(raw.get("events")),
        reviewed_at=_iso_date(raw.get("reviewed_at"), "reviewed_at"),
        boundary_note=_text(raw.get("boundary_note"), "boundary_note"),
    )


def _coverage(raw: object) -> ProcurementCoverage:
    if not isinstance(raw, dict):
        raise ProcurementCatalogError("coverage entries must be objects")
    status = _text(raw.get("status"), "coverage status")
    count = _nonnegative_int(raw.get("record_count"), "record_count", optional=False)
    if count is None:
        raise ProcurementCatalogError("record_count is required")
    if status not in COVERAGE_STATUSES:
        raise ProcurementCatalogError("coverage status is invalid")
    if status in {"exact_evidence", "partial_evidence"} and count == 0:
        raise ProcurementCatalogError("evidence coverage requires a positive record_count")
    if status in {"not_located", "current_year_not_yet_located", "quarantined"} and count != 0:
        raise ProcurementCatalogError(f"{status} coverage cannot claim records")
    return ProcurementCoverage(
        case_id=_text(raw.get("case_id"), "case_id"),
        contract_id=_text(raw.get("contract_id"), "contract_id"),
        fiscal_year=_year(raw.get("fiscal_year")),
        status=status,
        record_count=count,
        review_note=_text(raw.get("review_note"), "review_note"),
        reviewed_at=_iso_date(raw.get("reviewed_at"), "reviewed_at"),
    )


def _unique(items: tuple[object, ...], field: str) -> None:
    values = [getattr(item, field) for item in items]
    if len(values) != len(set(values)):
        raise ProcurementCatalogError(f"duplicate {field}")


def _validate_links(
    sources: tuple[ProcurementSource, ...],
    records: tuple[ProcurementRecord, ...],
    coverage: tuple[ProcurementCoverage, ...],
) -> None:
    source_by_id = {source.source_id: source for source in sources}
    for record in records:
        source = source_by_id[record.source_id]
        if SOURCE_EVIDENCE_TYPES[source.document_type] != record.evidence_type:
            raise ProcurementCatalogError("record evidence type conflicts with its source type")
        if source.fiscal_year != record.fiscal_year:
            raise ProcurementCatalogError("record fiscal year conflicts with its source")
        if (
            record.page_number is not None
            and source.page_count is not None
            and record.page_number > source.page_count
        ):
            raise ProcurementCatalogError("record page exceeds the source page count")
    coverage_cases = {item.case_id for item in coverage}
    if any(record.case_id not in coverage_cases for record in records):
        raise ProcurementCatalogError("every evidence record requires a coverage row")
    record_counts = Counter(item.case_id for item in records)
    for item in coverage:
        if record_counts[item.case_id] != item.record_count:
            raise ProcurementCatalogError("coverage record_count does not match evidence records")
        if any(
            record.contract_id != item.contract_id or record.fiscal_year != item.fiscal_year
            for record in records
            if record.case_id == item.case_id
        ):
            raise ProcurementCatalogError("coverage identity conflicts with evidence records")


def load_procurement_catalog(payload: bytes) -> ProcurementCatalog:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProcurementCatalogError("procurement catalogue JSON is invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ProcurementCatalogError("unsupported procurement schema version")
    checked_at = _text(raw.get("checked_at"), "checked_at")
    try:
        parsed = datetime.fromisoformat(checked_at)
    except ValueError as exc:
        raise ProcurementCatalogError("checked_at must be ISO formatted") from exc
    if parsed.tzinfo is None:
        raise ProcurementCatalogError("checked_at must be timezone-aware")
    if not all(isinstance(raw.get(key), list) for key in ("sources", "records", "coverage")):
        raise ProcurementCatalogError("sources, records and coverage must be arrays")
    sources = tuple(_source(item) for item in raw["sources"])
    _unique(sources, "source_id")
    records = tuple(
        _record(item, frozenset(source.source_id for source in sources)) for item in raw["records"]
    )
    coverage = tuple(_coverage(item) for item in raw["coverage"])
    _unique(records, "evidence_id")
    _unique(coverage, "case_id")
    _unique(coverage, "contract_id")
    _validate_links(sources, records, coverage)
    return ProcurementCatalog(checked_at, sources, records, coverage)


def summarize_procurement_catalog(catalog: ProcurementCatalog) -> ProcurementCatalogSummary:
    counts = Counter(item.status for item in catalog.coverage)
    return ProcurementCatalogSummary(
        source_count=len(catalog.sources),
        archived_sources=sum(
            item.acquisition_status == "verified_archived" for item in catalog.sources
        ),
        record_count=len(catalog.records),
        exact_records=sum(item.match_basis in MATCH_BASES for item in catalog.records),
        checked_projects=len(catalog.coverage),
        projects_with_evidence=sum(item.record_count > 0 for item in catalog.coverage),
        status_counts=MappingProxyType(dict(sorted(counts.items()))),
    )
