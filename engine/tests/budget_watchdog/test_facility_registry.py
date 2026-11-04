import io
import json
import zipfile
from pathlib import Path

import pytest

from engine.budget_watchdog.facility_identity import (
    FacilityLink,
    FacilityRegistryRecord,
    FacilityTitleRecord,
    link_school_title,
)
from engine.budget_watchdog.facility_registry import (
    DEPED_PPP_SOURCE_URL,
    parse_deped_ppp_workbook,
)
from engine.budget_watchdog.facility_registry_bundle import (
    FacilityRegistrySource,
    build_facility_registry_bundle,
)
from engine.budget_watchdog.facility_release_gate import candidate_set_sha256


def _xlsx(rows: tuple[tuple[str, ...], ...], sheet: str = "Annex A") -> bytes:
    strings: list[str] = []
    indices: dict[str, int] = {}

    def shared(value: str) -> int:
        if value not in indices:
            indices[value] = len(strings)
            strings.append(value)
        return indices[value]

    sheet_rows = []
    for row_number, values in enumerate(rows, start=1):
        cells = []
        for column_number, value in enumerate(values, start=1):
            column = chr(64 + column_number)
            cells.append(f'<c r="{column}{row_number}" t="s"><v>{shared(value)}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in strings)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            f'<sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            f"{''.join(sheet_rows)}</sheetData></worksheet>",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{shared_xml}</sst>",
        )
    return output.getvalue()


def _workbook(*data_rows: tuple[str, ...]) -> bytes:
    headers = (
        "Region",
        "Division",
        "City or Municipality",
        "School ID",
        "Name of School",
        "Latitude",
        "Longitude",
        "Demolition Required?",
        "With Geotechnical Report?",
        "With previous Site Development Plan?",
        "With ownership documents as of Nov 2025",
    )
    return _xlsx((headers, *data_rows))


SCHOOL_ONE = (
    "CAR",
    "Abra",
    "BANGUED (Capital)",
    "134966",
    "Agtangao ES",
    "17.56758",
    "120.630268",
    "",
    "",
    "yes",
    "yes",
)
SCHOOL_TWO = (
    "NCR",
    "Quezon City",
    "QUEZON CITY",
    "136505",
    "San Antonio Elementary School",
    "14.650000",
    "121.050000",
    "yes",
    "yes",
    "",
    "yes",
)


def test_parses_and_validates_the_scoped_deped_school_registry() -> None:
    records = parse_deped_ppp_workbook(
        _workbook(SCHOOL_ONE, SCHOOL_TWO),
        DEPED_PPP_SOURCE_URL,
        "a" * 64,
        expected_count=2,
    )

    assert len(records) == 2
    assert records[0].official_id == "134966"
    assert records[0].division == "Abra"
    assert records[0].municipality == "BANGUED (Capital)"
    assert records[0].latitude_e6 == 17_567_580
    assert records[0].longitude_e6 == 120_630_268
    assert records[0].source_row == 2
    assert records[1].demolition_required is True


def test_rejects_duplicate_ids_bad_coordinates_and_nonofficial_sources() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        parse_deped_ppp_workbook(
            _workbook(SCHOOL_ONE, SCHOOL_ONE),
            DEPED_PPP_SOURCE_URL,
            "a" * 64,
            expected_count=2,
        )
    outside = (*SCHOOL_ONE[:5], "54.1", "120.6", *SCHOOL_ONE[7:])
    with pytest.raises(ValueError, match="coordinates"):
        parse_deped_ppp_workbook(
            _workbook(outside),
            DEPED_PPP_SOURCE_URL,
            "a" * 64,
            expected_count=1,
        )
    with pytest.raises(ValueError, match="official DepEd"):
        parse_deped_ppp_workbook(
            _workbook(SCHOOL_ONE),
            "https://example.test/list.xlsx",
            "a" * 64,
            expected_count=1,
        )


def test_builds_a_verified_atomic_registry_bundle(tmp_path: Path) -> None:
    records = parse_deped_ppp_workbook(
        _workbook(SCHOOL_ONE, SCHOOL_TWO),
        DEPED_PPP_SOURCE_URL,
        "a" * 64,
        expected_count=2,
    )
    source = FacilityRegistrySource(
        source_id="deped-ppp-2025",
        publisher="Department of Education",
        dataset_name="Indicative List of Schools for PPP Project in 2026",
        source_url=DEPED_PPP_SOURCE_URL,
        artifact_sha256="a" * 64,
        acquired_at="2026-11-04T00:00:00+00:00",
        scope_note="Preliminary list of 1,095 possible PPP sites, not a national registry.",
        status="partial",
    )

    matched = link_school_title(
        FacilityTitleRecord(
            source_type="delivery",
            record_id="25AB0001",
            title="Construction of classrooms at Agtangao Elementary School, Bangued, Abra",
            location="Abra DEO, CAR",
        ),
        records,
    )
    unmatched = link_school_title(
        FacilityTitleRecord(
            source_type="delivery",
            record_id="25AB0002",
            title="Construction of classrooms at an unlisted school, Bangued, Abra",
            location="Abra DEO, CAR",
        ),
        records,
    )

    held = build_facility_registry_bundle(
        records,
        source,
        tmp_path / "held-bundle",
        links=(matched, unmatched),
    )

    assert held.link_count == 0
    assert "25AB0001" not in (held.output_dir / "facility-registry.sql").read_text()

    manifest = json.loads((held.output_dir / "manifest.json").read_text())
    assert manifest["facility_count"] == 2
    assert manifest["candidate_count"] == 1
    assert manifest["release_gate"] is None
    assert manifest["artifact_sha256"] == "a" * 64


