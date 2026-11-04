import hashlib
import json
from pathlib import Path

import pytest

from engine.budget_watchdog.research_package import (
    build_multipurpose_release,
    is_multipurpose_building,
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
