"""Reconcile archived official procurement documents to targeted contracts."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

SHA256 = re.compile(r"[0-9a-f]{64}")
CONTRACT_ID = re.compile(r"\b\d{2}[A-Z]{1,3}\d{3,5}\b")
NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")
ALLOWED_EVIDENCE_CLASSES = frozenset({"official_artifact", "official_summary", "identity_conflict"})
ALLOWED_DOCUMENT_TYPES = frozenset(
    {
        "annual_procurement_plan",
        "bidding_documents",
        "constructors_performance_report",
        "post_contract_award_disclosure",
        "procurement_monitoring_report",
    }
)
ALLOWED_EVIDENCE_TYPES = frozenset(
    {
        "procurement_plan",
        "bid_notice",
        "procurement_monitoring_report",
        "award_notice",
        "completion_certificate",
    }
)
OFFICIAL_DPWH_HOSTS = frozenset({"dpwh.gov.ph", "www.dpwh.gov.ph"})


class ProcurementEvidenceError(ValueError):
    """Raised when an official-source claim exceeds the archived evidence."""


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    contract_id: str
    evidence_type: str
    evidence_class: str
    identity_terms: tuple[str, ...]
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialDocument:
    source_id: str
    source_url: str
    document_type: str
    retrieved_at: str
    artifact_sha256: str
    payload: bytes
    extracted_text: str
    bindings: tuple[EvidenceBinding, ...]


def _normalize(value: str) -> str:
    return " ".join(NON_ALPHANUMERIC.sub(" ", value.upper()).split())


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProcurementEvidenceError("retrieved_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ProcurementEvidenceError("retrieved_at must be timezone-aware")
    return value


def _validate_document(document: OfficialDocument) -> None:
    parsed = urlparse(document.source_url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_DPWH_HOSTS:
        raise ProcurementEvidenceError("source URL must use an official DPWH host")
    if document.document_type not in ALLOWED_DOCUMENT_TYPES:
        raise ProcurementEvidenceError("unsupported official document type")
    _timestamp(document.retrieved_at)
    if not document.payload or not document.extracted_text.strip():
        raise ProcurementEvidenceError("official document bytes and extracted text are required")
    observed_digest = hashlib.sha256(document.payload).hexdigest()
    if (
        SHA256.fullmatch(document.artifact_sha256) is None
        or observed_digest != document.artifact_sha256
    ):
        raise ProcurementEvidenceError("official document digest does not match its payload")
    if not document.bindings:
        raise ProcurementEvidenceError("official document must declare at least one binding")


def _contract_window(text: str, contract_id: str, width: int = 1_200) -> str:
    normalized = _normalize(text)
    position = normalized.find(contract_id)
    if position < 0:
        raise ProcurementEvidenceError(f"official document does not contain {contract_id}")
    start = max(position - width // 4, 0)
    return normalized[start : position + width]


def _validate_binding(binding: EvidenceBinding, candidates: dict[str, str], text: str) -> None:
    if CONTRACT_ID.fullmatch(binding.contract_id) is None:
        raise ProcurementEvidenceError("binding contract ID is invalid")
    if binding.contract_id not in candidates:
        raise ProcurementEvidenceError("binding is outside the targeted candidate set")
    if binding.evidence_type not in ALLOWED_EVIDENCE_TYPES:
        raise ProcurementEvidenceError("binding evidence type is unsupported")
    if binding.evidence_class not in ALLOWED_EVIDENCE_CLASSES:
        raise ProcurementEvidenceError("binding evidence class is unsupported")
    if not binding.identity_terms or any(not term.strip() for term in binding.identity_terms):
        raise ProcurementEvidenceError("binding identity terms must be non-empty")
    if binding.evidence_class == "identity_conflict" and not binding.limitation:
        raise ProcurementEvidenceError("identity conflicts require a limitation")
    window = _contract_window(text, binding.contract_id)
    missing = [term for term in binding.identity_terms if _normalize(term) not in window]
    if missing:
        raise ProcurementEvidenceError(
            f"official document lacks binding identity terms for {binding.contract_id}: {missing}"
        )


def _status(evidence_class: str) -> str:
    return {
        "official_artifact": "official_artifact_archived",
        "official_summary": "official_summary_archived",
        "identity_conflict": "source_conflict_quarantined",
    }[evidence_class]


def _record(document: OfficialDocument, binding: EvidenceBinding) -> dict[str, Any]:
    return {
        "contract_id": binding.contract_id,
        "evidence_type": binding.evidence_type,
        "status": _status(binding.evidence_class),
        "evidence_class": binding.evidence_class,
        "document_type": document.document_type,
        "source_id": document.source_id,
        "source_url": document.source_url,
        "retrieved_at": document.retrieved_at,
        "artifact_sha256": document.artifact_sha256,
        "limitation": binding.limitation,
    }


def _contract_states(
    expected_contract_ids: tuple[str, ...], records: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["contract_id"]].append(record)
    result = {}
    for contract_id in expected_contract_ids:
        contract_records = grouped[contract_id]
        states = {row["status"] for row in contract_records}
        if "source_conflict_quarantined" in states:
            state = "source_conflict_quarantined"
        elif states & {"official_artifact_archived", "official_summary_archived"}:
            state = "official_source_archived"
        elif "indexed_unarchived" in states:
            state = "official_source_indexed"
        else:
            state = "discovery_pending"
        result[contract_id] = {
            "state": state,
            "record_count": len(contract_records),
            "source_ids": sorted({row["source_id"] for row in contract_records}),
        }
    return result


def _summary(contracts: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, int]:
    states = [item["state"] for item in contracts.values()]
    return {
        "targeted_contracts": len(contracts),
        "contracts_with_official_sources": sum(state != "discovery_pending" for state in states),
        "official_artifact_records": sum(
            row["status"] == "official_artifact_archived" for row in records
        ),
        "official_summary_records": sum(
            row["status"] == "official_summary_archived" for row in records
        ),
        "indexed_unarchived_records": sum(row["status"] == "indexed_unarchived" for row in records),
        "quarantined_contracts": states.count("source_conflict_quarantined"),
        "discovery_pending_contracts": states.count("discovery_pending"),
    }


def reconcile_official_documents(
    candidates: dict[str, str],
    documents: tuple[OfficialDocument, ...],
    *,
    expected_contract_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Validate archived documents and return a deterministic evidence review."""

    if not expected_contract_ids or len(expected_contract_ids) != len(set(expected_contract_ids)):
        raise ProcurementEvidenceError("expected contract IDs must be unique and non-empty")
    if set(expected_contract_ids) != set(candidates):
        raise ProcurementEvidenceError(
            "candidate descriptions must cover the targeted contract set"
        )
    records = []
    source_ids = set()
    for document in documents:
        _validate_document(document)
        if document.source_id in source_ids:
            raise ProcurementEvidenceError(f"duplicate official source ID: {document.source_id}")
        source_ids.add(document.source_id)
        for binding in document.bindings:
            _validate_binding(binding, candidates, document.extracted_text)
            records.append(_record(document, binding))
    records.sort(key=lambda row: (row["contract_id"], row["evidence_type"], row["source_id"]))
    contracts = _contract_states(expected_contract_ids, records)
    return {
        "schema_version": 1,
        "summary": _summary(contracts, records),
        "contracts": contracts,
        "records": records,
    }


