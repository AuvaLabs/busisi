import json
from pathlib import Path

from engine.budget_watchdog.research_change_concentration import (
    build_change_concentration_release,
)
from engine.budget_watchdog.research_editor import verify_published_package
from engine.budget_watchdog.stage_changes import StageChange


def _record(
    record_id: str,
    change_type: str,
    *,
    region: str,
    office: str,
    program: str,
    dataset: str = "dpwh",
    nep: int = 0,
    house: int = 1_000_00,
    review_status: str = "candidate",
) -> StageChange:
    return StageChange(
        record_id=record_id,
        fiscal_year=2027,
        dataset=dataset,
        title=f"Project {record_id}",
        program=program,
        pap="PAP",
        region=region,
        office=office,
        change_type=change_type,
        change_label=change_type.replace("_", " "),
        review_status=review_status,
        held=review_status == "quarantine",
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


def _context() -> tuple[dict, dict]:
    overview = {
        "meta": {
            "source_commit": "a" * 40,
            "built_at": "2026-10-26T00:00:00Z",
            "source_repo": "https://github.com/example/research",
        },
        "data": {"documents": []},
    }
    manifest = {
        "retrieved_at": "2026-11-03T01:00:00+00:00",
        "overview_sha256": "c" * 64,
        "source_commit": "a" * 40,
        "documents": [],
    }
    return overview, manifest


def test_concentration_release_keeps_group_rankings_and_review_boundaries() -> None:
    overview, manifest = _context()
    rows = [
        _record("one", "house_only", region="Region I", office="Office A", program="Roads"),
        _record("two", "house_only", region="Region I", office="Office A", program="Roads"),
        _record(
            "held",
            "house_only",
            region="Region II",
            office="Office B",
            program="Flood",
            review_status="quarantine",
        ),
        _record(
            "increase",
            "increased",
            region="Region II",
            office="Office B",
            program="Flood",
            nep=500_00,
            house=900_00,
        ),
        _record(
            "decrease",
            "decreased",
            region="Region III",
            office="Office C",
            program="Bridges",
            nep=800_00,
            house=300_00,
        ),
        _record(
            "same",
            "unchanged",
            region="Region III",
            office="Office C",
            program="Bridges",
            nep=200_00,
            house=200_00,
        ),
    ]

    release = build_change_concentration_release(
        rows,
        overview=overview,
        snapshot_manifest=manifest,
        published_at="2026-11-05",
    )
    claims = {item["id"]: item for item in release["claims"]}

    assert claims["concentration-changed-rows"]["value"] == 5
    assert claims["concentration-house-only"]["value"] == 3
    assert claims["concentration-quarantined"]["value"] == 1
    assert release["chart_data"]["regions"][0]["label"] == "Region I"
    assert release["chart_data"]["regions"][0]["house_only"] == 2
    assert release["chart_data"]["programs"][0]["label"] == "Roads"
    assert release["story"]["sections"][1]["narration_eligible"] is False
    assert release["editorial_package"]["status"] == "ready_for_consumption"


def test_published_concentration_package_matches_release_controls() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "fy2027-change-concentration"
        / "v1"
    )
    manifest = verify_published_package(package)
    claims = {
        item["id"]: item
        for item in json.loads((package / "claims.json").read_text())
    }

    assert manifest["package_sha256"] == (
        "b2a09440ee641fd5f6693401e7f18ed0392b83451e0afd94361a8dc5d6f979ed"
    )
    assert manifest["story_id"] == "fy2027-change-concentration-2026"
    assert claims["concentration-total-rows"]["value"] == 20_431
    assert claims["concentration-changed-rows"]["value"] == 9_283
    assert claims["concentration-house-only"]["value"] == 6_954
    assert claims["concentration-quarantined"]["value"] == 426
