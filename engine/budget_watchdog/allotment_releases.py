"""Parse and reconcile the official FY2026 DBM allotment-release workbook."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

FISCAL_YEAR = 2026
AS_OF_DATE = "2026-09-30"
THOUSAND_PESOS_TO_CENTAVOS = 100_000
CURRENT_GAA_ADJUSTED_THOUSAND_PESOS = 4_391_044_969
CURRENT_GAA_RELEASES_THOUSAND_PESOS = 4_072_227_740
CURRENT_GAA_BALANCE_THOUSAND_PESOS = 318_817_229
TOTAL_PROGRAM_THOUSAND_PESOS = 6_793_162_000
TOTAL_RELEASES_THOUSAND_PESOS = 6_532_951_466
TOTAL_BALANCE_THOUSAND_PESOS = 260_210_534
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_XLSX_ENTRIES = 128
MAX_XLSX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
DEPARTMENT_ROWS = range(9, 56)
ATTACHED_AGENCY_ROWS = range(56, 93)
FORCED_SUBUNIT_ROWS = range(72, 78)
SPECIAL_PURPOSE_FUND_ROWS = range(94, 107)
PUBLISHABLE_ROWS = range(9, 107)
SECTION_HEADER_ROW = 93


@dataclass(frozen=True, slots=True)
class AllotmentReleaseRecord:
    record_id: str
    fiscal_year: int
    as_of_date: str
    source_row: int
    level: str
    parent_id: str | None
    code: str
    name: str
    program_centavos: int
    adjustment_centavos: int
    adjusted_program_centavos: int
    release_centavos: int
    balance_centavos: int
    release_bps: int | None
    source_url: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class AllotmentReleaseControls:
    current_gaa_adjusted_centavos: int
    current_gaa_releases_centavos: int
    current_gaa_balance_centavos: int
    total_program_centavos: int
    total_releases_centavos: int
    total_balance_centavos: int


PUBLIC_NAMES = {
    "COP": "Congress of the Philippines",
    "OP": "Office of the President",
    "OVP": "Office of the Vice President",
    "DAR": "Department of Agrarian Reform",
    "DA": "Department of Agriculture",
    "DBM": "Department of Budget and Management",
    "DepEd": "Department of Education",
    "SUCS": "State Universities and Colleges",
    "DOE": "Department of Energy",
    "DENR": "Department of Environment and Natural Resources",
    "DOF": "Department of Finance",
    "DFA": "Department of Foreign Affairs",
    "DOH": "Department of Health",
    "DHSUD": "Department of Human Settlements and Urban Development",
    "DICT": "Department of Information and Communications Technology",
    "DILG": "Department of the Interior and Local Government",
    "DOJ": "Department of Justice",
    "DOLE": "Department of Labor and Employment",
    "DMW": "Department of Migrant Workers",
    "DND": "Department of National Defense",
    "DPWH": "Department of Public Works and Highways",
    "DOST": "Department of Science and Technology",
    "DSWD": "Department of Social Welfare and Development",
    "DOT": "Department of Tourism",
    "DTI": "Department of Trade and Industry",
    "DOTr": "Department of Transportation",
    "DEPDev (formerly NEDA)": "Department of Economy, Planning, and Development",
    "PCO": "Presidential Communications Office",
    "Judiciary": "The Judiciary",
    "CSC": "Civil Service Commission",
    "COA": "Commission on Audit",
    "COMELEC": "Commission on Elections",
    "OMBUDSMAN": "Office of the Ombudsman",
    "CHR": "Commission on Human Rights",
    "OEOs": "Other Executive Offices",
}


def _safe_workbook_member(target: str) -> str:
    candidate = PurePosixPath(target.lstrip("/"))
    if not target.startswith("/"):
        candidate = PurePosixPath("xl") / candidate
    if ".." in candidate.parts or not str(candidate).startswith("xl/"):
        raise ValueError("workbook relationship escapes the XLSX archive")
    return str(candidate)


def extract_xlsx_rows(payload: bytes, sheet_name: str) -> tuple[dict[str, str], ...]:
    """Read cached cell values from one XLSX worksheet using the standard library."""

    if not isinstance(payload, bytes) or not payload:
        raise ValueError("XLSX payload must contain bytes")
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise ValueError("XLSX archive contains too many entries")
            if sum(entry.file_size for entry in entries) > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise ValueError("XLSX archive exceeds the uncompressed size limit")
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relationships.findall(f"{{{PACKAGE_RELATIONSHIP_NS}}}Relationship")
            }
            selected = next(
                (
                    sheet
                    for sheet in workbook.findall(f".//{{{SPREADSHEET_NS}}}sheet")
                    if sheet.attrib.get("name") == sheet_name
                ),
                None,
            )
            if selected is None:
                raise ValueError(f"worksheet is unavailable: {sheet_name}")
            relationship_id = selected.attrib.get(f"{{{RELATIONSHIP_NS}}}id", "")
            if relationship_id not in targets:
                raise ValueError("worksheet relationship is unavailable")
            worksheet = ElementTree.fromstring(
                archive.read(_safe_workbook_member(targets[relationship_id]))
            )
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [
                    "".join(text.text or "" for text in item.iter(f"{{{SPREADSHEET_NS}}}t"))
                    for item in shared_root.findall(f"{{{SPREADSHEET_NS}}}si")
                ]
    except (DefusedXmlException, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("XLSX workbook structure is invalid") from exc

    rows: list[dict[str, str]] = []
    for row in worksheet.findall(f".//{{{SPREADSHEET_NS}}}sheetData/{{{SPREADSHEET_NS}}}row"):
        output = {"row": row.attrib.get("r", "")}
        for cell in row.findall(f"{{{SPREADSHEET_NS}}}c"):
            reference = cell.attrib.get("r", "")
            match = re.match(r"[A-Z]+", reference)
            if match is None:
                raise ValueError("XLSX cell reference is invalid")
            value_node = cell.find(f"{{{SPREADSHEET_NS}}}v")
            value = "" if value_node is None else value_node.text or ""
            if cell.attrib.get("t") == "s" and value:
                try:
                    value = shared[int(value)]
                except (IndexError, ValueError) as exc:
                    raise ValueError("XLSX shared-string reference is invalid") from exc
            output[match.group()] = value
        rows.append(output)
    return tuple(rows)


def _source_metadata(source_url: str, source_sha256: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.netloc != "www.dbm.gov.ph":
        raise ValueError("source URL must use the registered DBM HTTPS origin")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("source digest must be a lowercase SHA-256 value")


def _integer(row: dict[str, str], column: str) -> int:
    value = str(row.get(column, "")).strip()
    if not value:
        return 0
    if not re.fullmatch(r"-?\d+", value):
        raise ValueError(f"source row {row.get('row')} column {column} is not an integer")
    return int(value)


def _centavos(value: int) -> int:
    return value * THOUSAND_PESOS_TO_CENTAVOS


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("release record label cannot produce an empty identifier")
    return slug


def _basis_points(releases: int, adjusted: int) -> int | None:
    if adjusted <= 0:
        return None
    ratio = (Decimal(releases) * Decimal(10_000) / Decimal(adjusted)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(ratio)


def _row_by_number(rows: tuple[dict[str, str], ...], number: int) -> dict[str, str]:
    matches = [row for row in rows if int(row.get("row", 0)) == number]
    if len(matches) != 1:
        raise ValueError(f"required source row {number} is unavailable or duplicated")
    return matches[0]


def _validate_controls(rows: tuple[dict[str, str], ...]) -> AllotmentReleaseControls:
    current = _row_by_number(rows, 7)
    total = _row_by_number(rows, 264)
    current_values = (_integer(current, "D"), _integer(current, "H"), _integer(current, "I"))
    if current_values != (
        CURRENT_GAA_ADJUSTED_THOUSAND_PESOS,
        CURRENT_GAA_RELEASES_THOUSAND_PESOS,
        CURRENT_GAA_BALANCE_THOUSAND_PESOS,
    ):
        raise ValueError("current GAA control does not reconcile")
    total_values = (_integer(total, "D"), _integer(total, "H"), _integer(total, "I"))
    if total_values != (
        TOTAL_PROGRAM_THOUSAND_PESOS,
        TOTAL_RELEASES_THOUSAND_PESOS,
        TOTAL_BALANCE_THOUSAND_PESOS,
    ):
        raise ValueError("all-source release control does not reconcile")
    return AllotmentReleaseControls(
        *(_centavos(value) for value in (*current_values, *total_values))
    )


def _record_scope(row_number: int, raw_label: str) -> tuple[str, str | None]:
    if row_number in DEPARTMENT_ROWS:
        if raw_label != raw_label.lstrip():
            return "subunit", None
        return "department", None
    if row_number in ATTACHED_AGENCY_ROWS:
        if raw_label != raw_label.lstrip() or row_number in FORCED_SUBUNIT_ROWS:
            return "subunit", None
        return "attached_agency", "release:oeos"
    if row_number in SPECIAL_PURPOSE_FUND_ROWS:
        return "special_purpose_fund", None
    raise ValueError("row is outside the publishable release scope")


def parse_release_rows(
    rows: tuple[dict[str, str], ...], source_url: str, source_sha256: str
) -> tuple[tuple[AllotmentReleaseRecord, ...], AllotmentReleaseControls]:
    """Parse the reconciled department section without inferring missing stages."""

    _source_metadata(source_url, source_sha256)
    controls = _validate_controls(rows)
    records: list[AllotmentReleaseRecord] = []
    current_department: str | None = None
    current_attached: str | None = None
    used_ids: set[str] = set()
    for row in rows:
        row_number = int(row.get("row", 0))
        if row_number not in PUBLISHABLE_ROWS or row_number == SECTION_HEADER_ROW:
            continue
        raw_label = str(row.get("A", ""))
        label = " ".join(raw_label.split())
        if not label:
            continue
        level, fixed_parent = _record_scope(row_number, raw_label)
        code = label.rstrip()
        name = PUBLIC_NAMES.get(code, code)
        if level == "department":
            record_id = f"release:{_slug(code)}"
            current_department = record_id
            current_attached = None
            parent_id = None
        elif level == "attached_agency":
            record_id = f"release:oeos:{_slug(code)}"
            current_attached = record_id
            parent_id = fixed_parent
        elif level == "subunit":
            parent_id = (
                current_attached if row_number in ATTACHED_AGENCY_ROWS else current_department
            )
            if parent_id is None:
                raise ValueError(f"source row {row_number} has no parent release record")
            record_id = f"{parent_id}:{_slug(code)}"
        else:
            record_id = f"release:spf:{_slug(code)}"
            parent_id = None
        if record_id in used_ids:
            record_id = f"{record_id}:{row_number}"
        used_ids.add(record_id)
        program = _integer(row, "B")
        adjustment = _integer(row, "C")
        adjusted = _integer(row, "D")
        releases = _integer(row, "H")
        balance = _integer(row, "I")
        if program < 0 or adjusted < 0 or releases < 0:
            raise ValueError(f"source row {row_number} contains a negative unsigned amount")
        if adjusted - releases != balance:
            raise ValueError(f"source row {row_number} balance does not reconcile")
        records.append(
            AllotmentReleaseRecord(
                record_id=record_id,
                fiscal_year=FISCAL_YEAR,
                as_of_date=AS_OF_DATE,
                source_row=row_number,
                level=level,
                parent_id=parent_id,
                code=code,
                name=name,
                program_centavos=_centavos(program),
                adjustment_centavos=_centavos(adjustment),
                adjusted_program_centavos=_centavos(adjusted),
                release_centavos=_centavos(releases),
                balance_centavos=_centavos(balance),
                release_bps=_basis_points(releases, adjusted),
                source_url=source_url,
                source_sha256=source_sha256,
            )
        )
    if not records:
        raise ValueError("release workbook produced no publishable records")
    return tuple(records), controls
