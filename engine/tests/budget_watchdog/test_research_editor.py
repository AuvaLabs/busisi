import hashlib
import json
from copy import deepcopy
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


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("metadata", "metadata"),
        ("required_text", "story_id"),
        ("status", "status"),
        ("version", "version"),
        ("canonical", "canonical_url"),
        ("digest", "SHA-256"),
        ("date", "ISO date"),
        ("freshness_limit", "max_source_age_days"),
        ("editorial_ready", "editorial ready"),
        ("claims", "claims"),
        ("duplicate_claim", "duplicate claim"),
        ("claim_state", "evidence state"),
        ("limitations", "limitations"),
        ("duplicate_limit", "duplicate limitation"),
        ("findings", "findings"),
        ("finding_object", "finding"),
        ("finding_claim", "unknown claims"),
        ("story_pair", "published together"),
        ("story_status", "story must be ready"),
        ("story_identity", "story identity"),
        ("story_sections", "ordered sections"),
        ("story_copy", "section copy"),
        ("story_claims", "identify at least one claim"),
        ("story_source", "unknown source"),
        ("story_limitation", "unknown limitation"),
        ("story_visual", "outside the public package"),
        ("lead_boundary", "limited investigation lead"),
        ("package_status", "ready consumption index"),
        ("package_identity", "story_id does not match"),
    ],
)
def test_editor_fails_closed_for_malformed_release_contract(  # noqa: PLR0912, PLR0915
    case: str, message: str
) -> None:
    release = _release()
    if case == "metadata":
        release["metadata"] = None
    elif case == "required_text":
        release["metadata"]["story_id"] = ""
    elif case == "status":
        release["metadata"]["status"] = "draft"
    elif case == "version":
        release["metadata"]["version"] = 0
    elif case == "canonical":
        release["metadata"]["canonical_url"] = "http://example.test/story"
    elif case == "digest":
        release["metadata"]["source_artifact_sha256"] = "bad"
    elif case == "date":
        release["metadata"]["published_at"] = "today"
    elif case == "freshness_limit":
        release["metadata"]["max_source_age_days"] = True
    elif case == "editorial_ready":
        release["metadata"]["editorial_ready"] = False
    elif case == "claims":
        release["claims"] = []
    elif case == "duplicate_claim":
        release["claims"].append(deepcopy(release["claims"][0]))
    elif case == "claim_state":
        release["claims"][0]["evidence_state"] = "maybe"
    elif case == "limitations":
        release["limitations"] = []
    elif case == "duplicate_limit":
        release["limitations"].append(deepcopy(release["limitations"][0]))
    elif case == "findings":
        release["findings"] = None
    elif case == "finding_object":
        release["findings"] = ["bad"]
    elif case == "finding_claim":
        release["findings"][0]["claim_ids"] = ["missing"]
    elif case == "story_pair":
        del release["editorial_package"]
    elif case == "story_status":
        release["story"]["editorial_status"] = "draft"
    elif case == "story_identity":
        release["story"]["story_id"] = "wrong"
    elif case == "story_sections":
        release["story"]["sections"] = []
    elif case == "story_copy":
        release["story"]["sections"][0]["copy"] = []
    elif case == "story_claims":
        release["story"]["sections"][0]["claim_ids"] = []
    elif case == "story_source":
        release["story"]["sections"][0]["source_ids"] = ["missing"]
    elif case == "story_limitation":
        release["story"]["sections"][0]["limitation_ids"] = ["missing"]
    elif case == "story_visual":
        release["story"]["sections"][0]["visual_refs"] = ["private.notes"]
    elif case == "lead_boundary":
        release["story"]["sections"][1]["section_type"] = "finding"
    elif case == "package_status":
        release["editorial_package"]["status"] = "draft"
    else:
        release["editorial_package"]["story_id"] = "wrong"

    with pytest.raises(ValueError, match=message):
        validate_research_release(release)


def test_writer_refuses_nonempty_output_and_verifier_detects_tampering(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep")
    with pytest.raises(FileExistsError, match="empty"):
        write_research_release(_release(), occupied)

    package = tmp_path / "package"
    write_research_release(_release(), package)
    (package / "claims.json").write_text("[]")
    with pytest.raises(ValueError, match="failed authentication"):
        verify_published_package(package)

    with pytest.raises(ValueError, match="manifest is missing"):
        verify_published_package(tmp_path / "missing")
