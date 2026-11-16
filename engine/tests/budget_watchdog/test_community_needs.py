import json

import pytest

from engine.budget_watchdog.community_needs import (
    build_population_snapshot,
    openstat_national_population_query,
    openstat_population_query,
    parse_national_population_control,
    parse_population_table,
)

SOURCE_SHA = "a" * 64
SOURCE_URL = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/test.px"


def _payload(rows: list[tuple[str, str, tuple[int, int, int]]]) -> bytes:
    codes = [code for code, _, _ in rows]
    labels = {code: label for code, label, _ in rows}
    values = [value for _, _, measures in rows for value in measures]
    return json.dumps(
        {
            "dataset": {
                "dimension": {
                    "Geographic Location": {
                        "category": {
                            "index": {code: index for index, code in enumerate(codes)},
                            "label": labels,
                        }
                    },
                    "Parameter": {
                        "category": {
                            "index": {"0": 0, "1": 1, "2": 2},
                            "label": {
                                "0": "Total Population",
                                "1": "Household Population",
                                "2": "Number of Households",
                            },
                        }
                    },
                    "id": ["Geographic Location", "Parameter"],
                    "size": [len(rows), 3],
                },
                "value": values,
                "label": "2024 population",
                "source": "Philippine Statistics Authority, 2024 Census of Population",
                "updated": "2026-11-16T10:00:00+08:00",
            }
        }
    ).encode()


def _region_payload(total: int = 100) -> bytes:
    return _payload(
        [
            ("0100000000", "..Region I", (total, total - 2, 30)),
            ("0102800000", "....Ilocos Norte", (total, total - 2, 30)),
            ("0102801000", "......Adams", (total, total - 2, 30)),
            ("0102801001", "........Adams", (total, total - 2, 30)),
        ]
    )


def test_population_query_requests_all_geographies_and_required_measures() -> None:
    assert openstat_population_query() == {
        "query": [
            {
                "code": "Geographic Location",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "Parameter",
                "selection": {"filter": "item", "values": ["0", "1", "2"]},
            },
        ],
        "response": {"format": "json-stat"},
    }


def test_national_population_query_requests_only_the_philippines_control() -> None:
    query = openstat_national_population_query()

    assert query["query"][0]["selection"] == {
        "filter": "item",
        "values": ["0000000000"],
    }
    assert query["response"] == {"format": "json-stat"}


def test_national_population_control_reads_all_three_exact_counts() -> None:
    control = parse_national_population_control(
        _payload([("0000000000", "Philippines", (300, 291, 90))]),
        source_sha256="c" * 64,
        source_url="https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/control.px",
    )

    assert control.total_population == 300
    assert control.household_population == 291
    assert control.households == 90


def test_population_parser_preserves_psgc_hierarchy_and_integer_units() -> None:
    table = parse_population_table(
        _region_payload(), source_sha256=SOURCE_SHA, source_url=SOURCE_URL
    )

    assert table.region_code == "0100000000"
    assert table.source_updated_at == "2026-11-16T10:00:00+08:00"
    assert [record.geographic_level for record in table.records] == [
        "region",
        "province_or_huc",
        "city_or_municipality",
        "barangay",
    ]
    assert [record.parent_psgc_code for record in table.records] == [
        None,
        "0100000000",
        "0102800000",
        "0102801000",
    ]
    assert table.records[-1].name == "Adams"
    assert table.records[-1].total_population == 100
    assert table.records[-1].household_population == 98
    assert table.records[-1].households == 30
    assert table.excluded_out_of_region == 0


def test_population_parser_excludes_and_counts_rows_from_another_region() -> None:
    table = parse_population_table(
        _payload(
            [
                ("1400000000", "..CAR", (10, 9, 2)),
                ("1400100000", "....Abra", (10, 9, 2)),
                ("0200101001", "........Wrong region barangay", (3, 3, 1)),
            ]
        ),
        source_sha256=SOURCE_SHA,
        source_url=SOURCE_URL,
    )

    assert [record.psgc_code for record in table.records] == [
        "1400000000",
        "1400100000",
    ]
    assert table.excluded_out_of_region == 1


def test_population_parser_records_incomplete_child_coverage_without_filling_it() -> None:
    table = parse_population_table(
        _payload(
            [
                ("0900000000", "..Region IX", (100, 98, 30)),
                ("0907200000", "....Zamboanga del Norte", (80, 79, 25)),
            ]
        ),
        source_sha256=SOURCE_SHA,
        source_url=SOURCE_URL,
    )

    assert len(table.hierarchy_gaps) == 1
    gap = table.hierarchy_gaps[0]
    assert gap.parent_psgc_code == "0900000000"
    assert gap.unallocated_population == 20
    assert gap.unallocated_household_population == 19
    assert gap.unallocated_households == 5