def merge_indexed_records(
    review: dict[str, Any], indexed_records: list[dict[str, object]]
) -> dict[str, Any]:
    """Merge blocked official index leads without converting them to archived proof."""

    contracts = review.get("contracts")
    existing = review.get("records")
    if not isinstance(contracts, dict) or not isinstance(existing, list):
        raise ProcurementEvidenceError("review is missing contracts or records")
    allowed = frozenset({"indexed_unarchived", "source_conflict_quarantined"})
    merged = [dict(item) for item in existing]
    for record in indexed_records:
        contract_id = record.get("contract_id")
        status = record.get("status")
        if contract_id not in contracts or status not in allowed:
            raise ProcurementEvidenceError("indexed record is outside the review contract")
        if record.get("artifact_sha256") is not None:
            raise ProcurementEvidenceError("indexed records cannot claim archived bytes")
        source_url = record.get("source_url")
        parsed = urlparse(str(source_url or ""))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_DPWH_HOSTS:
            raise ProcurementEvidenceError("indexed record requires an official DPWH URL")
        merged.append(dict(record))
    merged.sort(key=lambda row: (row["contract_id"], row["evidence_type"], row["source_id"]))
    expected_ids = tuple(contracts)
    merged_contracts = _contract_states(expected_ids, merged)
    return {
        **review,
        "summary": _summary(merged_contracts, merged),
        "contracts": merged_contracts,
        "records": merged,
    }
