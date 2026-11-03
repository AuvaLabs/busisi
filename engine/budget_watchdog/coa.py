"""Validated Commission on Audit report and project-coverage catalogue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from urllib.parse import urlparse

REPORT_TYPES = frozenset(
    {
        "annual_audit_report",
        "compliance_audit",
        "performance_audit",
        "citizen_participatory_audit",
        "special_audit",
        "oda_consolidated_audit",
    }
)
ACQUISITION_STATUSES = frozenset({"discovered", "verified_archived", "unavailable"})
COVERAGE_STATUSES = frozenset(
    {
        "not_covered",
        "agency_report_available",
        "program_audit_available",
        "candidate_observation_match",
        "reviewed_observation_match",
        "resolved_or_implemented",
    }
)
MATCH_CONFIDENCES = frozenset({"none", "candidate", "high", "exact"})
IMPLEMENTATION_STATUSES = frozenset(
    {"not_applicable", "not_stated", "pending", "in_progress", "implemented", "unresolved"}
)
CATALOG_STATUSES = frozenset({"reachable", "reachable_by_index", "blocked", "unavailable"})
MINIMUM_FISCAL_YEAR = 2000
MAXIMUM_FISCAL_YEAR = 2100
SHA256_HEX_LENGTH = 64


class CoaCatalogError(ValueError):
    """Raised when COA evidence makes an unsupported or contradictory claim."""


@dataclass(frozen=True, slots=True)
class CoaSourceCatalog:
    catalog_id: str
    title: str
    source_url: str
    checked_status: str
    evidence_note: str


@dataclass(frozen=True, slots=True)
class CoaReport:
    report_id: str
    title: str
    report_type: str
    audited_entity: str
    fiscal_year: int
    publication_date: str | None
    source_url: str
    landing_url: str
    acquisition_status: str
    artifact_sha256: str | None
    byte_size: int | None
    page_count: int | None
    scope_note: str
    evidence_note: str


@dataclass(frozen=True, slots=True)
class CoaProjectCoverage:
    case_id: str
    contract_id: str
    fiscal_year: int
    status: str
    report_id: str | None
    match_confidence: str
    match_basis: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    observation_summary: str
    recommendation_summary: str
    management_response: str
    implementation_status: str
    review_note: str
    reviewed_at: str


@dataclass(frozen=True, slots=True)
class CoaCatalog:
    checked_at: str
    catalogs: tuple[CoaSourceCatalog, ...]
    reports: tuple[CoaReport, ...]
    project_coverage: tuple[CoaProjectCoverage, ...]


@dataclass(frozen=True, slots=True)
class CoaCatalogSummary:
    report_count: int
    archived_reports: int
    checked_projects: int
    project_matches: int
    status_counts: MappingProxyType[str, int]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoaCatalogError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _year(value: object, field: str = "fiscal_year") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MINIMUM_FISCAL_YEAR <= value <= MAXIMUM_FISCAL_YEAR
    ):
        raise CoaCatalogError(f"{field} is outside the supported range")
    return value


def _https(value: object, field: str) -> str:
    url = _text(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CoaCatalogError(f"{field} must use HTTPS without credentials")
    return url


def _iso_date(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise CoaCatalogError(f"{field} must be ISO formatted") from exc
    return text


def _catalog_time(value: object) -> str:
    text = _text(value, "checked_at")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CoaCatalogError("checked_at must be ISO formatted") from exc
    if parsed.tzinfo is None:
        raise CoaCatalogError("checked_at must be timezone-aware")
    return text


def _positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoaCatalogError(f"{field} must be a positive integer")
    return value


def _source_catalog(raw: object) -> CoaSourceCatalog:
    if not isinstance(raw, dict):
        raise CoaCatalogError("catalog entries must be objects")
    status = _text(raw.get("checked_status"), "checked_status")
    if status not in CATALOG_STATUSES:
        raise CoaCatalogError("checked_status is invalid")
    return CoaSourceCatalog(
        catalog_id=_text(raw.get("catalog_id"), "catalog_id"),
        title=_text(raw.get("title"), "catalog title"),
        source_url=_https(raw.get("source_url"), "catalog source_url"),
        checked_status=status,
        evidence_note=_text(raw.get("evidence_note"), "catalog evidence_note"),
    )


def _report(raw: object) -> CoaReport:
    if not isinstance(raw, dict):
        raise CoaCatalogError("report entries must be objects")
    report_type = _text(raw.get("report_type"), "report_type")
    acquisition = _text(raw.get("acquisition_status"), "acquisition_status")
    if report_type not in REPORT_TYPES or acquisition not in ACQUISITION_STATUSES:
        raise CoaCatalogError("report type or acquisition status is invalid")
    sha = _optional_text(raw.get("artifact_sha256"), "artifact_sha256")
    byte_size = _positive_int(raw.get("byte_size"), "byte_size")
    page_count = _positive_int(raw.get("page_count"), "page_count")
    if acquisition == "verified_archived":
        if (
            sha is None
            or len(sha) != SHA256_HEX_LENGTH
            or byte_size is None
            or page_count is None
        ):
            raise CoaCatalogError("verified report requires hash, byte size and page count")
    elif any(value is not None for value in (sha, byte_size, page_count)):
        raise CoaCatalogError("unarchived report must not claim archived artifact metadata")
    publication = raw.get("publication_date")
    return CoaReport(
        report_id=_text(raw.get("report_id"), "report_id"),
        title=_text(raw.get("title"), "report title"),
        report_type=report_type,
        audited_entity=_text(raw.get("audited_entity"), "audited_entity"),
        fiscal_year=_year(raw.get("fiscal_year")),
        publication_date=_iso_date(publication, "publication_date") if publication else None,
        source_url=_https(raw.get("source_url"), "report source_url"),
        landing_url=_https(raw.get("landing_url"), "report landing_url"),
        acquisition_status=acquisition,
        artifact_sha256=sha,
        byte_size=byte_size,
        page_count=page_count,
        scope_note=_text(raw.get("scope_note"), "scope_note"),
        evidence_note=_text(raw.get("evidence_note"), "report evidence_note"),
    )


def _page_range(raw: dict[str, object]) -> tuple[int | None, int | None]:
    start = _positive_int(raw.get("page_start"), "page_start")
    end = _positive_int(raw.get("page_end"), "page_end")
    if (start is None) != (end is None) or (start is not None and end is not None and end < start):
        raise CoaCatalogError("page range must contain ordered start and end pages")
    return start, end


def _coverage(raw: object, report_ids: frozenset[str]) -> CoaProjectCoverage:
    if not isinstance(raw, dict):
        raise CoaCatalogError("project coverage entries must be objects")
    status = _text(raw.get("status"), "coverage status")
    confidence = _text(raw.get("match_confidence"), "match_confidence")
    report_id = _optional_text(raw.get("report_id"), "coverage report_id")
    if status not in COVERAGE_STATUSES or confidence not in MATCH_CONFIDENCES:
        raise CoaCatalogError("coverage status or match confidence is invalid")
    if report_id is not None and report_id not in report_ids:
        raise CoaCatalogError("coverage references an unknown report")
    if status == "not_covered" and (report_id is not None or confidence != "none"):
        raise CoaCatalogError("not_covered status cannot claim a report match")
    if status != "not_covered" and report_id is None:
        raise CoaCatalogError("matched coverage requires a report")
    if status in {"reviewed_observation_match", "resolved_or_implemented"} and confidence not in {
        "exact",
        "high",
    }:
        raise CoaCatalogError("reviewed coverage requires high or exact confidence")
    basis = raw.get("match_basis")
    if not isinstance(basis, list) or any(not isinstance(item, str) or not item for item in basis):
        raise CoaCatalogError("match_basis must be an array of non-empty strings")
    start, end = _page_range(raw)
    implementation = _text(raw.get("implementation_status"), "implementation_status")
    if implementation not in IMPLEMENTATION_STATUSES:
        raise CoaCatalogError("implementation_status is invalid")
    return CoaProjectCoverage(
        case_id=_text(raw.get("case_id"), "case_id"),
        contract_id=_text(raw.get("contract_id"), "contract_id"),
        fiscal_year=_year(raw.get("fiscal_year")),
        status=status,
        report_id=report_id,
        match_confidence=confidence,
        match_basis=tuple(basis),
        page_start=start,
        page_end=end,
        observation_summary=str(raw.get("observation_summary", "")).strip(),
        recommendation_summary=str(raw.get("recommendation_summary", "")).strip(),
        management_response=str(raw.get("management_response", "")).strip(),
        implementation_status=implementation,
        review_note=_text(raw.get("review_note"), "review_note"),
        reviewed_at=_iso_date(raw.get("reviewed_at"), "reviewed_at"),
    )


def _unique(values: tuple[object, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise CoaCatalogError(f"duplicate {field}")


def load_coa_catalog(payload: bytes) -> CoaCatalog:
    """Parse and validate a manually reviewed COA evidence catalogue."""

    try:
        root = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoaCatalogError("catalog JSON is invalid") from exc
    if not isinstance(root, dict) or root.get("schema_version") != 1:
        raise CoaCatalogError("unsupported schema version")
    raw_catalogs = root.get("catalogs")
    raw_reports = root.get("reports")
    raw_coverage = root.get("project_coverage")
    if not all(isinstance(value, list) for value in (raw_catalogs, raw_reports, raw_coverage)):
        raise CoaCatalogError("catalogs, reports and project_coverage must be arrays")
    catalogs = tuple(_source_catalog(item) for item in raw_catalogs)
    reports = tuple(_report(item) for item in raw_reports)
    report_ids = frozenset(report.report_id for report in reports)
    coverage = tuple(_coverage(item, report_ids) for item in raw_coverage)
    _unique(tuple(item.catalog_id for item in catalogs), "catalog_id")
    _unique(tuple(item.report_id for item in reports), "report_id")
    _unique(tuple(item.case_id for item in coverage), "project coverage case_id")
    _unique(tuple(item.contract_id for item in coverage), "project coverage contract_id")
    return CoaCatalog(_catalog_time(root.get("checked_at")), catalogs, reports, coverage)


def summarize_coa_catalog(catalog: CoaCatalog) -> CoaCatalogSummary:
    counts = dict.fromkeys(COVERAGE_STATUSES, 0)
    for item in catalog.project_coverage:
        counts[item.status] += 1
    populated = {key: value for key, value in counts.items() if value}
    matches = sum(
        count
        for status, count in counts.items()
        if status in {"candidate_observation_match", "reviewed_observation_match", "resolved_or_implemented"}
    )
    return CoaCatalogSummary(
        report_count=len(catalog.reports),
        archived_reports=sum(report.acquisition_status == "verified_archived" for report in catalog.reports),
        checked_projects=len(catalog.project_coverage),
        project_matches=matches,
        status_counts=MappingProxyType(populated),
    )
