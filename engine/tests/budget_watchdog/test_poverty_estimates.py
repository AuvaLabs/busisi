import io
import zipfile
from decimal import Decimal

import pytest

from engine.budget_watchdog.poverty_estimates import (
    PSA_POVERTY_SOURCE_URL,
    parse_poverty_workbook,
)


def _xlsx(rows: tuple[tuple[str, ...], ...], sheet: str = "2023 SAE") -> bytes:
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


HEADERS = (
    "PSGC",
    "City or Municipality",
    "Poverty incidence among population estimate",
    "Standard error",
    "Coefficient of variation",
    "95% confidence interval lower limit",
    "95% confidence interval upper limit",
)


def test_parses_checked_city_and_municipal_poverty_estimates() -> None:
    payload = _xlsx(
        (
            HEADERS,
            ("0102801000", "Adams", "15.5", "1.2", "7.7", "13.1", "17.9"),
            ("0972015000", "Siayan", "67.8", "2.1", "3.1", "63.7", "71.9"),
        )
    )

    records = parse_poverty_workbook(
        payload,
        PSA_POVERTY_SOURCE_URL,
        "a" * 64,
        expected_count=2,
        expected_class_counts=(1, 0, 0, 1, 0),
    )

    assert [record.psgc_code for record in records] == ["0102801000", "0972015000"]
    assert records[0].poverty_incidence_bps == 1_550
    assert records[0].standard_error_bps == 120
    assert records[0].coefficient_variation_bps == 770
    assert records[1].confidence_lower_bps == 6_370
    assert records[1].confidence_upper_bps == 7_190
    assert records[1].source_row == 3


def test_rejects_duplicate_ids_invalid_intervals_and_wrong_controls() -> None:
    duplicate = (
        HEADERS,
        ("0102801000", "Adams", "15.5", "1.2", "7.7", "13.1", "17.9"),
        ("0102801000", "Adams", "15.5", "1.2", "7.7", "13.1", "17.9"),
    )
    with pytest.raises(ValueError, match="duplicated"):
        parse_poverty_workbook(_xlsx(duplicate), PSA_POVERTY_SOURCE_URL, "a" * 64, expected_count=2)

    invalid_interval = (
        HEADERS,
        ("0102801000", "Adams", "15.5", "1.2", "7.7", "16.0", "17.9"),
    )
    with pytest.raises(ValueError, match="confidence interval"):
        parse_poverty_workbook(
            _xlsx(invalid_interval), PSA_POVERTY_SOURCE_URL, "a" * 64, expected_count=1
        )

    with pytest.raises(ValueError, match="classification controls"):
        parse_poverty_workbook(
            _xlsx((HEADERS, duplicate[1])),
            PSA_POVERTY_SOURCE_URL,
            "a" * 64,
            expected_count=1,
            expected_class_counts=(0, 1, 0, 0, 0),
        )


def test_preserves_decimal_precision_without_binary_floats() -> None:
    records = parse_poverty_workbook(
        _xlsx((HEADERS, ("0102801000", "Adams", "15.55", "1.25", "8.04", "13.05", "18.05"))),
        PSA_POVERTY_SOURCE_URL,
        "a" * 64,
        expected_count=1,
        expected_class_counts=(1, 0, 0, 0, 0),
    )

    assert records[0].poverty_incidence_bps == 1_555
    assert Decimal(records[0].poverty_incidence_bps) / Decimal(100) == Decimal("15.55")
