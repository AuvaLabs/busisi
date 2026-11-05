"""Publish bounded official-procurement discovery without overstating evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.research_editor import build_consumption_index

DPWH_SOURCE_ID = "dpwh-delivery-snapshot-2026-01-22"
CALCULATION_ID = "mpb-official-procurement-evidence-v1"
OFFICIAL_HOSTS = frozenset({"dpwh.gov.ph", "www.dpwh.gov.ph"})
REVIEW_STATUSES = frozenset(
    {
        "official_artifact_archived",
        "official_summary_archived",
        "indexed_unarchived",
        "source_conflict_quarantined",
    }
)


def _candidate_ids(release: dict[str, Any]) -> tuple[str, ...]:
    candidates = release["project_examples"]["public_value_candidates"]
    identifiers = tuple(str(item["contract_id"]) for item in candidates)
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise ValueError("release candidate set must be unique and non-empty")
    return identifiers


def _validate_acquisition(
    acquisition: dict[str, Any], candidate_ids: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    candidates = acquisition.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("acquisition candidates must be a list")
    indexed = {str(item.get("contract_id")): item for item in candidates}
    if set(indexed) != set(candidate_ids) or len(indexed) != len(candidates):
        raise ValueError("acquisition candidate set must match the public queue")
    task_definitions = acquisition.get("task_definitions")
    summary = acquisition.get("summary")
    if not isinstance(task_definitions, list) or not isinstance(summary, dict):
        raise ValueError("acquisition summary and task definitions are required")
    if summary.get("task_count") != len(candidate_ids) * len(task_definitions):
        raise ValueError("acquisition task count does not reconcile")
    observed = Counter()
    for candidate in candidates:
        counts = candidate.get("status_counts")
        if not isinstance(counts, dict) or sum(counts.values()) != len(task_definitions):
            raise ValueError("candidate acquisition counts do not reconcile")
        observed.update(counts)
    for status in (
        "verified_archived",
        "official_summary_archived",
        "indexed_unarchived",
        "secondary_exact",
        "source_media_archived",
        "pending",
        "quarantined",
    ):
        if summary.get(status, 0) != observed[status]:
            raise ValueError(f"acquisition summary does not reconcile for {status}")
    return indexed


def _expected_contract_state(records: list[dict[str, Any]]) -> str:
    states = {str(item.get("status")) for item in records}
    if "source_conflict_quarantined" in states:
        return "source_conflict_quarantined"
    if states & {"official_artifact_archived", "official_summary_archived"}:
        return "official_source_archived"
    if "indexed_unarchived" in states:
        return "official_source_indexed"
    return "discovery_pending"


def _validate_review(
    review: dict[str, Any], candidate_ids: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    contracts = review.get("contracts")
    records = review.get("records")
    summary = review.get("summary")
    if not isinstance(contracts, dict) or set(contracts) != set(candidate_ids):
        raise ValueError("official review candidate set must match the public queue")
    if not isinstance(records, list) or not isinstance(summary, dict):
        raise ValueError("official review records and summary are required")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        contract_id = str(record.get("contract_id") or "")
        status = str(record.get("status") or "")
        parsed = urlparse(str(record.get("source_url") or ""))
        if (
            contract_id not in contracts
            or status not in REVIEW_STATUSES
            or parsed.scheme != "https"
            or parsed.hostname not in OFFICIAL_HOSTS
        ):
            raise ValueError("official review contains an invalid record")
        if status == "indexed_unarchived" and record.get("artifact_sha256") is not None:
            raise ValueError("indexed official records cannot claim archived bytes")
        grouped[contract_id].append(record)
    state_counts = Counter()
    for contract_id, contract in contracts.items():
        expected = _expected_contract_state(grouped[contract_id])
        if contract.get("state") != expected:
            raise ValueError(f"official review state does not reconcile for {contract_id}")
        state_counts[expected] += 1
    observed = {
        "targeted_contracts": len(contracts),
        "contracts_with_official_sources": len(contracts) - state_counts["discovery_pending"],
        "official_artifact_records": sum(
            item["status"] == "official_artifact_archived" for item in records
        ),
        "official_summary_records": sum(
            item["status"] == "official_summary_archived" for item in records
        ),
        "indexed_unarchived_records": sum(
            item["status"] == "indexed_unarchived" for item in records
        ),
        "quarantined_contracts": state_counts["source_conflict_quarantined"],
        "discovery_pending_contracts": state_counts["discovery_pending"],
    }
    if any(summary.get(key) != value for key, value in observed.items()):
        raise ValueError("official review summary does not reconcile")
    return grouped


def _claim(identifier: str, statement: str, value: int, unit: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "value": value,
        "unit": unit,
        "scope": "Official procurement discovery for the 43-project evidence queue",
        "evidence_state": "review_candidate",
        "calculation_id": CALCULATION_ID,
        "source_ids": [DPWH_SOURCE_ID],
        "limitations": [
            "Indexed official URLs are leads, not archived evidence. Conflicts are quarantined and do not establish wrongdoing."
        ],
    }


def _replace_claims(
    release: dict[str, Any], acquisition: dict[str, Any], review: dict[str, Any]
) -> None:
    summary = acquisition["summary"]
    replacements = {
        "mpb-acquisition-tasks": (summary["task_count"], "evidence checks"),
        "mpb-official-verified-tasks": (summary["verified_archived"], "evidence checks"),
        "mpb-secondary-award-leads": (summary["secondary_exact"], "evidence checks"),
        "mpb-source-media-leads": (summary["source_media_archived"], "evidence checks"),
        "mpb-pending-acquisition-tasks": (summary["pending"], "evidence checks"),
    }
    for claim in release["claims"]:
        replacement = replacements.get(claim["id"])
        if replacement:
            claim["value"] = replacement[0]
    official = review["summary"]
    release["claims"].extend(
        [
            _claim(
                "mpb-indexed-official-records",
                "The stated number of evidence checks have an official DPWH document URL, but the source bytes are not archived.",
                official["indexed_unarchived_records"],
                "indexed records",
            ),
            _claim(
                "mpb-official-source-contracts",
                "The stated number of targeted contracts have at least one indexed official procurement source or a quarantined identity conflict.",
                official["contracts_with_official_sources"],
                "contracts",
            ),
            _claim(
                "mpb-identity-conflicts",
                "The stated number of targeted contracts are quarantined because official sources associate the same contract number with different project identities.",
                official["quarantined_contracts"],
                "contracts",
            ),
            _claim(
                "mpb-official-discovery-pending",
                "The stated number of targeted contracts still have no accepted official procurement source lead in this bounded search.",
                official["discovery_pending_contracts"],
                "contracts",
            ),
        ]
    )


def _public_sources(
    review: dict[str, Any], grouped: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    source_contracts: dict[str, set[str]] = defaultdict(set)
    source_states: dict[str, set[str]] = defaultdict(set)
    source_types: dict[str, set[str]] = defaultdict(set)
    for contract_id, records in grouped.items():
        for record in records:
            source_id = str(record["source_id"])
            source_contracts[source_id].add(contract_id)
            source_states[source_id].add(str(record["status"]))
            source_types[source_id].add(str(record.get("document_type") or "official document"))
    sources = []
    for attempt in review.get("source_manifest", []):
        source_id = str(attempt["source_id"])
        sources.append(
            {
                "source_id": source_id,
                "source_url": attempt["source_url"],
                "status": attempt["status"],
                "http_status": attempt.get("http_status"),
                "retry_eligible": bool(attempt.get("retry_eligible")),
                "contract_ids": sorted(source_contracts[source_id]),
                "record_states": sorted(source_states[source_id]),
                "document_types": sorted(source_types[source_id]),
                "archived_sha256": None,
            }
        )
    return sorted(sources, key=lambda item: item["source_id"])


def _extend_story(
    release: dict[str, Any], acquisition: dict[str, Any], review: dict[str, Any]
) -> None:
    summary = acquisition["summary"]
    official = review["summary"]
    limitations = {
        "official-index-boundary": "An official URL is not archived evidence until its bytes are acquired, hashed, parsed, and identity-checked.",
        "official-block-boundary": "The DPWH host returned HTTP 403 to this acquisition run. Busisi records the blocked attempt and retries later without treating the document as verified.",
        "identity-conflict-boundary": "A contract-number conflict is quarantined for resolution. It is not proof of fraud, corruption, or wrongdoing.",
    }
    existing = {item["id"] for item in release["limitations"]}
    release["limitations"].extend(
        {"id": identifier, "text": text}
        for identifier, text in limitations.items()
        if identifier not in existing
    )
    sections = [
        item for item in release["story"]["sections"] if item["id"] != "public-value-acquisition"
    ]
    sections.append(
        {
            "id": "public-value-acquisition",
            "section_type": "investigation_lead",
            "heading": "Official document leads are visible, but they are not yet verified files",
            "copy": [
                f"Busisi tracks {summary['task_count']:,} evidence checks for 43 selected projects. {official['contracts_with_official_sources']} contracts now have at least one indexed official procurement lead.",
                f"The bounded run produced {official['indexed_unarchived_records']} indexed records, but the DPWH host returned HTTP 403, so 0 official source files were archived or promoted as verified evidence.",
                f"{official['quarantined_contracts']} contract identities are quarantined and {official['discovery_pending_contracts']} contracts still need official-source discovery.",
            ],
            "claim_ids": [
                "mpb-acquisition-tasks",
                "mpb-indexed-official-records",
                "mpb-official-source-contracts",
                "mpb-identity-conflicts",
                "mpb-official-discovery-pending",
            ],
            "source_ids": [DPWH_SOURCE_ID],
            "visual_refs": [
                "chart_data.public_value_acquisition",
                "chart_data.official_procurement_evidence",
                "project_examples.public_value_candidates",
            ],
            "limitation_ids": [
                "acquisition-queue-boundary",
                "official-index-boundary",
                "official-block-boundary",
                "identity-conflict-boundary",
            ],
            "narration_eligible": False,
        }
    )
    release["story"]["sections"] = sections
    release["investigations"] = [
        item
        for item in release["investigations"]
        if item.get("calculation_id") != "mpb-public-value-acquisition-v1"
    ]
    release["investigations"].append(
        {
            "question": "What did the official procurement source search establish?",
            "result": (
                f"Official URLs were indexed for {official['contracts_with_official_sources']} of 43 contracts. "
                f"No source file was archived because the DPWH host returned HTTP 403. "
                f"{official['quarantined_contracts']} identity conflicts remain quarantined."
            ),
            "state": "evidence_gap",
            "calculation_id": CALCULATION_ID,
        }
    )


def build_official_procurement_release(
    base_release: dict[str, Any],
    acquisition: dict[str, Any],
    official_review: dict[str, Any],
    *,
    supersedes: dict[str, Any],
) -> dict[str, Any]:
    """Build version 6 with explicit indexed, blocked, and quarantined states."""

    release = deepcopy(base_release)
    release["metadata"].pop("files", None)
    release["metadata"].pop("package_sha256", None)
    candidate_ids = _candidate_ids(release)
    acquired = _validate_acquisition(acquisition, candidate_ids)
    grouped = _validate_review(official_review, candidate_ids)
    release["metadata"].update(
        {
            "version": 6,
            "methodology_version": CALCULATION_ID,
            "supersedes": deepcopy(supersedes),
        }
    )
    release["story"]["version"] = 6
    _replace_claims(release, acquisition, official_review)
    release["chart_data"]["public_value_acquisition"] = {
        **deepcopy(acquisition["summary"]),
        "checked_at": acquisition["checked_at"],
        "source_identities": deepcopy(acquisition["source_identities"]),
        "task_definitions": deepcopy(acquisition["task_definitions"]),
        "gate_counts": deepcopy(acquisition["gate_counts"]),
        "limitations": list(acquisition["limitations"]),
    }
    release["chart_data"]["official_procurement_evidence"] = {
        "checked_at": official_review["checked_at"],
        "catalog_sha256": official_review["catalog_sha256"],
        "source_catalog_count": official_review.get("source_catalog_count", 0),
        "archived_source_count": official_review.get("archived_source_count", 0),
        "blocked_source_count": official_review.get("blocked_source_count", 0),
        "summary": deepcopy(official_review["summary"]),
        "sources": _public_sources(official_review, grouped),
        "limitations": list(official_review.get("limitations", [])),
    }
    review_contracts = official_review["contracts"]
    for candidate in release["project_examples"]["public_value_candidates"]:
        contract_id = candidate["contract_id"]
        candidate["acquisition"] = deepcopy(acquired[contract_id])
        candidate["official_procurement"] = deepcopy(review_contracts[contract_id])
    _extend_story(release, acquisition, official_review)
    release["editorial_package"] = build_consumption_index(release["metadata"], release["sources"])
    return release
