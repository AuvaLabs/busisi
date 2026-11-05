from engine.budget_watchdog.research_multipurpose_value import (
    build_multipurpose_value_release,
)


def _row(
    contract_id: str,
    *,
    status: str,
    budget: int,
    description: str = "CONSTRUCTION OF MULTI-PURPOSE BUILDING, BARANGAY SAMPLE",
) -> dict:
    return {
        "contractId": contract_id,
        "description": description,
        "status": status,
        "budget": budget,
        "infraYear": "2025",
        "location": {"province": "Example DEO", "region": "Region IV-A"},
        "latitude": 14.5,
        "longitude": 121.0,
        "hasSatelliteImage": True,
    }


def _source(source_id: str, digest: str) -> dict:
    return {
        "id": source_id,
        "publisher": "Department of Budget and Management",
        "access_provider": "Department of Budget and Management",
        "source_kind": "official_record",
        "scope": "Official 2026 education infrastructure budget benchmark",
        "modified": "2026-01-05",
        "retrieved_at": "2026-11-05",
        "origin_url": "https://www.dbm.gov.ph/",
        "source_url": f"https://www.dbm.gov.ph/{source_id}.pdf",
        "sha256": digest,
    }


def _supersedes() -> dict:
    return {
        "version": 2,
        "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v2/manifest.json",
        "package_sha256": "c" * 64,
    }


def test_value_release_reconciles_budget_and_keeps_necessity_unresolved() -> None:
    rows = [
        _row("25AA0001", status="On-Going", budget=5_000_000),
        _row("25AA0002", status="For Procurement", budget=0),
        _row("25AA0003", status="Completed", budget=3_000_000),
    ]
    release = build_multipurpose_value_release(
        rows,
        source_sha256="a" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-05",
        benchmark_sources=[_source("dbm-technical-notes-2026", "b" * 64)],
        classroom_benchmarks=[
            {
                "id": "proposed-2026",
                "label": "2026 proposed technical-note target",
                "budget_centavos": 1_330_000_000_000,
                "physical_target": 4_869,
                "unit": "new classrooms",
                "source_id": "dbm-technical-notes-2026",
            }
        ],
        supersedes=_supersedes(),
    )

    claims = {item["id"]: item for item in release["claims"]}
    assert release["metadata"]["version"] == 3
    assert claims["mpb-all-recorded-budget"]["value"] == 800_000_000
    assert claims["mpb-active-budget"]["value"] == 500_000_000
    assert claims["mpb-completed-budget"]["value"] == 300_000_000
    assert claims["mpb-necessity-assessment"]["evidence_state"] == "not_supported"
    assert release["chart_data"]["opportunity_cost"][0]["equivalent_units"] == 1
    assert release["chart_data"]["assessment_gates"][0]["state"] == "not_in_snapshot"
    assert all(
        item["necessity_state"] == "not_assessable_from_snapshot"
        for item in release["project_examples"]["largest_active_recorded_budgets"]
    )


def test_value_release_uses_integer_floor_for_opportunity_cost() -> None:
    release = build_multipurpose_value_release(
        [_row("25AA0001", status="On-Going", budget=10)],
        source_sha256="a" * 64,
        source_modified="2026-01-22",
        published_at="2026-11-05",
        benchmark_sources=[_source("dbm-technical-notes-2026", "b" * 64)],
        classroom_benchmarks=[
            {
                "id": "integer-test",
                "label": "Integer test",
                "budget_centavos": 600,
                "physical_target": 4,
                "unit": "new classrooms",
                "source_id": "dbm-technical-notes-2026",
            }
        ],
        supersedes=_supersedes(),
    )

    comparison = release["chart_data"]["opportunity_cost"][0]
    assert comparison["equivalent_units"] == 6
    assert comparison["rounding"] == "floor"