def _reviewed_release(
    count: int = 100,
) -> tuple[
    tuple[FacilityRegistryRecord, ...],
    tuple[FacilityLink, ...],
    dict[str, object],
]:
    records = tuple(
        FacilityRegistryRecord(
            facility_id=f"deped:{100000 + index}",
            facility_type="school",
            official_id=str(100000 + index),
            official_name=f"Sample School {index}",
            municipality="Sample City",
            province="",
            region="NCR",
            source_id="deped-ppp-2025",
            division="Sample Division",
            source_row=index + 2,
        )
        for index in range(count)
    )
    links = tuple(
        FacilityLink(
            source_type="delivery",
            record_id=f"record-{index}",
            match_state="official_exact",
            facility_id=record.facility_id,
            record_group_key=None,
            record_group_label=record.official_name,
            match_method="exact_registry_name_and_place",
            confidence=95,
            signals=("exact_registry_name_in_title", "place_in_record"),
            limitation="The link identifies a school, not a completed building.",
        )
        for index, record in enumerate(records)
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_artifact_sha256": "a" * 64,
        "candidate_set_sha256": candidate_set_sha256(links),
        "matcher_version": "facility-identity-v1",
        "critical_reconciliation_failures": [],
        "cases": [
            {
                "source_type": link.source_type,
                "record_id": link.record_id,
                "facility_id": link.facility_id,
                "reviewer_one_id": "reviewer-one",
                "reviewer_one_decision": "accept",
                "reviewer_two_id": "reviewer-two",
                "reviewer_two_decision": "accept",
                "adjudication": "correct",
            }
            for link in links
        ],
    }
    return records, links, manifest


def test_registry_bundle_revalidates_and_publishes_a_passing_manifest(tmp_path: Path) -> None:
    records, links, review_manifest = _reviewed_release()
    source = FacilityRegistrySource(
        source_id="deped-ppp-2025",
        publisher="Department of Education",
        dataset_name="Indicative schools",
        source_url=DEPED_PPP_SOURCE_URL,
        artifact_sha256="a" * 64,
        acquired_at="2026-11-04T00:00:00+00:00",
        scope_note="Preliminary list.",
        status="partial",
    )

    result = build_facility_registry_bundle(
        records,
        source,
        tmp_path / "bundle",
        links=links,
        review_manifest=review_manifest,
    )

    assert result.facility_count == 100
    assert result.link_count == 100
    sql = (result.output_dir / "facility-registry.sql").read_text()
    assert "record-0" in sql
    bundle_manifest = json.loads((result.output_dir / "manifest.json").read_text())
    assert bundle_manifest["release_gate"]["passed"] is True
    assert bundle_manifest["release_gate"]["reviewed_cases"] == 100


def test_registry_bundle_rejects_a_gate_for_another_candidate_set(tmp_path: Path) -> None:
    records = parse_deped_ppp_workbook(
        _workbook(SCHOOL_ONE),
        DEPED_PPP_SOURCE_URL,
        "a" * 64,
        expected_count=1,
    )
    source = FacilityRegistrySource(
        source_id="deped-ppp-2025",
        publisher="Department of Education",
        dataset_name="Indicative schools",
        source_url=DEPED_PPP_SOURCE_URL,
        artifact_sha256="a" * 64,
        acquired_at="2026-11-04T00:00:00+00:00",
        scope_note="Preliminary list.",
        status="partial",
    )
    link = link_school_title(
        FacilityTitleRecord(
            "delivery",
            "record-1",
            "Agtangao Elementary School, Bangued",
            "Abra",
        ),
        records,
    )
    review_manifest = {
        "schema_version": 1,
        "source_artifact_sha256": "a" * 64,
        "candidate_set_sha256": "c" * 64,
        "matcher_version": "facility-identity-v1",
        "critical_reconciliation_failures": [],
        "cases": [],
    }

    with pytest.raises(ValueError, match="candidate set"):
        build_facility_registry_bundle(
            records,
            source,
            tmp_path / "bundle",
            links=(link,),
            review_manifest=review_manifest,
        )
