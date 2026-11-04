import hashlib
import json
from pathlib import Path

import pytest

from engine.budget_watchdog.research_editor import verify_published_package
from engine.budget_watchdog.research_stage_changes import (
    build_stage_change_release,
    load_stage_change_snapshot,
)
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
        "meta": {
            "source_commit": "a" * 40,
            "built_at": "2026-11-03T00:00:00Z",
            "source_repo": "https://github.com/example/research",
        },
        "data": {
            "documents": [{
                "key": "nep-sample",
                "stage": "nep",
                "title": "NEP sample annex",
                "pdf_url": "https://budget-assets.bettergov.ph/nep-sample.pdf",
                "source_url": "https://www.dbm.gov.ph/nep-sample.pdf",
                "sha256": "d" * 64,
            }],
        },
    }
    manifest = {
        "retrieved_at": "2026-11-03T01:00:00+00:00",
        "overview_sha256": "c" * 64,
        "source_commit": "a" * 40,
        "documents": [{
            "key": "nep-sample",
            "mirror_url": "https://budget-assets.bettergov.ph/nep-sample.pdf",
            "sha256": "d" * 64,
        }],
    }
    return overview, manifest


def _snapshot(path: Path) -> None:
    row = {
        "id": "record:1",
        "dataset": "dpwh",
        "title": "Construction of Sample Bridge",
        "program": "Network Development Program",
        "pap": "Bridge Program",
        "region": "Region III",
        "office": "Sample District Engineering Office",
        "bridge_group": "increased",
        "group_label": "Higher in the House bill",
        "held": False,
        "confidence": 1,
        "nep_php": 100,
        "house_php": 150,
        "delta_php": 50,
        "nep_page": 10,
        "hgab3_page": 20,
        "pdf_url": {
            "nep": "https://budget-assets.bettergov.ph/nep.pdf#page=10",
            "hgab3": "https://budget-assets.bettergov.ph/house.pdf#page=20",
        },
        "url": "https://budget.bettergov.ph/hgab/2027/dpwh/p/record%3A1",
    }
    page = json.dumps({
        "meta": {
            "dataset": "hgab",
            "fiscal_year": 2027,
            "currency": "PHP",
            "scale": "pesos",
            "source_commit": "a" * 40,
            "dataset_key": "dpwh",
            "house_stage": "hgab3",
        },
        "data": {
            "total": 1,
            "sums": {
                "nep_php": 100,
                "hgab3_php": 150,
                "unconfirmed_rows": 0,
            },
            "rows": [row],
            "next_offset": None,
        },
    }).encode()
    overview = json.dumps({
        "meta": {"source_commit": "a" * 40},
        "data": {
            "datasets": [{
                "key": "dpwh",
                "house_stage": "hgab3",
                "bridge": {
                    "groups": {
                        "increased": {"rows": 1},
                        "scope_review": {"rows": 0},
                    },
                },
                "totals": {"nep_php": 100, "hgab3_php": 150},
                "unconfirmed_rows": 0,
            }],
        },
    }).encode()
    document = b"%PDF authenticated test"
    (path / "pages").mkdir(parents=True)
    (path / "documents").mkdir()
    (path / "pages" / "page.json").write_bytes(page)
    (path / "overview.json").write_bytes(overview)
    (path / "documents" / "house.pdf").write_bytes(document)
    manifest = {
        "overview_sha256": hashlib.sha256(overview).hexdigest(),
        "source_commit": "a" * 40,
        "pages": [{
            "path": "pages/page.json",
            "sha256": hashlib.sha256(page).hexdigest(),
            "record_count": 1,
        }],
        "documents": [{
            "key": "house",
            "sha256": hashlib.sha256(document).hexdigest(),
            "byte_size": len(document),
        }],
    }
    (path / "snapshot-manifest.json").write_text(json.dumps(manifest))


def test_loads_and_authenticates_a_complete_stage_change_snapshot(tmp_path: Path) -> None:
    _snapshot(tmp_path)

    records, overview, manifest = load_stage_change_snapshot(tmp_path)

    assert [record.record_id for record in records] == ["dpwh:record:1"]
    assert overview["data"]["datasets"][0]["key"] == "dpwh"
    assert manifest["source_commit"] == "a" * 40


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("overview_digest", "overview failed authentication"),
        ("page_digest", "page failed authentication"),
        ("page_count", "page count changed"),
        ("source_commit", "source commit changed"),
        ("missing_document", "document is missing"),
        ("document_digest", "document failed authentication"),
    ],
)
def test_stage_snapshot_fails_closed_on_authentication_errors(
    tmp_path: Path, mutation: str, message: str
) -> None:
    _snapshot(tmp_path)
    manifest_path = tmp_path / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "overview_digest":
        manifest["overview_sha256"] = "0" * 64
    elif mutation == "page_digest":
        manifest["pages"][0]["sha256"] = "0" * 64
    elif mutation == "page_count":
        manifest["pages"][0]["record_count"] = 2
    elif mutation == "source_commit":
        manifest["source_commit"] = "b" * 40
    elif mutation == "missing_document":
        (tmp_path / "documents" / "house.pdf").unlink()
    else:
        manifest["documents"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match=message):
        load_stage_change_snapshot(tmp_path)


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
