import json
from pathlib import Path

from engine.budget_watchdog.research_editor import verify_published_package
from engine.budget_watchdog.research_stage_changes import build_stage_change_release
from engine.budget_watchdog.stage_changes import StageChange


def _record(
    record_id: str,
    change_type: str,
    *,
    dataset: str = "dpwh",
    nep: int = 0,
    house: int = 10_000_00,
    review_status: str = "candidate",
) -> StageChange:
    return StageChange(
        record_id=record_id,
        fiscal_year=2027,
        dataset=dataset,
        title=f"Project {record_id}",
        program="Program",
        pap="PAP",
        region="Region III",
        office="Example Office",
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


def _source_context() -> tuple[dict, dict]:
    overview = {
        "meta": {"source_commit": "a" * 40, "built_at": "2026-11-03T00:00:00Z"},
        "data": {"documents": []},
    }
    manifest = {
        "retrieved_at": "2026-11-03T01:00:00+00:00",
        "overview_sha256": "c" * 64,
        "source_commit": "a" * 40,
        "documents": [],
    }
    return overview, manifest


def test_stage_change_story_separates_counts_review_leads_and_quarantine() -> None:
    overview, manifest = _source_context()
    records = [
        _record("dpwh:1", "house_only"),
        _record("dpwh:2", "house_only", review_status="quarantine"),
        _record("dpwh:3", "unchanged", nep=10_000_00),
        _record("fmr:1", "increased", dataset="fmr", nep=5_000_00),
        _record("fmr:2", "nep_only", dataset="fmr", nep=7_000_00, house=0),
    ]

    release = build_stage_change_release(
        records,
        overview=overview,
        snapshot_manifest=manifest,
        published_at="2026-11-04",
    )
    claims = {item["id"]: item for item in release["claims"]}

    assert claims["stage-total-records"]["value"] == 5
    assert claims["stage-house-only"]["value"] == 2
    assert claims["stage-publishable-house-only"]["value"] == 1
    assert claims["stage-quarantined"]["value"] == 1
    lead = next(section for section in release["story"]["sections"] if section["id"] == "house-only-review")
    assert lead["narration_eligible"] is False
    assert lead["section_type"] == "investigation_lead"
    assert release["editorial_package"]["status"] == "ready_for_consumption"
    assert release["chart_data"]["change_types"]["house_only"]["count"] == 2


def test_published_stage_change_package_matches_reconciled_controls() -> None:
    root = Path(__file__).resolve().parents[3]
    package = (
        root
        / "cloudflare"
        / "busisi"
        / "public"
        / "data"
        / "research"
        / "fy2027-nep-house-changes"
        / "v1"
    )
    manifest = verify_published_package(package)
    claims = {
        item["id"]: item
        for item in json.loads((package / "claims.json").read_text())
    }

    assert manifest["package_sha256"] == (
        "7cd2b9fc154cdae4228232fae5fd2446bb2b88c5bd82f56823d9e1afd77cca1a"
    )
    assert claims["stage-total-records"]["value"] == 20_431
    assert claims["stage-house-only"]["value"] == 6_954
    assert claims["stage-publishable-house-only"]["value"] == 6_565
    assert claims["stage-quarantined"]["value"] == 426
