import hashlib
import json
from pathlib import Path

import pytest

from engine.budget_watchdog.research_package import (
    build_multipurpose_release,
    is_multipurpose_building,
    validate_editorial_release,
    write_release_package,
)
from engine.budget_watchdog.research_sources import (
    ResearchEvidenceError,
    validate_release_evidence,
)


def _row(
    contract_id: str,
    description: str,
    *,
    year: str = "2025",
    status: str = "On-Going",
    budget: float = 5_000_000.00,
    latitude: float | None = 14.5,
    longitude: float | None = 121.0,
) -> dict[str, object]:
    return {
        "contractId": contract_id,
        "description": description,
        "status": status,
        "budget": budget,
        "infraYear": year,
        "location": {"province": "Example DEO", "region": "Region IV-A"},
        "latitude": latitude,
        "longitude": longitude,
        "hasSatelliteImage": True,
    }


def test_classifier_removes_program_heading_false_positives() -> None:
    assert not is_multipurpose_building(
        "BIP - MULTI-PURPOSE BUILDINGS/FACILITIES TO SUPPORT SOCIAL SERVICES - "
        "CONSTRUCTION OF AIRPORT FACILITY"
    )
    assert is_multipurpose_building(
        "BIP - MULTI-PURPOSE BUILDINGS/FACILITIES TO SUPPORT SOCIAL SERVICES - "
        "CONSTRUCTION OF MULTI-PURPOSE BUILDING, BARANGAY SAMPLE"
    )


def test_release_separates_status_work_type_and_existing_site_evidence() -> None:
    prior = _row(
        "23AA0001",
        "CONSTRUCTION OF MULTI-PURPOSE BUILDING, BARANGAY SAMPLE",
        year="2023",
        status="Completed",
    )
    rows = [
        prior,
        _row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY"),
        _row(
            "25AA0002",
            "REHABILITATION OF MULTI-PURPOSE BUILDING, SAMPLE CITY",
            latitude=14.6,
        ),
        _row(
            "25AA0003",
            "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY",
            status="For Procurement",
            budget=0,
            latitude=14.7,
        ),
        _row(
            "24AA0004",
            "CONSTRUCTION (COMPLETION) OF MULTI-PURPOSE BUILDING, SAMPLE CITY",
            year="2024",
            latitude=14.8,
        ),
        _row(
            "24AA0005",
            "CONSTRUCTION OF MULTI-PURPOSE BUILDING, BARANGAY SAMPLE",
            year="2024",
            latitude=14.5,
        ),
        _row(
            "24AA0006",
            "CONSTRUCTION OF CLASSROOM BUILDING",
            year="2024",
        ),
    ]
    release = build_multipurpose_release(
        rows,
        source_sha256="a" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
    )

    claims = {claim["id"]: claim for claim in release["claims"]}
    assert claims["mpb-total-records"]["value"] == 5
    assert claims["mpb-active-pipeline"]["value"] == 5
    assert claims["mpb-ongoing"]["value"] == 4
    assert claims["mpb-positive-active-budget"]["value"] == 4
    assert claims["mpb-existing-work-wording"]["value"] == 2
    assert claims["mpb-prior-coordinate-candidates"]["value"] == 2
    assert release["chart_data"]["work_types"]["repair_or_improvement"]["count"] == 1
    assert release["chart_data"]["work_types"]["completion_or_later_phase"]["count"] == 1
    assert release["chart_data"]["regions"][0]["active_pipeline"] == 5


