import hashlib
import json

import pytest

from engine.budget_watchdog.hgab_bundle import build_hgab_bundle


def _row(record_id: str, *, nep: int, house: int, change: str) -> dict:
    return {
        "id": record_id,
        "dataset": "dpwh",
        "title": f"Project {record_id}",
        "program": "Network Development",
        "pap": "Bridge Program",
        "region": "Region III",
        "office": "Sample DEO",
        "bridge_group": change,
        "group_label": change.replace("_", " "),
        "held": False,
        "confidence": 1,
        "nep_php": nep,
        "house_php": house,
        "delta_php": house - nep,
        "nep_page": 1,
        "hgab3_page": 2,
        "pdf_url": {
            "nep": "https://budget.example/nep.pdf#page=1",
            "hgab3": "https://budget.example/house.pdf#page=2",
        },
        "url": f"https://budget.example/changes/{record_id}",
    }


def _write_snapshot(tmp_path, rows: list[dict], *, expected_house: int | None = None):
    snapshot = tmp_path / "snapshot"
    pages = snapshot / "pages"
    pages.mkdir(parents=True)
    payload = json.dumps(
        {
            "meta": {
                "dataset": "hgab",
                "fiscal_year": 2027,
                "currency": "PHP",
                "scale": "pesos",
                "source_commit": "a" * 40,
                "dataset_key": "dpwh",
                "house_stage": "hgab3",
            },
            "data": {"total": len(rows), "rows": rows, "next_offset": None},
        }
    ).encode()
    page_path = pages / "dpwh-000000.json"
    page_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    groups = {
        name: {"rows": sum(row["bridge_group"] == name for row in rows)}
        for name in ("house_only", "nep_only", "unchanged", "increased", "decreased", "scope_review")
    }
    overview = {
        "data": {
            "documents": [],
            "datasets": [
                {
                    "key": "dpwh",
                    "house_stage": "hgab3",
                    "totals": {
                        "nep_php": sum(row["nep_php"] for row in rows),
                        "hgab3_php": expected_house
                        if expected_house is not None
                        else sum(row["house_php"] for row in rows),
                    },
                    "unconfirmed_rows": 0,
                    "bridge": {"groups": groups},
                }
            ],
        }
    }
    (snapshot / "overview.json").write_text(json.dumps(overview), encoding="utf-8")
    (snapshot / "snapshot-manifest.json").write_text(
        json.dumps({"pages": [{"path": "pages/dpwh-000000.json", "sha256": digest}]}),
        encoding="utf-8",
    )
    return snapshot


def test_builds_reconciled_stage_change_d1_bundle(tmp_path) -> None:
    snapshot = _write_snapshot(
        tmp_path,
        [
            _row("one", nep=100, house=150, change="increased"),
            _row("two", nep=200, house=120, change="decreased"),
        ],
    )
    output = tmp_path / "bundle"

    result = build_hgab_bundle(snapshot, output, chunk_rows=1)

    assert result.record_count == 2
    assert result.quarantine_count == 0
    assert result.sql_chunks == 3
    assert len(result.manifest_sha256) == 64
    assert "INSERT OR REPLACE INTO stage_change_items" in (
        output / "chunks" / "100-stage-changes-0001.sql"
    ).read_text(encoding="utf-8")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == "2"
    assert len(manifest["chunk_sha256"]) == 3


def test_bundle_rejects_digest_and_control_total_mismatches(tmp_path) -> None:
    snapshot = _write_snapshot(
        tmp_path,
        [_row("one", nep=100, house=150, change="increased")],
        expected_house=999,
    )
    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        build_hgab_bundle(snapshot, tmp_path / "digest-bundle")

    payload = (snapshot / "pages" / "dpwh-000000.json").read_bytes()
    manifest["pages"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="House control total"):
        build_hgab_bundle(snapshot, tmp_path / "control-bundle")


def test_bundle_rejects_invalid_chunk_size(tmp_path) -> None:
    snapshot = _write_snapshot(tmp_path, [_row("one", nep=100, house=100, change="unchanged")])

    with pytest.raises(ValueError, match="chunk_rows"):
        build_hgab_bundle(snapshot, tmp_path / "bundle", chunk_rows=0)
