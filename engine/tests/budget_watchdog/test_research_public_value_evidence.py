import pytest

from engine.budget_watchdog.research_public_value_evidence import (
    build_public_value_evidence_release,
)


def _row(
    contract_id: str,
    *,
    status: str,
    budget: int,
    year: str,
    latitude: float,
    longitude: float,
) -> dict:
    return {
        "contractId": contract_id,
        "description": f"CONSTRUCTION OF MULTI-PURPOSE BUILDING, {contract_id}",
        "status": status,
        "budget": budget,
        "infraYear": year,
        "location": {"province": "Example DEO", "region": "Region IV-A"},
        "latitude": latitude,
        "longitude": longitude,
        "hasSatelliteImage": contract_id == "25AA0001",
    }


def _benchmark_source() -> dict:
    return {
        "id": "dbm-technical-notes-2026",
        "publisher": "Department of Budget and Management",
        "access_provider": "Department of Budget and Management",
        "source_kind": "official_record",
        "scope": "Official 2026 education infrastructure budget benchmark",
        "modified": "2026-01-05",
        "retrieved_at": "2026-11-05",
        "origin_url": "https://www.dbm.gov.ph/",
        "source_url": "https://www.dbm.gov.ph/technical-notes.pdf",
        "sha256": "b" * 64,
    }


def _benchmark() -> dict:
    return {
        "id": "proposed-2026",
        "label": "2026 proposed technical-note target",
        "budget_centavos": 1_330_000_000_000,
        "physical_target": 4_869,
        "unit": "new classrooms",
        "source_id": "dbm-technical-notes-2026",
    }


def test_public_value_release_builds_a_bounded_project_evidence_queue() -> None:
    rows = [
        _row(
            "25AA0001",
            status="On-Going",
            budget=10_000_000,
            year="2025",
            latitude=14.5,
            longitude=121.0,
        ),
        _row(
            "23AA0001",
            status="Completed",
            budget=2_000_000,
            year="2023",
            latitude=14.5,
            longitude=121.0,
        ),
        _row(
            "25AA0002",
            status="For Procurement",
            budget=20_000_000,
            year="2025",
            latitude=14.6,
            longitude=121.1,
        ),
    ]
    release = build_public_value_evidence_release(
        rows,
        source_sha256="a" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-05",
        benchmark_sources=[_benchmark_source()],
        classroom_benchmarks=[_benchmark()],
        supersedes={
            "version": 3,
            "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v3/manifest.json",
            "package_sha256": "c" * 64,
        },
    )

    claims = {item["id"]: item for item in release["claims"]}
    candidates = {
        item["contract_id"]: item
        for item in release["project_examples"]["public_value_candidates"]
    }

    assert release["metadata"]["version"] == 4
    assert release["metadata"]["methodology_version"] == "mpb-public-value-evidence-v1"
    assert claims["mpb-public-value-candidates"]["value"] == 2
    assert claims["mpb-coordinate-history-candidates"]["value"] == 1
    assert claims["mpb-largest-budget-candidates"]["value"] == 2
    assert claims["mpb-fully-assessed-candidates"]["value"] == 0

    coordinate_lead = candidates["25AA0001"]
    assert coordinate_lead["selection_reasons"] == [
        "exact_coordinate_history",
        "largest_active_recorded_budget",
    ]
    assert coordinate_lead["coordinates_e6"] == {
        "latitude": 14_500_000,
        "longitude": 121_000_000,
    }
    assert coordinate_lead["gate_states"] == {
        "identity": "partial",
        "need": "not_in_snapshot",
        "location": "review_lead",
        "design": "not_in_snapshot",
        "cost_delivery": "partial",
    }
    assert coordinate_lead["related_completed_records"] == [
        {"contract_id": "23AA0001", "fiscal_year": 2023}
    ]
    assert coordinate_lead["source_image_state"] == "reported_available"
    assert candidates["25AA0002"]["gate_states"]["location"] == "partial"
    assert candidates["25AA0002"]["reader_url"] == "/contracts/25AA0002/"

    coverage = release["chart_data"]["public_value_evidence"]
    assert coverage["candidate_count"] == 2
    assert coverage["selection_overlap"] == 1
    assert coverage["fully_assessed"] == 0
    assert coverage["gate_counts"]["need"] == {"not_in_snapshot": 2}
    assert release["story"]["sections"][-1]["narration_eligible"] is False


def test_public_value_release_rejects_duplicate_candidate_rows() -> None:
    duplicate = _row(
        "25AA0001",
        status="On-Going",
        budget=10_000_000,
        year="2025",
        latitude=14.5,
        longitude=121.0,
    )

    with pytest.raises(ValueError, match="duplicate contract id"):
        build_public_value_evidence_release(
            [duplicate, dict(duplicate)],
            source_sha256="a" * 64,
            source_modified="2026-01-22",
            published_at="2026-11-05",
            benchmark_sources=[_benchmark_source()],
            classroom_benchmarks=[_benchmark()],
            supersedes={
                "version": 3,
                "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v3/manifest.json",
                "package_sha256": "c" * 64,
            },
        )