def test_package_manifest_hashes_every_payload(tmp_path: Path) -> None:
    release = build_multipurpose_release(
        [_row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY")],
        source_sha256="b" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
    )
    manifest = write_release_package(release, tmp_path)

    assert manifest["status"] == "published"
    assert manifest["video_ready"] is True
    assert manifest["package_sha256"]
    for entry in manifest["files"]:
        payload = (tmp_path / entry["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        json.loads(payload)


def test_v2_package_contains_a_ready_story_and_consumption_index(tmp_path: Path) -> None:
    release = build_multipurpose_release(
        [_row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY")],
        source_sha256="c" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
        version=2,
        supersedes={
            "version": 1,
            "manifest_url": (
                "https://busisi.org/data/research/multipurpose-buildings/v1/manifest.json"
            ),
            "package_sha256": ("0ee46af783e1c700116014b671e8558550fe09cd102bd783e93eed1d74b22dd2"),
        },
    )
    manifest = write_release_package(release, tmp_path)

    assert manifest["version"] == 2
    assert {entry["path"] for entry in manifest["files"]} >= {
        "story.json",
        "editorial-package.json",
    }
    story = json.loads((tmp_path / "story.json").read_text())
    consumption = json.loads((tmp_path / "editorial-package.json").read_text())
    assert story["editorial_status"] == "ready"
    assert story["audience"] == "Filipino public"
    assert story["sections"]
    assert consumption["status"] == "ready_for_consumption"
    assert consumption["story_url"].endswith("/v2/story.json")
    assert consumption["manifest_url"].endswith("/v2/manifest.json")
    assert consumption["files"]["sources"].endswith("/v2/sources.json")


def test_editorial_story_rejects_review_leads_as_narration() -> None:
    release = build_multipurpose_release(
        [_row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY")],
        source_sha256="d" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
        version=2,
        supersedes={
            "version": 1,
            "manifest_url": (
                "https://busisi.org/data/research/multipurpose-buildings/v1/manifest.json"
            ),
            "package_sha256": ("0ee46af783e1c700116014b671e8558550fe09cd102bd783e93eed1d74b22dd2"),
        },
    )
    release["story"]["sections"][0]["claim_ids"] = ["mpb-prior-coordinate-candidates"]

    with pytest.raises(ValueError, match="review candidate"):
        validate_editorial_release(release)


def test_release_evidence_requires_direct_archived_sources() -> None:
    release = build_multipurpose_release(
        [_row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY")],
        source_sha256="b" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
    )
    validate_release_evidence(release)

    release["sources"][0]["source_url"] = "https://www.perplexity.ai/search/example"
    release["sources"][0]["source_kind"] = "discovery_service"
    with pytest.raises(ResearchEvidenceError, match="source_kind"):
        validate_release_evidence(release)


def test_release_evidence_rejects_unknown_claim_source() -> None:
    release = build_multipurpose_release(
        [_row("25AA0001", "CONSTRUCTION OF MULTI-PURPOSE BUILDING, SAMPLE CITY")],
        source_sha256="b" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-04",
    )
    release["claims"][0]["source_ids"] = ["missing-source"]

    with pytest.raises(ResearchEvidenceError, match="unknown source"):
        validate_release_evidence(release)


def test_published_package_matches_control_totals_and_hashes() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "multipurpose-buildings"
        / "v1"
    )
    manifest = json.loads((package / "manifest.json").read_text())
    claims = {item["id"]: item for item in json.loads((package / "claims.json").read_text())}

    assert (
        manifest["package_sha256"]
        == "0ee46af783e1c700116014b671e8558550fe09cd102bd783e93eed1d74b22dd2"
    )
    assert claims["mpb-total-records"]["value"] == 12_609
    assert claims["mpb-ongoing"]["value"] == 5_842
    assert claims["mpb-active-pipeline"]["value"] == 7_024
    for entry in manifest["files"]:
        payload = (package / entry["path"]).read_bytes()
        assert len(payload) == entry["bytes"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


def test_published_v2_editorial_package_is_complete_and_authenticated() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "multipurpose-buildings"
        / "v2"
    )
    manifest = json.loads((package / "manifest.json").read_text())
    story = json.loads((package / "story.json").read_text())
    consumption = json.loads((package / "editorial-package.json").read_text())

    assert manifest["version"] == 2
    assert manifest["package_sha256"] == (
        "bdf6fd74d6fc4a53a9c8025cc5e3214b31e61a4f84911020701a3f2709eadec1"
    )
    assert manifest["supersedes"]["package_sha256"] == (
        "0ee46af783e1c700116014b671e8558550fe09cd102bd783e93eed1d74b22dd2"
    )
    assert story["editorial_status"] == "ready"
    assert consumption["status"] == "ready_for_consumption"
    assert set(consumption["files"]) == {
        "chart_data",
        "claims",
        "findings",
        "investigations",
        "limitations",
        "project_examples",
        "sources",
    }
    for entry in manifest["files"]:
        payload = (package / entry["path"]).read_bytes()
        assert len(payload) == entry["bytes"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


def test_published_v3_reconciles_value_and_evidence_gates() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "multipurpose-buildings"
        / "v3"
    )
    manifest = json.loads((package / "manifest.json").read_text())
    claims = {
        item["id"]: item for item in json.loads((package / "claims.json").read_text())
    }
    chart_data = json.loads((package / "chart-data.json").read_text())

    assert manifest["version"] == 3
    assert manifest["package_sha256"] == (
        "ac0b7b30a0e353ffe7734e5929af2e12ca1540f2ee6871a6671347c6fcc72519"
    )
    assert manifest["supersedes"]["package_sha256"] == (
        "bdf6fd74d6fc4a53a9c8025cc5e3214b31e61a4f84911020701a3f2709eadec1"
    )
    assert claims["mpb-active-budget"]["value"] == 8_878_625_428_536
    assert claims["mpb-all-recorded-budget"]["value"] == 12_977_915_530_776
    assert claims["mpb-classroom-equivalent-low"]["value"] == 25_499
    assert claims["mpb-classroom-equivalent-high"]["value"] == 32_503
    assert claims["mpb-necessity-assessment"]["evidence_state"] == "not_supported"
    assert len(chart_data["assessment_gates"]) == 4
    for entry in manifest["files"]:
        payload = (package / entry["path"]).read_bytes()
        assert len(payload) == entry["bytes"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


def test_published_v4_exposes_bounded_project_value_evidence() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "multipurpose-buildings"
        / "v4"
    )
    manifest = json.loads((package / "manifest.json").read_text())
    claims = {
        item["id"]: item for item in json.loads((package / "claims.json").read_text())
    }
    chart_data = json.loads((package / "chart-data.json").read_text())
    examples = json.loads((package / "project-examples.json").read_text())

    assert manifest["version"] == 4
    assert manifest["package_sha256"] == (
        "4136d509893112797abbc3f1dd9931fd017276ade6ded8fdfc303d527e98cc4d"
    )
    assert manifest["supersedes"]["package_sha256"] == (
        "ac0b7b30a0e353ffe7734e5929af2e12ca1540f2ee6871a6671347c6fcc72519"
    )
    assert claims["mpb-public-value-candidates"]["value"] == 43
    assert claims["mpb-coordinate-history-candidates"]["value"] == 31
    assert claims["mpb-largest-budget-candidates"]["value"] == 12
    assert claims["mpb-fully-assessed-candidates"]["value"] == 0
    coverage = chart_data["public_value_evidence"]
    assert coverage["selection_overlap"] == 0
    assert coverage["gate_counts"]["need"] == {"not_in_snapshot": 43}
    assert coverage["gate_counts"]["location"] == {
        "partial": 12,
        "review_lead": 31,
    }
    assert len(examples["public_value_candidates"]) == 43
    assert all(
        item["assessment_state"] == "cannot_assess_from_current_evidence"
        for item in examples["public_value_candidates"]
    )
    for entry in manifest["files"]:
        payload = (package / entry["path"]).read_bytes()
        assert len(payload) == entry["bytes"]
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