def test_population_parser_attaches_huc_to_region_not_previous_province() -> None:
    table = parse_population_table(
        _payload(
            [
                ("0900000000", "..Region IX", (30, 29, 8)),
                ("0908300000", "....Zamboanga Sibugay", (20, 19, 5)),
                ("0990101000", "......City of Isabela", (10, 10, 3)),
            ]
        ),
        source_sha256=SOURCE_SHA,
        source_url=SOURCE_URL,
    )

    assert table.records[-1].parent_psgc_code == "0900000000"
    assert table.hierarchy_gaps == ()


def test_population_parser_recognizes_manila_submunicipalities() -> None:
    table = parse_population_table(
        _payload(
            [
                ("1300000000", "..NCR", (10, 10, 2)),
                ("1380600000", "....City of Manila", (10, 10, 2)),
                ("1380601000", "Tondo I/II", (10, 10, 2)),
                ("1380601001", "........Barangay 1", (10, 10, 2)),
            ]
        ),
        source_sha256=SOURCE_SHA,
        source_url=SOURCE_URL,
    )

    assert table.records[2].geographic_level == "submunicipality"
    assert table.records[2].parent_psgc_code == "1380600000"
    assert table.records[3].parent_psgc_code == "1380601000"


def test_population_snapshot_reconciles_region_totals_to_national_control() -> None:
    first = parse_population_table(
        _region_payload(100), source_sha256=SOURCE_SHA, source_url=SOURCE_URL
    )
    second = parse_population_table(
        _payload(
            [
                ("0200000000", "..Region II", (200, 195, 60)),
                ("0200900000", "....Batanes", (200, 195, 60)),
            ]
        ),
        source_sha256="b" * 64,
        source_url="https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/test-2.px",
    )

    snapshot = build_population_snapshot(
        (first, second),
        national_population=300,
        national_household_population=293,
        national_households=90,
        national_source_sha256="c" * 64,
    )

    assert snapshot.total_population == 300
    assert snapshot.region_count == 2
    assert snapshot.place_count == 6
    assert snapshot.barangay_count == 1
    assert snapshot.excluded_out_of_region == 0
    assert snapshot.hierarchy_gaps == ()
    assert snapshot.national_unallocated_population == 0


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{}", "dataset"),
        (
            _payload([("0100000000", "..Region I", (9, 10, 2))]),
            "household population",
        ),
        (
            _payload([("0100000000", "......Wrong depth", (10, 9, 2))]),
            "first place",
        ),
    ],
)
def test_population_parser_rejects_invalid_boundaries(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_population_table(payload, source_sha256=SOURCE_SHA, source_url=SOURCE_URL)


def test_population_snapshot_rejects_duplicate_codes_and_control_mismatch() -> None:
    table = parse_population_table(
        _region_payload(), source_sha256=SOURCE_SHA, source_url=SOURCE_URL
    )
    with pytest.raises(ValueError, match="unique"):
        build_population_snapshot(
            (table, table),
            national_population=200,
            national_household_population=196,
            national_households=60,
            national_source_sha256="c" * 64,
        )
    with pytest.raises(ValueError, match="exceed the national control"):
        build_population_snapshot(
            (table,),
            national_population=99,
            national_household_population=98,
            national_households=30,
            national_source_sha256="c" * 64,
        )


def test_population_snapshot_preserves_positive_national_control_gap() -> None:
    table = parse_population_table(
        _region_payload(), source_sha256=SOURCE_SHA, source_url=SOURCE_URL
    )
    snapshot = build_population_snapshot(
        (table,),
        national_population=101,
        national_household_population=98,
        national_households=30,
        national_source_sha256="c" * 64,
    )

    assert snapshot.national_unallocated_population == 1
    assert snapshot.national_unallocated_household_population == 0
    assert snapshot.national_unallocated_households == 0


def test_population_parser_rejects_children_exceeding_parent_total() -> None:
    with pytest.raises(ValueError, match="exceed parent"):
        parse_population_table(
            _payload(
                [
                    ("0100000000", "..Region I", (10, 9, 2)),
                    ("0102800000", "....Ilocos Norte", (11, 10, 3)),
                ]
            ),
            source_sha256=SOURCE_SHA,
            source_url=SOURCE_URL,
        )
