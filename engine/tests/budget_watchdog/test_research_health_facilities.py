from dataclasses import replace

import pytest

from engine.budget_watchdog.research_editor import validate_research_release
from engine.budget_watchdog.research_health_facilities import (
    build_health_facility_release,
)
from engine.budget_watchdog.stage_changes import StageChange


def _record(
    record_id: str,
    change_type: str,
    *,
    nep: int,
    house: int,
    region: str = "Region III",
    dataset: str = "hfep",
) -> StageChange:
    return StageChange(
        record_id=record_id,
        fiscal_year=2027,
        dataset=dataset,
        title=f"Health project {record_id}",
        program="Health Facilities Enhancement Program",
        pap="Capital outlays",
        region=region,
        office="Department of Health",
        change_type=change_type,
        change_label=change_type.replace("_", " "),
        review_status="candidate",
        held=False,
        confidence=1.0,
        nep_centavos=nep,
        house_centavos=house,
        difference_centavos=house - nep,
        source_url=f"https://budget.bettergov.ph/record/{record_id}",
        nep_pdf_url="https://budget-assets.bettergov.ph/nep.pdf" if nep else "",
        house_pdf_url="https://budget-assets.bettergov.ph/house.pdf" if house else "",
        nep_page=1 if nep else None,
        house_page=2 if house else None,
        source_commit="a" * 40,
        artifact_sha256="b" * 64,
    )


def _source_context() -> tuple[dict, dict]:
    documents = [
        {
            "key": "nep2027-hfep",
            "stage": "nep",
            "title": "NEP health facilities list",
            "pdf_url": "https://budget-assets.bettergov.ph/nep.pdf",
            "source_url": None,
            "sha256": "d" * 64,
        },
        {
            "key": "hb10858-2r-vol-ib",
            "stage": "house",
            "title": "House bill health facilities list, second reading",
            "pdf_url": "https://budget-assets.bettergov.ph/house-2r.pdf",
            "source_url": "https://www.congress.gov.ph/cso",
            "sha256": "e" * 64,
        },
        {
            "key": "hb10858-3r-vol-ib",
            "stage": "house",
            "title": "House bill health facilities list, third reading",
            "pdf_url": "https://budget-assets.bettergov.ph/house-3r.pdf",
            "source_url": "https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027",
            "sha256": "f" * 64,
        },
    ]
    overview = {
        "meta": {
            "source_commit": "a" * 40,
            "built_at": "2026-11-25T00:00:00Z",
            "source_repo": "https://github.com/bettergovph/budget",
        },
        "data": {"documents": documents},
    }
    manifest = {
        "retrieved_at": "2026-11-25T01:00:00+00:00",
        "overview_sha256": "c" * 64,
        "source_commit": "a" * 40,
        "documents": [
            {
                "key": document["key"],
                "mirror_url": document["pdf_url"],
                "sha256": document["sha256"],
            }
            for document in documents
        ],
    }
    return overview, manifest


def test_builds_question_led_health_facility_release_from_only_hfep_rows() -> None:
    overview, manifest = _source_context()
    records = [
        _record("hfep:1", "house_only", nep=0, house=300_000_00),
        _record("hfep:2", "nep_only", nep=500_000_00, house=0),
        _record("hfep:3", "increased", nep=100_000_00, house=200_000_00),
        _record("hfep:4", "decreased", nep=400_000_00, house=250_000_00),
        _record("hfep:5", "unchanged", nep=150_000_00, house=150_000_00),
        _record("dpwh:1", "house_only", nep=0, house=9_999_000_00, dataset="dpwh"),
    ]

    release = build_health_facility_release(
        records,
        overview=overview,
        snapshot_manifest=manifest,
        published_at="2026-11-25",
    )
    validate_research_release(release)
    claims = {item["id"]: item for item in release["claims"]}

    assert claims["health-total-records"]["value"] == 5
    assert claims["health-nep-total"]["value"] == 115_000_000
    assert claims["health-house-total"]["value"] == 90_000_000
    assert claims["health-net-movement"]["value"] == -25_000_000
    assert release["story"]["editorial_format"] == "question-led-v1"
    assert release["story"]["sections"][0]["heading"] == "The short answer"
    assert release["story"]["sections"][-1]["editorial_role"] == "limits"
    assert release["chart_data"]["change_types"]["house_only"]["count"] == 1
    assert len(release["project_examples"]["largest_absolute_changes"]) == 5
    assert {item["id"] for item in release["sources"]} == {
        "bettergov-hgab-overview-2027",
        "document-nep2027-hfep",
        "document-hb10858-2r-vol-ib",
        "document-hb10858-3r-vol-ib",
    }


def test_health_facility_release_rejects_missing_or_held_health_rows() -> None:
    overview, manifest = _source_context()
    non_health = [_record("dpwh:1", "house_only", nep=0, house=100, dataset="dpwh")]

    with pytest.raises(ValueError, match="no health-facility rows"):
        build_health_facility_release(
            non_health,
            overview=overview,
            snapshot_manifest=manifest,
            published_at="2026-11-25",
        )

    held = replace(
        _record("hfep:held", "house_only", nep=0, house=100),
        review_status="quarantine",
        held=True,
    )
    with pytest.raises(ValueError, match="held health-facility rows"):
        build_health_facility_release(
            [held],
            overview=overview,
            snapshot_manifest=manifest,
            published_at="2026-11-25",
        )
