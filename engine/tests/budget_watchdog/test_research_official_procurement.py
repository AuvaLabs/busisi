import json
from copy import deepcopy
from pathlib import Path

import pytest

from engine.budget_watchdog.research_editor import validate_research_release
from engine.budget_watchdog.research_official_procurement import (
    build_official_procurement_release,
)

ROOT = Path(__file__).resolve().parents[3]
V5 = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v5"
)


def _release() -> dict:
    mapping = {
        "metadata": "manifest.json",
        "claims": "claims.json",
        "findings": "findings.json",
        "investigations": "investigations.json",
        "chart_data": "chart-data.json",
        "project_examples": "project-examples.json",
        "sources": "sources.json",
        "limitations": "limitations.json",
        "story": "story.json",
        "editorial_package": "editorial-package.json",
    }
    return {
        key: json.loads((V5 / filename).read_text(encoding="utf-8"))
        for key, filename in mapping.items()
    }


def _inputs(base: dict) -> tuple[dict, dict]:
    candidates = deepcopy(base["project_examples"]["public_value_candidates"])
    contract_ids = [item["contract_id"] for item in candidates]
    first, second = contract_ids[:2]
    for item in candidates:
        item["acquisition"]["status_counts"] = {"pending": 22}
    candidates[0]["acquisition"]["status_counts"] = {
        "indexed_unarchived": 1,
        "pending": 21,
    }
    candidates[1]["acquisition"]["status_counts"] = {
        "quarantined": 1,
        "pending": 21,
    }
    acquisition = {
        "checked_at": "2026-11-05T18:41:38+00:00",
        "source_identities": {"official_procurement_review_sha256": "a" * 64},
        "task_definitions": deepcopy(
            base["chart_data"]["public_value_acquisition"]["task_definitions"]
        ),
        "gate_counts": {"cost_delivery": {"indexed_unarchived": 1, "quarantined": 1}},
        "limitations": ["Indexed URLs are not archived evidence."],
        "summary": {
            "candidate_count": 43,
            "task_count": 946,
            "verified_archived": 0,
            "official_summary_archived": 0,
            "indexed_unarchived": 1,
            "secondary_exact": 0,
            "source_media_archived": 0,
            "pending": 944,
            "quarantined": 1,
        },
        "candidates": [item["acquisition"] for item in candidates],
    }
    contracts = {
        contract_id: {"state": "discovery_pending", "record_count": 0, "source_ids": []}
        for contract_id in contract_ids
    }
    contracts[first] = {
        "state": "official_source_indexed",
        "record_count": 1,
        "source_ids": ["dpwh-test-app"],
    }
    contracts[second] = {
        "state": "source_conflict_quarantined",
        "record_count": 1,
        "source_ids": ["dpwh-test-pmr"],
    }
    review = {
        "schema_version": 1,
        "checked_at": "2026-11-05T18:41:38+00:00",
        "catalog_sha256": "b" * 64,
        "source_catalog_count": 2,
        "archived_source_count": 0,
        "blocked_source_count": 2,
        "summary": {
            "targeted_contracts": 43,
            "contracts_with_official_sources": 2,
            "official_artifact_records": 0,
            "official_summary_records": 0,
            "indexed_unarchived_records": 1,
            "quarantined_contracts": 1,
            "discovery_pending_contracts": 41,
        },
        "contracts": contracts,
        "records": [
            {
                "contract_id": first,
                "evidence_type": "procurement_plan",
                "status": "indexed_unarchived",
                "source_id": "dpwh-test-app",
                "source_url": "https://www.dpwh.gov.ph/dpwh/test-app.pdf",
                "artifact_sha256": None,
                "http_status": 403,
                "retry_eligible": True,
                "document_type": "annual_procurement_plan",
                "limitation": "The official file is indexed but not archived.",
            },
            {
                "contract_id": second,
                "evidence_type": "procurement_monitoring_report",
                "status": "source_conflict_quarantined",
                "source_id": "dpwh-test-pmr",
                "source_url": "https://www.dpwh.gov.ph/dpwh/test-pmr.pdf",
                "artifact_sha256": None,
                "http_status": 403,
                "retry_eligible": True,
                "document_type": "procurement_monitoring_report",
                "limitation": "Official sources associate this number with different projects.",
            },
        ],
        "source_manifest": [
            {
                "source_id": "dpwh-test-app",
                "source_url": "https://www.dpwh.gov.ph/dpwh/test-app.pdf",
                "status": "blocked",
                "http_status": 403,
                "retry_eligible": True,
            },
            {
                "source_id": "dpwh-test-pmr",
                "source_url": "https://www.dpwh.gov.ph/dpwh/test-pmr.pdf",
                "status": "blocked",
                "http_status": 403,
                "retry_eligible": True,
            },
        ],
        "limitations": ["Indexed URLs are not archived evidence."],
    }
    return acquisition, review


def test_builds_v6_with_indexed_sources_and_quarantined_conflicts() -> None:
    base = _release()
    acquisition, review = _inputs(base)
    release = build_official_procurement_release(
        base,
        acquisition,
        review,
        supersedes={
            "version": 5,
            "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v5/manifest.json",
            "package_sha256": "5" * 64,
        },
    )

    claims = {item["id"]: item for item in release["claims"]}
    assert release["metadata"]["version"] == 6
    assert claims["mpb-indexed-official-records"]["value"] == 1
    assert claims["mpb-official-source-contracts"]["value"] == 2
    assert claims["mpb-identity-conflicts"]["value"] == 1
    assert (
        release["chart_data"]["official_procurement_evidence"]["sources"][0]["status"] == "blocked"
    )
    assert (
        release["project_examples"]["public_value_candidates"][0]["official_procurement"]["state"]
        == "official_source_indexed"
    )
    assert release["story"]["sections"][-1]["narration_eligible"] is False
    validate_research_release(release)


def test_rejects_review_candidate_mismatch() -> None:
    base = _release()
    acquisition, review = _inputs(base)
    review["contracts"].pop(next(iter(review["contracts"])))

    with pytest.raises(ValueError, match="candidate set"):
        build_official_procurement_release(
            base,
            acquisition,
            review,
            supersedes={
                "version": 5,
                "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v5/manifest.json",
                "package_sha256": "5" * 64,
            },
        )
