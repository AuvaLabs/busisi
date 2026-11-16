"""Validate official PSA 2023 city and municipal poverty estimates."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import urlparse

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from engine.budget_watchdog.allotment_releases import extract_xlsx_rows

PSA_POVERTY_SOURCE_URL = (
    "https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx"
)
PSA_POVERTY_SOURCE_VERSION = "2023-sae-2026-02-06"
EXPECTED_POVERTY_RECORDS = 1_611
EXPECTED_CLASS_COUNTS = (881, 603, 119, 8, 0)
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
MAX_WORKBOOK_SHEETS = 12
PERCENT_MAX = Decimal(100)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PSGC = re.compile(r"[0-9]{10}")
_HEADERS = {
    "psgc": "psgc_code",
    "city or municipality": "name",
    "poverty incidence among population estimate": "poverty_incidence",
    "standard error": "standard_error",
    "coefficient of variation": "coefficient_variation",
    "95 confidence interval lower limit": "confidence_lower",
    "95 confidence interval upper limit": "confidence_upper",
}


@dataclass(frozen=True, slots=True)
class PovertyEstimate:
    psgc_code: str
    name: str
    poverty_incidence_bps: int
    standard_error_bps: int
    coefficient_variation_bps: int
    confidence_lower_bps: int
    confidence_upper_bps: int
    source_row: int
    source_url: str
    source_sha256: str


def _label(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _source(source_url: str, source_sha256: str) -> None:
    parsed = urlparse(source_url)
    expected = urlparse(PSA_POVERTY_SOURCE_URL)
    if parsed.scheme != "https" or parsed.netloc != expected.netloc or parsed.path != expected.path:
        raise ValueError("poverty source URL is not the registered PSA workbook")
    if _SHA256.fullmatch(source_sha256) is None:
        raise ValueError("poverty source digest must be lowercase SHA-256")


def _sheet_names(payload: bytes) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    except (DefusedXmlException, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("poverty workbook structure is invalid") from exc
    names = tuple(
        sheet.attrib.get("name", "").strip()
        for sheet in root.findall(f".//{{{SPREADSHEET_NS}}}sheet")
    )
    if not names or len(names) > MAX_WORKBOOK_SHEETS or any(not name for name in names):
        raise ValueError("poverty workbook sheet catalogue is invalid")
    return names


def _header_map(row: dict[str, str]) -> dict[str, str] | None:
    mapping = {
        _HEADERS[_label(value)]: column
        for column, value in row.items()
        if column != "row" and _label(value) in _HEADERS
    }
    return mapping if set(mapping) == set(_HEADERS.values()) else None


def _rows(payload: bytes) -> tuple[tuple[dict[str, str], ...], dict[str, str], int]:
    for sheet_name in _sheet_names(payload):
        rows = extract_xlsx_rows(payload, sheet_name)
        for index, row in enumerate(rows):
            columns = _header_map(row)
            if columns is not None:
                return rows, columns, index
    raise ValueError("poverty workbook required headers are unavailable")


def _basis_points(value: str, label: str, source_row: int) -> int:
    try:
        decimal = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError(f"source row {source_row} {label} is invalid") from exc
    scaled = decimal * Decimal(100)
    if (
        not decimal.is_finite()
        or decimal < 0
        or decimal > PERCENT_MAX
        or scaled != scaled.to_integral()
    ):
        raise ValueError(f"source row {source_row} {label} is invalid")
    return int(scaled)


def _parse_record(
    row: dict[str, str], columns: dict[str, str], source_url: str, source_sha256: str
) -> PovertyEstimate:
    source_row = int(row.get("row", "0"))
    values = {name: row.get(column, "").strip() for name, column in columns.items()}
    code = values["psgc_code"]
    name = values["name"]
    if _PSGC.fullmatch(code) is None or not name:
        raise ValueError(f"source row {source_row} poverty identity is invalid")
    measures = {
        key: _basis_points(values[key], key.replace("_", " "), source_row)
        for key in (
            "poverty_incidence",
            "standard_error",
            "coefficient_variation",
            "confidence_lower",
            "confidence_upper",
        )
    }
    if not (
        measures["confidence_lower"]
        <= measures["poverty_incidence"]
        <= measures["confidence_upper"]
    ):
        raise ValueError(f"source row {source_row} confidence interval is invalid")
    return PovertyEstimate(
        code,
        name,
        measures["poverty_incidence"],
        measures["standard_error"],
        measures["coefficient_variation"],
        measures["confidence_lower"],
        measures["confidence_upper"],
        source_row,
        source_url,
        source_sha256,
    )


def _poverty_class(incidence_bps: int) -> int:
    return min(5, incidence_bps // 2_000 + (1 if incidence_bps % 2_000 else 0)) or 1


def _validate_controls(
    records: tuple[PovertyEstimate, ...],
    expected_count: int,
    expected_class_counts: tuple[int, int, int, int, int] | None,
) -> None:
    if len(records) != expected_count:
        raise ValueError(
            f"poverty control total expected {expected_count}, received {len(records)}"
        )
    if len({record.psgc_code for record in records}) != len(records):
        raise ValueError("poverty PSGC identity is duplicated")
    if expected_class_counts is None:
        return
    observed = tuple(
        sum(_poverty_class(record.poverty_incidence_bps) == level for record in records)
        for level in range(1, 6)
    )
    if observed != expected_class_counts:
        raise ValueError("poverty classification controls do not reconcile")


def parse_poverty_workbook(
    payload: bytes,
    source_url: str,
    source_sha256: str,
    *,
    expected_count: int = EXPECTED_POVERTY_RECORDS,
    expected_class_counts: tuple[int, int, int, int, int] | None = EXPECTED_CLASS_COUNTS,
) -> tuple[PovertyEstimate, ...]:
    """Parse the official workbook and enforce identity and published controls."""

    _source(source_url, source_sha256)
    if expected_count <= 0:
        raise ValueError("poverty expected record count must be positive")
    rows, columns, header_index = _rows(payload)
    records = tuple(
        _parse_record(row, columns, source_url, source_sha256)
        for row in rows[header_index + 1 :]
        if any(row.get(column, "").strip() for column in columns.values())
    )
    _validate_controls(records, expected_count, expected_class_counts)
    return tuple(sorted(records, key=lambda record: record.psgc_code))
