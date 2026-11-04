"""Validate the scoped DepEd PPP school registry without widening its meaning."""

from __future__ import annotations

import re
import zipfile
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import urlparse

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from engine.budget_watchdog.allotment_releases import extract_xlsx_rows
from engine.budget_watchdog.facility_identity import FacilityRegistryRecord

DEPED_PPP_SOURCE_URL = "https://www.deped.gov.ph/wp-content/uploads/List-of-PSIP-III-Sites.xlsx"
EXPECTED_DEPED_PPP_SCHOOLS = 1_095
SOURCE_ID = "deped-ppp-2025"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ALLOWED_REGIONS = {"car", "ncr", "region i", "region ii", "region iii", "region iv a", "region iv b", "region v"}
PHILIPPINE_LATITUDE = (Decimal("4"), Decimal("22"))
PHILIPPINE_LONGITUDE = (Decimal("116"), Decimal("127"))
HEADERS = {
    "region": "region",
    "division": "division",
    "city or municipality": "municipality",
    "school id": "official_id",
    "name of school": "official_name",
    "latitude": "latitude",
    "longitude": "longitude",
    "demolition required": "demolition_required",
    "with geotechnical report": "geotechnical_report",
    "with previous site development plan": "site_development_plan",
    "with ownership documents as of nov 2025": "ownership_documents",
}


def _label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _sheet_names(payload: bytes) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    except (DefusedXmlException, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("DepEd workbook structure is invalid") from exc
    names = tuple(
        sheet.attrib.get("name", "").strip()
        for sheet in root.findall(f".//{{{SPREADSHEET_NS}}}sheet")
    )
    if not names or len(names) > 8 or any(not name for name in names):
        raise ValueError("DepEd workbook sheet catalogue is invalid")
    return names


def _source(source_url: str, source_sha256: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.netloc != "www.deped.gov.ph":
        raise ValueError("source URL must use the official DepEd HTTPS origin")
    if parsed.path != urlparse(DEPED_PPP_SOURCE_URL).path:
        raise ValueError("source URL is not the registered DepEd PPP workbook")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("source digest must be a lowercase SHA-256 value")


def _header_map(row: dict[str, str]) -> dict[str, str] | None:
    mapping = {
        HEADERS[_label(value)]: column
        for column, value in row.items()
        if column != "row" and _label(value) in HEADERS
    }
    return mapping if set(mapping) == set(HEADERS.values()) else None


def _rows(payload: bytes) -> tuple[tuple[dict[str, str], ...], dict[str, str], int]:
    for sheet_name in _sheet_names(payload):
        rows = extract_xlsx_rows(payload, sheet_name)
        for index, row in enumerate(rows):
            mapping = _header_map(row)
            if mapping is not None:
                return rows, mapping, index
    raise ValueError("DepEd workbook required headers are unavailable")


def _coordinate(value: str, *, latitude: bool, source_row: int) -> int:
    try:
        coordinate = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"source row {source_row} coordinates are invalid") from exc
    lower, upper = PHILIPPINE_LATITUDE if latitude else PHILIPPINE_LONGITUDE
    if not coordinate.is_finite() or coordinate < lower or coordinate > upper:
        raise ValueError(f"source row {source_row} coordinates fall outside broad Philippines bounds")
    return int((coordinate * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _flag(value: str, field: str, source_row: int) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"", "no"}:
        return False
    if normalized == "yes":
        return True
    raise ValueError(f"source row {source_row} {field} value is invalid")


def parse_deped_ppp_workbook(
    payload: bytes,
    source_url: str,
    source_sha256: str,
    *,
    expected_count: int = EXPECTED_DEPED_PPP_SCHOOLS,
) -> tuple[FacilityRegistryRecord, ...]:
    """Parse the official scoped list and enforce its public control total."""

    _source(source_url, source_sha256)
    if expected_count <= 0:
        raise ValueError("expected school count must be positive")
    rows, columns, header_index = _rows(payload)
    records: list[FacilityRegistryRecord] = []
    identifiers: set[str] = set()
    for row in rows[header_index + 1 :]:
        values = {field: row.get(column, "").strip() for field, column in columns.items()}
        if not any(values.values()):
            continue
        source_row = int(row.get("row", "0"))
        official_id = values["official_id"]
        if not re.fullmatch(r"\d{6}", official_id):
            raise ValueError(f"source row {source_row} school ID is invalid")
        if official_id in identifiers:
            raise ValueError(f"school ID {official_id} is duplicated")
        identifiers.add(official_id)
        required = (values["region"], values["division"], values["municipality"], values["official_name"])
        if any(not value for value in required):
            raise ValueError(f"source row {source_row} required identity field is missing")
        if _label(values["region"]) not in ALLOWED_REGIONS:
            raise ValueError(f"source row {source_row} region is outside the announced scope")
        records.append(FacilityRegistryRecord(
            facility_id=f"deped:{official_id}",
            facility_type="school",
            official_id=official_id,
            official_name=values["official_name"],
            municipality=values["municipality"],
            province="",
            region=values["region"],
            source_id=SOURCE_ID,
            division=values["division"],
            latitude_e6=_coordinate(values["latitude"], latitude=True, source_row=source_row),
            longitude_e6=_coordinate(values["longitude"], latitude=False, source_row=source_row),
            source_row=source_row,
            demolition_required=_flag(values["demolition_required"], "demolition", source_row),
            geotechnical_report=_flag(values["geotechnical_report"], "geotechnical report", source_row),
            site_development_plan=_flag(values["site_development_plan"], "site plan", source_row),
            ownership_documents=_flag(values["ownership_documents"], "ownership documents", source_row),
        ))
    if len(records) != expected_count:
        raise ValueError(f"DepEd school control total expected {expected_count}, received {len(records)}")
    return tuple(sorted(records, key=lambda record: record.official_id))
