import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from engine.budget_watchdog.allotment_release_bundle import build_allotment_release_bundle
from engine.budget_watchdog.allotment_releases import extract_xlsx_rows, parse_release_rows


SOURCE_URL = (
    "https://www.dbm.gov.ph/wp-content/uploads/e-Fund_Releases/"
    "Status-of-Allotment-Releases/2026/September/"
    "FY-2026-as-of-September-30-Website.xlsx"
)
SOURCE_SHA = "a" * 64


def _minimal_xlsx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets><sheet name="By Dept" '
            'sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><si><t>DEPARTMENTS</t></si></sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData><row r="8"><c r="A8" t="s"><v>0</v>'
            '</c><c r="D8"><v>3671970347</v></c></row></sheetData></worksheet>',
        )
    return output.getvalue()


def test_extracts_the_named_xlsx_sheet_without_spreadsheet_dependencies() -> None:
    assert extract_xlsx_rows(_minimal_xlsx(), "By Dept") == (
        {"row": "8", "A": "DEPARTMENTS", "D": "3671970347"},
    )
    with pytest.raises(ValueError, match="worksheet is unavailable"):
        extract_xlsx_rows(_minimal_xlsx(), "Missing")


def _source_rows() -> tuple[dict[str, str], ...]:
    return (
        {"row": "7", "A": "A. FY 2026 GAA, RA NO. 12314", "D": "4391044969", "H": "4072227740", "I": "318817229"},
        {"row": "8", "A": "DEPARTMENTS", "D": "3671970347", "H": "3501002619", "I": "170967728"},
        {"row": "9", "A": "COP", "B": "38600212", "C": "0", "D": "38600212", "H": "38600212", "I": "0"},
        {"row": "15", "A": "DepEd", "B": "961323626", "C": "-185960", "D": "961137666", "H": "906410125", "I": "54727541"},
        {"row": "16", "A": "         Central Office", "B": "212063108", "C": "7166215", "D": "219229323", "H": "182760884", "I": "36468439"},
        {"row": "55", "A": "OEOs", "B": "79750974", "C": "107713", "D": "79858687", "H": "73314030", "I": "6544657"},
        {"row": "56", "A": "AMLC", "B": "333102", "C": "0", "D": "333102", "H": "170161", "I": "162941"},
        {"row": "93", "A": "SPECIAL PURPOSE FUNDS", "D": "719074622", "H": "571225121", "I": "147849501"},
        {"row": "94", "A": "Budgetary Support to Government Corporations", "B": "264819717", "C": "10443782", "D": "275263499", "H": "251745782", "I": "23517717"},
        {"row": "106", "A": "Revised AFP Modernization Program", "B": "40000000", "C": "0", "D": "40000000", "H": "33794326", "I": "6205674"},
        {"row": "108", "A": "B. AUTOMATIC APPROPRIATIONS", "D": "2402117031", "H": "2159201387", "I": "242915644"},
        {"row": "121", "A": " ORIGINAL PROGRAM", "D": "6793162000", "H": "6231429127", "I": "561732873"},
        {"row": "264", "A": "TOTAL", "D": "6793162000", "H": "6532951466", "I": "260210534"},
    )


def test_parses_department_attached_agency_subunit_and_special_fund() -> None:
    records, controls = parse_release_rows(_source_rows(), SOURCE_URL, SOURCE_SHA)

    assert len(records) == 7
    assert controls.current_gaa_releases_centavos == 407_222_774_000_000
    assert controls.total_releases_centavos == 653_295_146_600_000
    deped = next(record for record in records if record.source_row == 15)
    central = next(record for record in records if record.source_row == 16)
    amlc = next(record for record in records if record.source_row == 56)
    bsgc = next(record for record in records if record.source_row == 94)
    assert deped.level == "department"
    assert deped.name == "Department of Education"
    assert deped.release_centavos == 90_641_012_500_000
    assert deped.release_bps == 9431
    assert central.level == "subunit"
    assert central.parent_id == deped.record_id
    assert amlc.level == "attached_agency"
    assert amlc.parent_id == "release:oeos"
    assert bsgc.level == "special_purpose_fund"
    assert bsgc.parent_id is None


def test_release_parser_rejects_control_drift_and_unsafe_source_metadata() -> None:
    rows = list(_source_rows())
    rows[0] = {**rows[0], "H": "4072227739"}
    with pytest.raises(ValueError, match="current GAA control"):
        parse_release_rows(tuple(rows), SOURCE_URL, SOURCE_SHA)
    with pytest.raises(ValueError, match="source URL"):
        parse_release_rows(_source_rows(), "http://example.test/releases.xlsx", SOURCE_SHA)
    with pytest.raises(ValueError, match="source digest"):
        parse_release_rows(_source_rows(), SOURCE_URL, "bad")


def _snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    rows_path = snapshot / "by-department.json"
    rows_path.write_text(json.dumps(_source_rows()), encoding="utf-8")
    manifest = {
        "fiscal_year": 2026,
        "as_of_date": "2026-09-30",
        "source_url": SOURCE_URL,
        "source_sha256": SOURCE_SHA,
        "rows_path": rows_path.name,
        "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
    }
    (snapshot / "snapshot-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return snapshot


def test_builds_reconciled_allotment_release_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    result = build_allotment_release_bundle(_snapshot(tmp_path), output)

    assert result.record_count == 7
    assert result.department_count == 3
    assert result.attached_count == 2
    assert len(result.manifest_sha256) == 64
    database = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare/busisi/migrations/0020_allotment_releases.sql"
        )
        database.executescript(migration.read_text(encoding="utf-8"))
        database.executescript((output / "allotment-releases.sql").read_text(encoding="utf-8"))
        row = database.execute(
            "SELECT level, release_centavos, release_bps FROM allotment_release_items "
            "WHERE source_row = 15"
        ).fetchone()
    finally:
        database.close()
    assert row == ("department", 90_641_012_500_000, 9431)


def test_release_bundle_rejects_tampered_rows_and_fiscal_boundary(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="rows digest"):
        build_allotment_release_bundle(snapshot, tmp_path / "bad-digest")

    manifest["rows_sha256"] = hashlib.sha256(
        (snapshot / manifest["rows_path"]).read_bytes()
    ).hexdigest()
    manifest["fiscal_year"] = 2025
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="fiscal boundary"):
        build_allotment_release_bundle(snapshot, tmp_path / "bad-year")
