"""Deterministic drift monitor for the Senate FY2027 publication catalogue."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

from engine.budget_watchdog.safe_http import install_ssrf_guard
from engine.budget_watchdog.senate_budget import (
    PortalRow,
    SenateCatalogError,
    SenateDocument,
    load_senate_catalog,
    parse_portal_rows,
)

PORTAL_ORIGIN = "https://budget-transparency-portal.senate.gov.ph"
PORTAL_URL = f"{PORTAL_ORIGIN}/public/Documents?gaa_year=2027"
READER_ORIGIN = "https://r.jina.ai"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_DIRECT_FOLDER_ROWS = 200
MAX_FETCH_ATTEMPTS = 4
HTTP_OK = 200
MARKDOWN_ROW = re.compile(
    r"(?P<title>.+?)\s+Document\s+"
    r"(?P<size>\d+(?:\.\d+)?\s+(?:B|KB|MB|GB))\s+"
    r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4}|—|-)"
)
Fetch = Callable[[str, dict[str, str]], "HttpPayload"]


class SenateMonitorError(RuntimeError):
    """Raised when catalogue drift cannot be checked safely."""


@dataclass(frozen=True, slots=True)
class HttpPayload:
    status_code: int
    final_url: str
    content: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ResponseArtifact:
    name: str
    url: str
    status_code: int
    media_type: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SenateMonitorResult:
    checked_at: str
    changed: bool
    direct_status: str
    discovery_mode: str
    expected_document_count: int
    observed_document_count: int
    differences: tuple[str, ...]
    response_artifacts: tuple[ResponseArtifact, ...]


@dataclass(frozen=True, slots=True)
class _MarkdownDocument:
    title: str
    publication_date: str | None


def _canonical_title(value: str) -> str:
    normalized = re.sub(r"^\s*\d+\s*-\s*", "", value)
    return " ".join(normalized.casefold().split())


def _record_sort_key(value: str) -> tuple[bool, int | str]:
    return (not value.isdigit(), int(value) if value.isdigit() else value)


def _challenge(payload: HttpPayload) -> bool:
    lowered = payload.content[:12_000].lower()
    return b"just a moment" in lowered and b"cloudflare" in lowered


def _fetch_checked(fetch: Fetch, url: str, headers: dict[str, str]) -> HttpPayload:
    for attempt in range(MAX_FETCH_ATTEMPTS):
        payload = fetch(url, headers)
        retryable = payload.status_code in {429, 500, 502, 503, 504} or (
            payload.status_code == HTTP_OK and _challenge(payload)
        )
        if not retryable:
            return payload
        if attempt < MAX_FETCH_ATTEMPTS - 1:
            time.sleep(0.25 * (2**attempt))
    raise SenateMonitorError(f"source remained unavailable after retries: {url}")


def _request(url: str, headers: dict[str, str]) -> HttpPayload:
    install_ssrf_guard()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "budget-transparency-portal.senate.gov.ph",
        "r.jina.ai",
    }:
        raise SenateMonitorError("monitor URL escaped the source allowlist")
    request_headers = {
        "Accept": "text/html, text/plain;q=0.9",
        "User-Agent": "BusisiBudgetWatchdog/1.0",
        **headers,
    }
    try:
        with requests.get(
            url,
            headers=request_headers,
            timeout=(5, 45),
            stream=True,
            allow_redirects=False,
        ) as response:
            chunks: list[bytes] = []
            received = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                received += len(chunk)
                if received > MAX_RESPONSE_BYTES:
                    raise SenateMonitorError("monitor response exceeded the size limit")
                chunks.append(chunk)
            final = urlparse(response.url)
            if final.scheme != "https" or final.hostname != parsed.hostname:
                raise SenateMonitorError("monitor response escaped the requested origin")
            media_type = response.headers.get("Content-Type", "application/octet-stream")
            return HttpPayload(
                status_code=response.status_code,
                final_url=response.url,
                content=b"".join(chunks),
                media_type=media_type.split(";", maxsplit=1)[0].strip(),
            )
    except requests.RequestException as exc:
        raise SenateMonitorError("monitor source request failed") from exc


def _folder_url(folder_id: str, offset: int) -> str:
    query = urlencode(
        {
            "type": "Documents",
            "gaa_year": 2027,
            "folder": folder_id,
            "limit": 1,
            "offset": offset,
            "search": "",
            "filter": "",
        }
    )
    return f"{PORTAL_ORIGIN}/index/file_card?{query}"


def _proxy_url(target: str) -> str:
    return f"{READER_ORIGIN}/{target}"


def _secondary_root_rows(
    rendered: HttpPayload,
    fetch: Fetch,
    recorder: _ArtifactRecorder,
) -> tuple[PortalRow, ...]:
    try:
        return parse_portal_rows(rendered.content)
    except SenateCatalogError:
        listing_url = _proxy_url(_folder_url("", 0).replace("limit=1", "limit=200"))
        listing = _fetch_checked(fetch, listing_url, {"X-Return-Format": "html"})
        if listing.status_code != HTTP_OK:
            raise SenateMonitorError("secondary root listing discovery failed") from None
        recorder.store("secondary-root-listing.html", listing)
        try:
            return parse_portal_rows(listing.content)
        except SenateCatalogError as exc:
            raise SenateMonitorError("secondary root response is invalid") from exc


def _markdown_documents(payload: bytes) -> tuple[_MarkdownDocument, ...]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SenateMonitorError("rendered folder listing is not UTF-8") from exc
    content = text.split("Markdown Content:", maxsplit=1)[-1]
    documents = []
    for match in MARKDOWN_ROW.finditer(" ".join(content.split())):
        raw_date = match.group("date")
        publication_date = None
        if raw_date not in {"-", "—"}:
            publication_date = datetime.strptime(raw_date, "%B %d, %Y").date().isoformat()
        documents.append(_MarkdownDocument(match.group("title").strip(), publication_date))
    if not documents:
        raise SenateMonitorError("rendered folder listing contains no documents")
    return tuple(documents)


class _ArtifactRecorder:
    def __init__(self, output_dir: Path) -> None:
        self._directory = output_dir / "responses"
        self._directory.mkdir(parents=True, exist_ok=True)
        self.artifacts: list[ResponseArtifact] = []

    def store(self, name: str, payload: HttpPayload) -> None:
        safe_name = re.sub(r"[^a-z0-9.-]+", "-", name.casefold()).strip("-")
        path = self._directory / safe_name
        path.write_bytes(payload.content)
        self.artifacts.append(
            ResponseArtifact(
                name=safe_name,
                url=payload.final_url,
                status_code=payload.status_code,
                media_type=payload.media_type,
                byte_size=len(payload.content),
                sha256=hashlib.sha256(payload.content).hexdigest(),
            )
        )


def _secondary_documents(
    root: tuple[PortalRow, ...],
    expected: tuple[SenateDocument, ...],
    fetch: Fetch,
    recorder: _ArtifactRecorder,
) -> tuple[PortalRow, ...]:
    documents = [row for row in root if row.kind == "document"]
    expected_by_title = {}
    for document in expected:
        expected_by_title.setdefault(_canonical_title(document.title), []).append(document)
    folders = [row for row in root if row.kind == "folder"]
    for folder in folders:
        markdown_url = _proxy_url(_folder_url(folder.record_id, 0).replace("limit=1", "limit=200"))
        markdown = _fetch_checked(fetch, markdown_url, {})
        if markdown.status_code != HTTP_OK:
            raise SenateMonitorError("secondary folder discovery failed")
        recorder.store(f"folder-{folder.record_id}-listing.md", markdown)
        for item in _markdown_documents(markdown.content):
            matches = expected_by_title.get(_canonical_title(item.title), [])
            if len(matches) > 1:
                raise SenateMonitorError("reviewed baseline contains an ambiguous title")
            record_id = (
                matches[0].source_record_id
                if matches
                else "unresolved:"
                + hashlib.sha256(_canonical_title(item.title).encode()).hexdigest()[:12]
            )
            documents.append(
                PortalRow(
                    kind="document",
                    record_id=record_id,
                    title=item.title,
                    size_label=None,
                    publication_date=item.publication_date,
                )
            )
    return tuple(documents)


def _direct_documents(
    root: tuple[PortalRow, ...], fetch: Fetch, recorder: _ArtifactRecorder
) -> tuple[PortalRow, ...]:
    documents = [row for row in root if row.kind == "document"]
    for folder in (row for row in root if row.kind == "folder"):
        for offset in range(MAX_DIRECT_FOLDER_ROWS):
            url = _folder_url(folder.record_id, offset)
            payload = _fetch_checked(fetch, url, {})
            recorder.store(f"direct-folder-{folder.record_id}-{offset:03d}.html", payload)
            if payload.status_code != HTTP_OK:
                raise SenateMonitorError("official folder discovery failed")
            if not payload.content.strip():
                break
            try:
                rows = parse_portal_rows(payload.content)
            except SenateCatalogError as exc:
                raise SenateMonitorError("official folder response is invalid") from exc
            documents.extend(row for row in rows if row.kind == "document")
            if not rows:
                break
        else:
            raise SenateMonitorError("official folder exceeded the traversal limit")
    return tuple(documents)


def _compare(expected, observed: tuple[PortalRow, ...]) -> tuple[str, ...]:
    expected_by_id = {document.source_record_id: document for document in expected}
    observed_by_id = {row.record_id: row for row in observed}
    if len(observed_by_id) != len(observed):
        raise SenateMonitorError("observed catalogue contains duplicate record identifiers")
    differences = []
    for record_id in sorted(expected_by_id.keys() - observed_by_id.keys(), key=_record_sort_key):
        differences.append(f"missing source record {record_id}")
    for record_id in sorted(observed_by_id.keys() - expected_by_id.keys(), key=_record_sort_key):
        differences.append(f"new source record {record_id}: {observed_by_id[record_id].title}")
    for record_id in sorted(expected_by_id.keys() & observed_by_id.keys(), key=_record_sort_key):
        expected_record = expected_by_id[record_id]
        observed_record = observed_by_id[record_id]
        if _canonical_title(expected_record.title) != _canonical_title(observed_record.title):
            differences.append(f"title changed for source record {record_id}")
        if expected_record.publication_date != observed_record.publication_date:
            differences.append(f"publication date changed for source record {record_id}")
    return tuple(differences)


def _expected_documents(
    payload: bytes,
    documents: tuple[SenateDocument, ...],
) -> tuple[SenateDocument, ...]:
    try:
        root = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SenateMonitorError("reviewed baseline is not valid JSON") from exc
    excluded = root.get("monitor_excluded_source_record_ids", [])
    if (
        not isinstance(excluded, list)
        or any(not isinstance(value, str) or not value.isdigit() for value in excluded)
        or len(set(excluded)) != len(excluded)
    ):
        raise SenateMonitorError("reviewed monitor exclusions are invalid")
    known = {document.source_record_id for document in documents}
    if not set(excluded) <= known:
        raise SenateMonitorError("reviewed monitor exclusions contain an unknown record")
    return tuple(document for document in documents if document.source_record_id not in excluded)


def run_senate_monitor(
    baseline_path: Path,
    output_dir: Path,
    *,
    fetch: Fetch = _request,
) -> SenateMonitorResult:
    """Compare a fresh bounded catalogue discovery with the reviewed baseline."""

    baseline_payload = baseline_path.read_bytes()
    catalog = load_senate_catalog(baseline_payload)
    expected = _expected_documents(baseline_payload, catalog.documents)
    output_dir.mkdir(parents=True, exist_ok=True)
    recorder = _ArtifactRecorder(output_dir)
    direct = _fetch_checked(fetch, PORTAL_URL, {})
    recorder.store("direct-root.html", direct)
    if direct.status_code == HTTP_OK and not _challenge(direct):
        direct_status = "available"
        discovery_mode = "official_direct"
        try:
            root_rows = parse_portal_rows(direct.content)
        except SenateCatalogError as exc:
            raise SenateMonitorError("official root response is invalid") from exc
        observed = _direct_documents(root_rows, fetch, recorder)
    else:
        direct_status = "blocked" if direct.status_code in {401, 403} else "unavailable"
        discovery_mode = "secondary_renderer"
        rendered = _fetch_checked(
            fetch,
            _proxy_url(PORTAL_URL),
            {"X-Return-Format": "html"},
        )
        if rendered.status_code != HTTP_OK:
            raise SenateMonitorError("secondary root discovery failed")
        recorder.store("secondary-root.html", rendered)
        root_rows = _secondary_root_rows(rendered, fetch, recorder)
        observed = _secondary_documents(root_rows, expected, fetch, recorder)
    differences = _compare(expected, observed)
    result = SenateMonitorResult(
        checked_at=datetime.now(UTC).isoformat(),
        changed=bool(differences),
        direct_status=direct_status,
        discovery_mode=discovery_mode,
        expected_document_count=len(expected),
        observed_document_count=len(observed),
        differences=differences,
        response_artifacts=tuple(recorder.artifacts),
    )
    (output_dir / "report.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
