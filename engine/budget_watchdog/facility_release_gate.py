"""Measured review gate for inferred facility identity links."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from engine.budget_watchdog.facility_identity import (
    FacilityLink,
    FacilityRegistryRecord,
    FacilityTitleRecord,
)

MATCHER_VERSION = "facility-identity-v1"
MIN_REVIEWED_CASES = 100
MIN_PRECISION_BPS = 9_500
MIN_AGREEMENT_BPS = 9_500
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DECISIONS = frozenset({"accept", "reject", "ambiguous"})
_ADJUDICATIONS = frozenset({"correct", "incorrect"})


@dataclass(frozen=True, slots=True)
class FacilityReleaseGateResult:
    passed: bool
    candidate_set_sha256: str
    manifest_sha256: str
    reviewed_cases: int
    precision_bps: int
    agreement_bps: int
    critical_failures: int
    reasons: tuple[str, ...]


def _official_candidates(links: tuple[FacilityLink, ...]) -> tuple[FacilityLink, ...]:
    return tuple(
        sorted(
            (link for link in links if link.match_state == "official_exact"),
            key=lambda link: (link.source_type, link.record_id, link.facility_id or ""),
        )
    )


def _candidate_document(links: tuple[FacilityLink, ...]) -> list[dict[str, Any]]:
    return [
        {
            "source_type": link.source_type,
            "record_id": link.record_id,
            "facility_id": link.facility_id,
            "match_method": link.match_method,
            "confidence": link.confidence,
            "signals": list(link.signals),
        }
        for link in _official_candidates(links)
    ]


def candidate_set_sha256(links: tuple[FacilityLink, ...]) -> str:
    """Fingerprint the complete inferred official-link candidate set."""

    payload = json.dumps(_candidate_document(links), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _manifest_digest(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"facility review {label} is invalid")
    return value.strip()


def _review_cases(
    manifest: dict[str, Any],
    candidate_keys: set[tuple[str, str, str]],
) -> tuple[int, int, int]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ValueError("facility review cases must be a list")
    seen: set[tuple[str, str, str]] = set()
    correct = 0
    agreements = 0
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("facility review case must be an object")
        key = (
            _required_text(case.get("source_type"), "source type"),
            _required_text(case.get("record_id"), "record ID"),
            _required_text(case.get("facility_id"), "facility ID"),
        )
        if key not in candidate_keys:
            raise ValueError("facility review case is outside the candidate set")
        if key in seen:
            raise ValueError("facility review case is duplicated")
        seen.add(key)
        reviewer_one = _required_text(case.get("reviewer_one_id"), "reviewer one")
        reviewer_two = _required_text(case.get("reviewer_two_id"), "reviewer two")
        if reviewer_one == reviewer_two:
            raise ValueError("facility review requires independent reviewers")
        decision_one = case.get("reviewer_one_decision")
        decision_two = case.get("reviewer_two_decision")
        adjudication = case.get("adjudication")
        if decision_one not in _DECISIONS or decision_two not in _DECISIONS:
            raise ValueError("facility review decision is invalid")
        if adjudication not in _ADJUDICATIONS:
            raise ValueError("facility review adjudication is invalid")
        agreements += int(decision_one == decision_two)
        correct += int(adjudication == "correct")
    count = len(cases)
    precision_bps = (correct * 10_000) // count if count else 0
    agreement_bps = (agreements * 10_000) // count if count else 0
    return count, precision_bps, agreement_bps


def evaluate_facility_release(
    manifest: dict[str, Any],
    links: tuple[FacilityLink, ...],
    source_artifact_sha256: str,
) -> FacilityReleaseGateResult:
    """Validate review evidence and measure the published release thresholds."""

    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("facility review manifest schema is invalid")
    if _SHA256.fullmatch(source_artifact_sha256) is None:
        raise ValueError("facility review source artifact digest is invalid")
    if manifest.get("source_artifact_sha256") != source_artifact_sha256:
        raise ValueError("facility review source artifact does not match")
    expected_candidates = candidate_set_sha256(links)
    if manifest.get("candidate_set_sha256") != expected_candidates:
        raise ValueError("facility review candidate set does not match")
    if manifest.get("matcher_version") != MATCHER_VERSION:
        raise ValueError("facility review matcher version does not match")
    failures = manifest.get("critical_reconciliation_failures")
    if not isinstance(failures, list) or any(
        not isinstance(item, str) or not item.strip() for item in failures
    ):
        raise ValueError("facility review critical failures must be a text list")
    candidate_keys: set[tuple[str, str, str]] = {
        (link.source_type, link.record_id, link.facility_id or "")
        for link in _official_candidates(links)
    }
    reviewed, precision, agreement = _review_cases(manifest, candidate_keys)
    reasons = []
    if reviewed < MIN_REVIEWED_CASES:
        reasons.append(f"reviewed cases below {MIN_REVIEWED_CASES}")
    if precision < MIN_PRECISION_BPS:
        reasons.append(f"measured precision below {MIN_PRECISION_BPS} basis points")
    if agreement < MIN_AGREEMENT_BPS:
        reasons.append(f"reviewer agreement below {MIN_AGREEMENT_BPS} basis points")
    if failures:
        reasons.append("critical reconciliation failures remain unresolved")
    return FacilityReleaseGateResult(
        passed=not reasons,
        candidate_set_sha256=expected_candidates,
        manifest_sha256=_manifest_digest(manifest),
        reviewed_cases=reviewed,
        precision_bps=precision,
        agreement_bps=agreement,
        critical_failures=len(failures),
        reasons=tuple(reasons),
    )


def build_facility_review_packet(
    source_records: tuple[FacilityTitleRecord, ...],
    registry: tuple[FacilityRegistryRecord, ...],
    links: tuple[FacilityLink, ...],
    source_artifact_sha256: str,
) -> dict[str, Any]:
    """Create the immutable evidence packet reviewers must complete."""

    if _SHA256.fullmatch(source_artifact_sha256) is None:
        raise ValueError("facility review source artifact digest is invalid")
    records = {(record.source_type, record.record_id): record for record in source_records}
    facilities = {record.facility_id: record for record in registry}
    cases = []
    for link in _official_candidates(links):
        record = records.get((link.source_type, link.record_id))
        facility = facilities.get(link.facility_id or "")
        if record is None or facility is None:
            raise ValueError("facility review candidate evidence is incomplete")
        cases.append(
            {
                "source_type": link.source_type,
                "record_id": link.record_id,
                "record_title": record.title,
                "record_location": record.location,
                "facility_id": facility.facility_id,
                "official_school_id": facility.official_id,
                "official_school_name": facility.official_name,
                "official_municipality": facility.municipality,
                "official_region": facility.region,
                "match_method": link.match_method,
                "confidence": link.confidence,
                "signals": list(link.signals),
                "reviewer_one_id": None,
                "reviewer_one_decision": None,
                "reviewer_two_id": None,
                "reviewer_two_decision": None,
                "adjudication": None,
            }
        )
    return {
        "schema_version": 1,
        "source_artifact_sha256": source_artifact_sha256,
        "candidate_set_sha256": candidate_set_sha256(links),
        "matcher_version": MATCHER_VERSION,
        "candidate_count": len(cases),
        "thresholds": {
            "minimum_reviewed_cases": MIN_REVIEWED_CASES,
            "minimum_precision_bps": MIN_PRECISION_BPS,
            "minimum_agreement_bps": MIN_AGREEMENT_BPS,
            "maximum_critical_reconciliation_failures": 0,
        },
        "critical_reconciliation_failures": [],
        "cases": cases,
    }
