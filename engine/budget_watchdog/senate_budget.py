"""Validated Senate budget-cycle catalogue records and stage coverage."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from types import MappingProxyType
from typing import Any
from urllib.parse import parse_qs, urlparse

FISCAL_YEAR = 2027
PORTAL_HOST = "budget-transparency-portal.senate.gov.ph"
STAGES = ("nep", "house_gab", "senate_committee", "senate_amendment", "bicam", "gaa")
DOCUMENT_STAGES = (*STAGES, "supporting", "unknown")
ACQUISITION_STATUSES = ("discovered", "verified_archived", "unavailable")
COVERAGE_STATUSES = ("available", "available_elsewhere", "partial", "unavailable")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SenateCatalogError(ValueError):
    """Raised when a Senate catalogue claim is unsupported or inconsistent."""


@dataclass(frozen=True, slots=True)
class PortalRow:
    kind: str
    record_id: str
    title: str
    size_label: str | None
    publication_date: str | None


@dataclass(frozen=True, slots=True)
class SenateDocument:
    document_id: str
    source_record_id: str
    title: str
    stage: str
    stage_label: str
    publisher: str
    volume: str | None
    publication_date: str | None
    source_url: str
    viewer_url: str
    acquisition_status: str
    artifact_sha256: str | None
    byte_size: int | None
    mirror_url: str | None
    evidence_note: str


@dataclass(frozen=True, slots=True)
class StageCoverage:
    stage: str
    status: str
    document_count: int


@dataclass(frozen=True, slots=True)
class SenateCatalog:
    fiscal_year: int
    source_url: str
    retrieved_at: str
    acquisition_status: str
    discovery_source_id: str | None
    documents: tuple[SenateDocument, ...]
    stage_coverage: tuple[StageCoverage, ...]


@dataclass(frozen=True, slots=True)
class SenateCatalogSummary:
    document_count: int
    verified_document_count: int
    discovered_document_count: int
    stage_counts: MappingProxyType[str, int]
    unavailable_stages: tuple[str, ...]


@dataclass(slots=True)
class _MutableRow:
    attrs: dict[str, str]
    cells: list[tuple[dict[str, str], str]]
    record_id: str | None = None


class _PortalTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[_MutableRow] = []
        self._row: _MutableRow | None = None
        self._cell_attrs: dict[str, str] | None = None
        self._cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "tr" and "portal-library-row" in values.get("class", "").split():
            self._row = _MutableRow(values, [])
            self._row.record_id = values.get("data-folder-id")
        elif tag == "td" and self._row is not None:
            self._cell_attrs = values
            self._cell_text = []
        if self._row is not None:
            self._row.record_id = (
                values.get("data-file-id") or values.get("data-folder-id") or self._row.record_id
            )

    def handle_data(self, data: str) -> None:
        if self._cell_attrs is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell_attrs is not None:
            text = " ".join(" ".join(self._cell_text).split())
            self._row.cells.append((self._cell_attrs, text))
            self._cell_attrs = None
            self._cell_text = []
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _iso_date(value: str) -> str | None:
    clean = " ".join(value.split())
    if clean in {"", "-", "—", "–"}:
        return None
    try:
        return datetime.strptime(clean, "%B %d, %Y").date().isoformat()
    except ValueError as exc:
        raise SenateCatalogError(f"portal publication date is invalid: {clean}") from exc


def parse_portal_rows(payload: bytes) -> tuple[PortalRow, ...]:
    """Parse rendered portal rows while retaining folders as traversal records."""

    parser = _PortalTableParser()
    try:
        parser.feed(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SenateCatalogError("portal HTML is invalid") from exc
    records: list[PortalRow] = []
    for row in parser.rows:
        kind = "folder" if row.attrs.get("data-folder-id") else "document"
        if not row.record_id or not row.record_id.isdigit():
            raise SenateCatalogError("portal row is missing a numeric record identifier")
        by_label = {attrs.get("data-label", "").lower(): text for attrs, text in row.cells}
        name_cells = [
            text for attrs, text in row.cells if "portal-library-name" in attrs.get("class", "")
        ]
        title = name_cells[0] if name_cells else ""
        if not title:
            raise SenateCatalogError("portal row is missing a title")
        records.append(
            PortalRow(
                kind=kind,
                record_id=row.record_id,
                title=title,
                size_label=by_label.get("size") if kind == "document" else None,
                publication_date=_iso_date(by_label.get("date", "")),
            )
        )
    if not records:
        raise SenateCatalogError("portal HTML contains no catalogue rows")
    return tuple(records)


def classify_stage(title: str) -> str:
    """Classify only explicit document-title evidence, never a page or year label."""

    normalized = " ".join(title.casefold().split())
    rules = (
        ("bicam", "bicameral" in normalized or "bicam" in normalized),
        (
            "gaa",
            "general appropriations act" in normalized and "bill" not in normalized,
        ),
        ("senate_amendment", "senate" in normalized and "amendment" in normalized),
        ("senate_committee", "senate" in normalized and "committee report" in normalized),
        ("house_gab", "house bill" in normalized or bool(re.search(r"\bhb\s*\d+", normalized))),
        (
            "nep",
            "national expenditure program" in normalized or bool(re.search(r"\bnep\b", normalized)),
        ),
        ("supporting", "budget notes" in normalized or "assessment" in normalized),
    )
    return next((stage for stage, matches in rules if matches), "unknown")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SenateCatalogError(f"{label} must be an object")
    return value


def _text(value: Any, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SenateCatalogError(f"{label} must be non-empty text")
    return value.strip()


def _https_url(value: Any, label: str, *, portal_only: bool = False) -> str:
    text = _text(value, label)
    assert text is not None
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SenateCatalogError(f"{label} must use HTTPS")
    if portal_only and parsed.hostname != PORTAL_HOST:
        raise SenateCatalogError(f"{label} must use the Senate portal origin")
    return text


def _optional_url(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _https_url(value, label)


def _document(raw: Any) -> SenateDocument:
    item = _mapping(raw, "document")
    title = _text(item.get("title"), "document title")
    stage = _text(item.get("stage"), "document stage")
    assert title is not None
    assert stage is not None
    if stage not in DOCUMENT_STAGES:
        raise SenateCatalogError("document stage is not supported")
    if stage != classify_stage(title):
        raise SenateCatalogError("document classified stage does not match title evidence")
    source_record_id = _text(item.get("source_record_id"), "source_record_id")
    if source_record_id is None or not source_record_id.isdigit():
        raise SenateCatalogError("source_record_id must be numeric")
    viewer_url = _https_url(item.get("viewer_url"), "viewer_url", portal_only=True)
    viewer_query = parse_qs(urlparse(viewer_url).query)
    if viewer_query.get("id") != [source_record_id]:
        raise SenateCatalogError("viewer_url does not match source_record_id")
    status = _text(item.get("acquisition_status"), "acquisition_status")
    if status not in ACQUISITION_STATUSES:
        raise SenateCatalogError("acquisition_status is not supported")
    digest = _text(item.get("artifact_sha256"), "artifact_sha256", optional=True)
    byte_size = item.get("byte_size")
    mirror_url = _optional_url(item.get("mirror_url"), "mirror_url")
    if status == "verified_archived":
        if digest is None or not SHA256_PATTERN.fullmatch(digest):
            raise SenateCatalogError("verified document requires a SHA-256 fingerprint")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
            raise SenateCatalogError("verified document requires a positive byte size")
        if mirror_url is None:
            raise SenateCatalogError("verified document requires an acquisition URL")
    elif any(value is not None for value in (digest, byte_size, mirror_url)):
        raise SenateCatalogError("unverified document must not claim an archived artifact")
    publication_date = _text(item.get("publication_date"), "publication_date", optional=True)
    if publication_date is not None:
        try:
            date.fromisoformat(publication_date)
        except ValueError as exc:
            raise SenateCatalogError("publication_date must be ISO formatted") from exc
    return SenateDocument(
        document_id=str(_text(item.get("document_id"), "document_id")),
        source_record_id=source_record_id,
        title=title,
        stage=stage,
        stage_label=str(_text(item.get("stage_label"), "stage_label")),
        publisher=str(_text(item.get("publisher"), "publisher")),
        volume=_text(item.get("volume"), "volume", optional=True),
        publication_date=publication_date,
        source_url=_https_url(item.get("source_url"), "source_url", portal_only=True),
        viewer_url=viewer_url,
        acquisition_status=status,
        artifact_sha256=digest,
        byte_size=byte_size,
        mirror_url=mirror_url,
        evidence_note=str(_text(item.get("evidence_note"), "evidence_note")),
    )


def _coverage(raw: Any) -> StageCoverage:
    item = _mapping(raw, "stage coverage")
    stage = _text(item.get("stage"), "coverage stage")
    status = _text(item.get("status"), "coverage status")
    count = item.get("document_count")
    if stage not in STAGES or status not in COVERAGE_STATUSES:
        raise SenateCatalogError("stage coverage value is not supported")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise SenateCatalogError("stage coverage count must be a non-negative integer")
    return StageCoverage(stage, status, count)


def load_senate_catalog(payload: bytes) -> SenateCatalog:
    """Load a source-separated catalogue and enforce its evidence claims."""

    try:
        root = _mapping(json.loads(payload), "catalogue")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SenateCatalogError("catalogue JSON is invalid") from exc
    if root.get("schema_version") != 1 or root.get("fiscal_year") != FISCAL_YEAR:
        raise SenateCatalogError("catalogue schema or fiscal year is unsupported")
    source = _mapping(root.get("source"), "source")
    if source.get("source_id") != "senate-budget-portal":
        raise SenateCatalogError("catalogue source is not the Senate portal")
    documents_raw = root.get("documents")
    coverage_raw = root.get("stage_coverage")
    if not isinstance(documents_raw, list) or not isinstance(coverage_raw, list):
        raise SenateCatalogError("catalogue documents and coverage must be arrays")
    documents = tuple(_document(item) for item in documents_raw)
    coverage = tuple(_coverage(item) for item in coverage_raw)
    if len({item.document_id for item in documents}) != len(documents):
        raise SenateCatalogError("catalogue contains duplicate document identifiers")
    if tuple(item.stage for item in coverage) != STAGES:
        raise SenateCatalogError("stage coverage must contain every budget stage in order")
    catalog = SenateCatalog(
        fiscal_year=FISCAL_YEAR,
        source_url=_https_url(source.get("url"), "source URL", portal_only=True),
        retrieved_at=str(_text(source.get("retrieved_at"), "retrieved_at")),
        acquisition_status=str(_text(source.get("acquisition_status"), "source status")),
        discovery_source_id=_text(
            source.get("discovery_source_id"), "discovery_source_id", optional=True
        ),
        documents=documents,
        stage_coverage=coverage,
    )
    reconcile_senate_catalog(catalog)
    return catalog


def reconcile_senate_catalog(catalog: SenateCatalog) -> SenateCatalogSummary:
    """Reconcile stage counts and preserve unavailable stages as missing evidence."""

    counts = Counter(document.stage for document in catalog.documents if document.stage in STAGES)
    for coverage in catalog.stage_coverage:
        actual = counts.get(coverage.stage, 0)
        if actual != coverage.document_count:
            raise SenateCatalogError(f"{coverage.stage} document count does not reconcile")
        if coverage.status == "unavailable" and actual != 0:
            raise SenateCatalogError(f"{coverage.stage} cannot be unavailable with documents")
    return SenateCatalogSummary(
        document_count=len(catalog.documents),
        verified_document_count=sum(
            document.acquisition_status == "verified_archived" for document in catalog.documents
        ),
        discovered_document_count=sum(
            document.acquisition_status == "discovered" for document in catalog.documents
        ),
        stage_counts=MappingProxyType(dict(counts)),
        unavailable_stages=tuple(
            coverage.stage
            for coverage in catalog.stage_coverage
            if coverage.status == "unavailable"
        ),
    )
