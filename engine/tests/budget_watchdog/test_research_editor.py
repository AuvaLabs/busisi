import hashlib
import json
from pathlib import Path

import pytest

from engine.budget_watchdog.research_editor import (
    build_consumption_index,
    validate_research_release,
    verify_published_package,
    write_research_release,
)


def _release() -> dict:
    metadata = {
        "schema_version": "1.1",
        "story_id": "test-story-2027",
        "slug": "test-story",
        "version": 1,
        "status": "published",
        "editorial_ready": True,
        "headline": "What changed?",
        "canonical_url": "https://busisi.org/research/test-story/",
        "published_at": "2026-11-04",
        "data_cutoff": "2026-11-03",
        "source_checked_at": "2026-11-03",
        "max_source_age_days": 7,
        "methodology_version": "test-v1",
        "source_artifact_sha256": "a" * 64,
        "supersedes": None,
    }
    sources = [
        {
            "id": "source-1",
            "publisher": "Example Office",
            "access_provider": "Example Archive",
            "source_kind": "curated_official_extract",
            "scope": "Test records",
            "retrieved_at": "2026-11-03",
            "source_url": "https://example.gov.ph/data.json",
            "sha256": "a" * 64,
        }
    ]
    limitations = [{"id": "source-limit", "text": "This is a test limitation."}]
    release = {
        "metadata": metadata,
        "claims": [
            {
                "id": "checked-count",
                "statement": "Ten records passed the test.",
                "value": 10,
                "unit": "records",
                "scope": "Test records",
                "evidence_state": "verified",
                "calculation_id": "test-v1",
                "source_ids": ["source-1"],
                "limitations": [],
            },
            {
                "id": "review-lead",
                "statement": "One record needs review.",
                "value": 1,
                "unit": "records",
                "scope": "Test records",
                "evidence_state": "review_candidate",
                "calculation_id": "test-v1",
                "source_ids": ["source-1"],
                "limitations": ["A match does not prove wrongdoing."],
            },
        ],
        "findings": [
            {
                "id": "count",
                "title": "Ten records passed",
                "result": "Ten records passed the test.",
                "claim_ids": ["checked-count"],
                "evidence_state": "verified",
            }
        ],
        "investigations": [],
        "chart_data": {"counts": {"checked": 10}},
        "project_examples": {"records": []},
        "sources": sources,
        "limitations": limitations,
        "story": {
            "schema_version": "1.0",
            "story_id": metadata["story_id"],
            "version": 1,
            "editorial_status": "ready",
            "headline": metadata["headline"],
            "deck": "A test story.",
            "audience": "Filipino public",
            "language": "en-PH",
            "canonical_url": metadata["canonical_url"],
            "data_cutoff": metadata["data_cutoff"],
            "source_ids": ["source-1"],
            "sections": [
                {
                    "id": "answer",
                    "section_type": "finding",
                    "heading": "Direct answer",
                    "copy": ["Ten records passed the test."],
                    "claim_ids": ["checked-count"],
                    "source_ids": ["source-1"],
                    "visual_refs": ["chart_data.counts"],
                    "limitation_ids": ["source-limit"],
                    "narration_eligible": True,
                },
                {
                    "id": "lead",
                    "section_type": "investigation_lead",
                    "heading": "Question to check",
                    "copy": ["One record needs review."],
                    "claim_ids": ["review-lead"],
                    "source_ids": ["source-1"],
                    "visual_refs": ["project_examples.records"],
                    "limitation_ids": ["source-limit"],
                    "narration_eligible": False,
                },
            ],
        },
    }
    release["editorial_package"] = build_consumption_index(metadata, sources)
    return release


def test_generic_editor_writes_and_reverifies_an_authenticated_package(tmp_path: Path) -> None:
    release = _release()
    manifest = write_research_release(release, tmp_path)
    verified = verify_published_package(tmp_path)

    assert verified["package_sha256"] == manifest["package_sha256"]
    assert {entry["path"] for entry in manifest["files"]} == {
        "chart-data.json",
        "claims.json",
        "editorial-package.json",
        "findings.json",
        "investigations.json",
        "limitations.json",
        "project-examples.json",
        "sources.json",
        "story.json",
    }
    identity = "".join(
        f"{entry['path']}\0{entry['sha256']}\n" for entry in manifest["files"]
    ).encode()
    assert hashlib.sha256(identity).hexdigest() == manifest["package_sha256"]
    assert json.loads((tmp_path / "story.json").read_text())["editorial_status"] == "ready"


def test_editor_rejects_stale_source_check_at_publication() -> None:
    release = _release()
    release["metadata"]["source_checked_at"] = "2026-10-01"

    with pytest.raises(ValueError, match="stale"):
        validate_research_release(release)


def test_editor_rejects_review_candidate_as_factual_narration() -> None:
    release = _release()
    release["story"]["sections"][0]["claim_ids"] = ["review-lead"]

    with pytest.raises(ValueError, match="review candidate"):
        validate_research_release(release)


def test_editor_rejects_missing_consumption_link() -> None:
    release = _release()
    del release["editorial_package"]["files"]["sources"]

    with pytest.raises(ValueError, match="every release data file"):
        validate_research_release(release)
