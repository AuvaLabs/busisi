"""Acquire reviewed DPWH procurement documents from a bounded source catalog."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.official_procurement_evidence import (
    ALLOWED_DOCUMENT_TYPES,
    ALLOWED_EVIDENCE_CLASSES,
    ALLOWED_EVIDENCE_TYPES,
    CONTRACT_ID,
    OFFICIAL_DPWH_HOSTS,
    EvidenceBinding,
    OfficialDocument,
)

HTTP_SERVER_ERROR_MINIMUM = 500


class OfficialAcquisitionError(ValueError):
    """Raised when the bounded source catalogue or downloaded bytes are invalid."""


@dataclass(frozen=True, slots=True)
class OfficialSource:
    source_id: str
    source_url: str
    document_type: str
    bindings: tuple[EvidenceBinding, ...]


class UrlFetcher(Protocol):
    def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition: ...


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfficialAcquisitionError(f"{field} must be non-empty text")
    return value.strip()


def _terms(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise OfficialAcquisitionError("identity_terms must be a non-empty list")
    return tuple(_text(item, "identity term") for item in value)


def _binding(raw: object) -> EvidenceBinding:
    if not isinstance(raw, dict):
        raise OfficialAcquisitionError("bindings must be objects")
    contract_id = _text(raw.get("contract_id"), "contract_id")
    evidence_type = _text(raw.get("evidence_type"), "evidence_type")
    evidence_class = _text(raw.get("evidence_class"), "evidence_class")
    if CONTRACT_ID.fullmatch(contract_id) is None:
        raise OfficialAcquisitionError("contract_id is invalid")
    if evidence_type not in ALLOWED_EVIDENCE_TYPES:
        raise OfficialAcquisitionError("evidence_type is unsupported")
    if evidence_class not in ALLOWED_EVIDENCE_CLASSES:
        raise OfficialAcquisitionError("evidence_class is unsupported")
    limitation = raw.get("limitation")
    if limitation is not None:
        limitation = _text(limitation, "limitation")
    return EvidenceBinding(
        contract_id=contract_id,
        evidence_type=evidence_type,
        evidence_class=evidence_class,
        identity_terms=_terms(raw.get("identity_terms")),
        limitation=limitation,
    )


def _source(raw: object) -> OfficialSource:
    if not isinstance(raw, dict):
        raise OfficialAcquisitionError("sources must be objects")
    source_id = _text(raw.get("source_id"), "source_id")
    source_url = _text(raw.get("source_url"), "source_url")
    document_type = _text(raw.get("document_type"), "document_type")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_DPWH_HOSTS:
        raise OfficialAcquisitionError("source_url must use an official DPWH host")
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise OfficialAcquisitionError("document_type is unsupported")
    bindings = raw.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise OfficialAcquisitionError("source bindings must be a non-empty list")
    return OfficialSource(
        source_id=source_id,
        source_url=source_url,
        document_type=document_type,
        bindings=tuple(_binding(item) for item in bindings),
    )


def load_official_source_catalog(payload: bytes) -> tuple[OfficialSource, ...]:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfficialAcquisitionError("official source catalogue JSON is invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise OfficialAcquisitionError("unsupported official source catalogue")
    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise OfficialAcquisitionError("official source catalogue must contain sources")
    sources = tuple(_source(item) for item in sources_raw)
    identifiers = [item.source_id for item in sources]
    if len(identifiers) != len(set(identifiers)):
        raise OfficialAcquisitionError("duplicate official source ID")
    return sources


def _retrieved_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OfficialAcquisitionError("retrieved_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise OfficialAcquisitionError("retrieved_at must be timezone-aware")
    return parsed


def _source_path(source_dir: Path, source_id: str) -> Path:
    path = source_dir / f"{source_id}.pdf"
    if not path.is_file():
        raise OfficialAcquisitionError(f"official source download is missing: {source_id}")
    if not path.read_bytes()[:5].startswith(b"%PDF-"):
        raise OfficialAcquisitionError(f"official source is not a PDF: {source_id}")
    return path


def _write_download(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_official_sources(
    sources: tuple[OfficialSource, ...],
    *,
    destination: Path,
    fetcher: UrlFetcher,
    retrieved_at: datetime,
) -> list[dict[str, object]]:
    """Download the bounded source catalogue without accepting redirects or HTML."""

    if retrieved_at.tzinfo is None:
        raise OfficialAcquisitionError("retrieved_at must be timezone-aware")
    manifest = []
    for source in sources:
        acquisition = fetcher.fetch_url(source.source_url, retrieved_at)
        if acquisition.source_url != source.source_url:
            raise OfficialAcquisitionError(f"official source URL changed: {source.source_id}")
        if not acquisition.payload.startswith(b"%PDF-"):
            raise OfficialAcquisitionError(
                f"official source did not return a PDF: {source.source_id}"
            )
        path = destination / f"{source.source_id}.pdf"
        _write_download(path, acquisition.payload)
        manifest.append(
            {
                "source_id": source.source_id,
                "source_url": source.source_url,
                "byte_size": len(acquisition.payload),
            }
        )
    return manifest


def attempt_official_source_downloads(
    sources: tuple[OfficialSource, ...],
    *,
    destination: Path,
    fetcher: UrlFetcher,
    retrieved_at: datetime,
) -> list[dict[str, object]]:
    """Attempt every source and retain explicit blocked states without promotion."""

    if retrieved_at.tzinfo is None:
        raise OfficialAcquisitionError("retrieved_at must be timezone-aware")
    attempts = []
    for source in sources:
        try:
            acquisition = fetcher.fetch_url(source.source_url, retrieved_at)
            if acquisition.source_url != source.source_url:
                raise OfficialAcquisitionError("official source URL changed")
            if not acquisition.payload.startswith(b"%PDF-"):
                raise OfficialAcquisitionError("official source did not return a PDF")
            _write_download(destination / f"{source.source_id}.pdf", acquisition.payload)
            attempts.append(
                {
                    "source_id": source.source_id,
                    "source_url": source.source_url,
                    "status": "downloaded",
                    "http_status": 200,
                    "retry_eligible": False,
                    "byte_size": len(acquisition.payload),
                }
            )
        except AcquisitionError as error:
            attempts.append(
                {
                    "source_id": source.source_id,
                    "source_url": source.source_url,
                    "status": "blocked",
                    "http_status": error.http_status,
                    "retry_eligible": error.http_status in {403, 408, 425, 429}
                    or bool(error.http_status and error.http_status >= HTTP_SERVER_ERROR_MINIMUM),
                }
            )
        except OfficialAcquisitionError:
            attempts.append(
                {
                    "source_id": source.source_id,
                    "source_url": source.source_url,
                    "status": "blocked",
                    "http_status": None,
                    "retry_eligible": False,
                }
            )
    return attempts


def indexed_records_for_blocked_sources(
    sources: tuple[OfficialSource, ...],
    attempts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Convert reviewed index leads into unarchived records, never verified evidence."""

    attempt_index = {str(item["source_id"]): item for item in attempts}
    if set(attempt_index) != {source.source_id for source in sources}:
        raise OfficialAcquisitionError("download attempts do not cover the source catalogue")
    records = []
    for source in sources:
        attempt = attempt_index[source.source_id]
        if attempt.get("status") != "blocked":
            continue
        for binding in source.bindings:
            conflict = binding.evidence_class == "identity_conflict"
            records.append(
                {
                    "contract_id": binding.contract_id,
                    "evidence_type": binding.evidence_type,
                    "status": ("source_conflict_quarantined" if conflict else "indexed_unarchived"),
                    "evidence_class": binding.evidence_class,
                    "document_type": source.document_type,
                    "source_id": source.source_id,
                    "source_url": source.source_url,
                    "retrieved_at": None,
                    "artifact_sha256": None,
                    "http_status": attempt.get("http_status"),
                    "retry_eligible": bool(attempt.get("retry_eligible")),
                    "limitation": binding.limitation
                    or "The official document is indexed but its source bytes are not archived.",
                }
            )
    return records


def acquire_official_documents(
    sources: tuple[OfficialSource, ...],
    *,
    source_dir: Path,
    archive: ArtifactArchive,
    retrieved_at: str,
    extract_text: Callable[[Path], str],
) -> tuple[OfficialDocument, ...]:
    """Archive each downloaded source and bind its extracted text to review records."""

    timestamp = _retrieved_at(retrieved_at)
    documents = []
    for source in sources:
        path = _source_path(source_dir, source.source_id)
        payload = path.read_bytes()
        artifact = archive.store(
            Acquisition(
                source_id=source.source_id,
                source_url=source.source_url,
                retrieved_at=timestamp,
                media_type="application/pdf",
                payload=payload,
            )
        )
        extracted_text = extract_text(path)
        if not extracted_text.strip():
            raise OfficialAcquisitionError(f"official source text is empty: {source.source_id}")
        documents.append(
            OfficialDocument(
                source_id=source.source_id,
                source_url=source.source_url,
                document_type=source.document_type,
                retrieved_at=retrieved_at,
                artifact_sha256=artifact.sha256,
                payload=payload,
                extracted_text=extracted_text,
                bindings=source.bindings,
            )
        )
    return tuple(documents)
