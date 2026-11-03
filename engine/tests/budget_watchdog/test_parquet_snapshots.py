from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from engine.budget_watchdog.parquet_snapshots import (
    load_dpwh_snapshot,
    load_gaa_snapshot,
)

EXPECTED_GAA_CENTAVOS = 1_000_000_000
EXPECTED_DPWH_CENTAVOS = 494_467_510
EXPECTED_QUARANTINED_CENTAVOS = 219_400_000


def test_gaa_snapshot_aggregates_object_rows_into_program_families(tmp_path) -> None:
    path = tmp_path / "gaa.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "department": "18",
                    "agency": "001",
                    "dsc": "Construction of Sample Building",
                    "amt": 6_000.0,
                    "year": 2026,
                },
                {
                    "department": "18",
                    "agency": "001",
                    "dsc": "Construction of Sample Building",
                    "amt": 4_000.0,
                    "year": 2026,
                },
                {
                    "department": "18",
                    "agency": "001",
                    "dsc": "Zero Placeholder",
                    "amt": 0.0,
                    "year": 2026,
                },
                {
                    "department": "07",
                    "agency": "001",
                    "dsc": "Different Department",
                    "amt": 1_000_000.0,
                    "year": 2026,
                },
            ]
        ),
        path,
    )

    result = load_gaa_snapshot(path, department_id="18", fiscal_years=(2026,))

    assert len(result.records) == 1
    assert result.records[0].budget_line_id == "18-001|construction of sample building"
    assert result.records[0].amount_centavos == EXPECTED_GAA_CENTAVOS
    assert result.issues == ()


def test_dpwh_snapshot_filters_years_and_preserves_decimal_budget(tmp_path) -> None:
    path = tmp_path / "dpwh.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "contractId": "24XX0001",
                    "description": "CONSTRUCTION OF SAMPLE BUILDING",
                    "budget": Decimal("4944675.10"),
                    "infraYear": "2024",
                    "location": {"province": "Sample DEO", "region": "Region X"},
                    "sourceOfFunds": "GAA 2024",
                },
                {
                    "contractId": "22XX0001",
                    "description": "OLDER PROJECT",
                    "budget": Decimal("1000000.00"),
                    "infraYear": "2022",
                    "location": {"province": "Sample DEO", "region": "Region X"},
                    "sourceOfFunds": "GAA 2022",
                },
            ]
        ),
        path,
    )

    result = load_dpwh_snapshot(path, fiscal_years=(2024, 2025, 2026))

    assert len(result.records) == 1
    assert result.records[0].contract_id == "24XX0001"
    assert result.records[0].budget_centavos == EXPECTED_DPWH_CENTAVOS
    assert result.issues == ()


def test_gaa_snapshot_quarantines_unidentifiable_description(tmp_path) -> None:
    path = tmp_path / "gaa.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "department": "18",
                    "agency": "001",
                    "dsc": "-",
                    "amt": 2194.0,
                    "year": 2026,
                }
            ]
        ),
        path,
    )

    result = load_gaa_snapshot(path, department_id="18", fiscal_years=(2026,))

    assert result.records == ()
    assert len(result.issues) == 1
    assert result.issues[0].code == "invalid_gaa_row"
    assert result.issues[0].row_number == 0
    assert result.issues[0].amount_centavos == EXPECTED_QUARANTINED_CENTAVOS
