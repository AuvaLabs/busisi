import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.agency_budget_bundle import build_agency_budget_bundle
from engine.budget_watchdog.agency_budgets import (
    HOUSE_CONGRESS_SPECS,
    HOUSE_HEAD_SPECS,
    HOUSE_SPF_SPECS,
    HouseHeadSpec,
    parse_house_totals,
)


def _document_text(specs: tuple[HouseHeadSpec, ...], values: dict[str, int]) -> str:
    pages = [""] * max(spec.pdf_page for spec in specs)
    for spec in specs:
        pages[spec.pdf_page - 1] += (
            f"  12 TOTAL NEW APPROPRIATIONS, {spec.source_label} 12\n"
            f"  13 P 1,000 P {values[spec.record_id]:,} 13\n"
        )
    return "\f".join(pages)


def _snapshot(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    all_house_specs = HOUSE_HEAD_SPECS + HOUSE_SPF_SPECS + HOUSE_CONGRESS_SPECS
    values = {spec.record_id: (index + 1) * 1_000 for index, spec in enumerate(all_house_specs)}
    documents = {}
    manifest_documents = []
    for document_key in {spec.document_key for spec in all_house_specs}:
        specs = tuple(spec for spec in all_house_specs if spec.document_key == document_key)
        path = snapshot / f"{document_key}.txt"
        path.write_text(_document_text(specs, values), encoding="utf-8")
        documents[document_key] = path
        manifest_documents.append(
            {
                "key": document_key,
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pdf_sha256": document_key[0] * 64,
                "source_url": f"https://example.test/{document_key}.pdf",
            }
        )

    departments = []
    for index, spec in enumerate(HOUSE_HEAD_SPECS, start=1):
        departments.append(
            {
                "id": spec.record_id,
                "description": spec.public_name,
                "section": "1",
                "source_department_code": spec.record_id,
                "amount": index * 2_000,
                "base_amount": index * 1_500,
            }
        )
    departments.extend(
        [
            {
                "id": "SPF",
                "description": "Special Purpose Funds (SPF)",
                "section": "2",
                "source_department_code": "01",
                "amount": 900_000,
                "base_amount": 800_000,
            },
            {
                "id": "AUTO",
                "description": "Automatic Appropriations (AUTO)",
                "section": "2",
                "source_department_code": "04",
                "amount": 1_000_000,
                "base_amount": 950_000,
            },
        ]
    )
    departments_payload = {
        "meta": {
            "dataset": "nep",
            "fiscal_year": 2027,
            "baseline_year": 2026,
            "currency": "PHP",
            "scale": "pesos",
            "total_items": len(departments),
        },
        "data": departments,
    }
    overview_payload = {
        "meta": {
            "dataset": "nep",
            "fiscal_year": 2027,
            "baseline_year": 2026,
            "currency": "PHP",
            "scale": "pesos",
        },
        "data": {"national": {"amount": sum(row["amount"] for row in departments)}},
    }
    congress_payload = {
        "meta": {
            "dataset": "nep",
            "fiscal_year": 2027,
            "baseline_year": 2026,
            "currency": "PHP",
            "scale": "pesos",
            "department_id": "01",
        },
        "data": {
            "agencies": [
                {
                    "code": spec.record_id.rsplit(":", 1)[-1],
                    "description": spec.public_name,
                    "amount": 50_000 + index,
                    "base_amount": 40_000 + index,
                }
                for index, spec in enumerate(HOUSE_CONGRESS_SPECS)
            ]
        },
    }
    for name, payload in (
        ("nep-overview.json", overview_payload),
        ("nep-departments.json", departments_payload),
        ("nep-congress.json", congress_payload),
    ):
        path = snapshot / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifest_documents.append(
            {
                "key": name.removesuffix(".json"),
                "path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_url": f"https://budget.example/{name}",
            }
        )

    house_control = sum(values[spec.record_id] for spec in HOUSE_HEAD_SPECS)
    house_control += sum(values[spec.record_id] for spec in HOUSE_SPF_SPECS)
    manifest = {
        "fiscal_year": 2027,
        "baseline_year": 2026,
        "house_control_pesos": house_control,
        "documents": manifest_documents,
    }
    (snapshot / "snapshot-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return snapshot


def test_parses_wrapped_house_total_from_an_exact_source_page() -> None:
    spec = HouseHeadSpec(
        record_id="18",
        public_name="Department of Public Works and Highways",
        source_label="DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS",
        document_key="house-ib",
        pdf_page=3,
    )
    pages = [
        "",
        "",
        "12 TOTAL NEW APPROPRIATIONS, DEPARTMENT OF PUBLIC WORKS 12\n13 AND HIGHWAYS P 1,000 P 2,000 P 654,102,015,000 13",
    ]

    totals = parse_house_totals({"house-ib": "\f".join(pages)}, (spec,))

    assert totals[0].amount_pesos == 654_102_015_000
    assert totals[0].pdf_page == 3


def test_house_parser_rejects_missing_or_ambiguous_controls() -> None:
    spec = HouseHeadSpec("18", "DPWH", "DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS", "ib", 1)
    with pytest.raises(ValueError, match="page is unavailable"):
        parse_house_totals({}, (spec,))
    with pytest.raises(ValueError, match="source label"):
        parse_house_totals({"ib": "TOTAL NEW APPROPRIATIONS, ANOTHER OFFICE P 1,000"}, (spec,))
    with pytest.raises(ValueError, match="exactly one"):
        parse_house_totals(
            {
                "ib": (
                    "TOTAL NEW APPROPRIATIONS, DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS P 1,000\n"
                    "TOTAL NEW APPROPRIATIONS, DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS P 2,000"
                )
            },
            (spec,),
        )


def test_builds_reconciled_agency_budget_bundle(tmp_path) -> None:
    snapshot = _snapshot(tmp_path)
    output = tmp_path / "bundle"

    result = build_agency_budget_bundle(snapshot, output, chunk_rows=10)

    assert result.record_count == 44
    assert result.compared_records == 43
    assert result.unavailable_records == 1
    assert len(result.manifest_sha256) == 64
    connection = sqlite3.connect(":memory:")
    try:
        migration_path = (
            Path(__file__).resolve().parents[3]
            / "cloudflare/busisi/migrations/0008_agency_budgets.sql"
        )
        connection.executescript(migration_path.read_text(encoding="utf-8"))
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text(encoding="utf-8"))
        auto = connection.execute(
            "SELECT house_centavos, stage_status FROM agency_budget_items WHERE record_id = 'head:AUTO'"
        ).fetchone()
        senate = connection.execute(
            "SELECT level, parent_id FROM agency_budget_items WHERE record_id = 'congress:001'"
        ).fetchone()
    finally:
        connection.close()
    assert auto == (None, "not_applicable")
    assert senate == ("congress_institution", "head:01")


def test_bundle_rejects_tampered_snapshot_and_house_control(tmp_path) -> None:
    snapshot = _snapshot(tmp_path)
    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        build_agency_budget_bundle(snapshot, tmp_path / "digest-bundle")

    manifest["documents"][0]["sha256"] = hashlib.sha256(
        (snapshot / manifest["documents"][0]["path"]).read_bytes()
    ).hexdigest()
    manifest["house_control_pesos"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="House control total"):
        build_agency_budget_bundle(snapshot, tmp_path / "control-bundle")


def test_bundle_rejects_invalid_boundaries_and_national_control(tmp_path) -> None:
    snapshot = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="chunk_rows"):
        build_agency_budget_bundle(snapshot, tmp_path / "chunk-bundle", chunk_rows=0)

    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["fiscal_year"] = 2026
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="fiscal boundary"):
        build_agency_budget_bundle(snapshot, tmp_path / "fiscal-bundle")

    manifest["fiscal_year"] = 2027
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    overview_path = snapshot / "nep-overview.json"
    overview = json.loads(overview_path.read_text(encoding="utf-8"))
    overview["data"]["national"]["amount"] += 1
    overview_path.write_text(json.dumps(overview), encoding="utf-8")
    for document in manifest["documents"]:
        if document["key"] == "nep-overview":
            document["sha256"] = hashlib.sha256(overview_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="NEP national control"):
        build_agency_budget_bundle(snapshot, tmp_path / "national-bundle")
