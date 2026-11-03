from decimal import Decimal
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.budget_watchdog import parquet_snapshots
from engine.budget_watchdog.parquet_snapshots import (
    SnapshotSchemaError,
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


@pytest.mark.parametrize(
    ("years", "message"),
    [
        ((), "must not be empty"),
        ((2026, 2026), "must be unique"),
        ((1899,), "between 1900 and 2200"),
    ],
)
def test_snapshot_rejects_invalid_fiscal_year_sets(
    tmp_path, years: tuple[int, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_gaa_snapshot(tmp_path / "unused.parquet", department_id="18", fiscal_years=years)


def test_gaa_snapshot_rejects_invalid_department_and_schema(tmp_path, monkeypatch) -> None:
    with pytest.raises(ValueError, match="numeric"):
        load_gaa_snapshot(tmp_path / "unused.parquet", department_id="DPWH", fiscal_years=(2026,))

    monkeypatch.setattr(parquet_snapshots.pq, "read_table", lambda *_args, **_kwargs: 1 / 0)
    with pytest.raises(SnapshotSchemaError, match="GAA Parquet schema"):
        load_gaa_snapshot(tmp_path / "broken.parquet", department_id="18", fiscal_years=(2026,))


def test_gaa_snapshot_quarantines_invalid_rows_and_preserves_valid_unicode(monkeypatch) -> None:
    rows = [
        {"agency": "", "year": 2026, "amt": 1, "dsc": "Missing agency"},
        {"agency": "001", "year": True, "amt": 1, "dsc": "Invalid year"},
        {"agency": "001", "year": 2026, "amt": "bad", "dsc": "Invalid amount"},
        {"agency": "001", "year": 2026, "amt": 1, "dsc": "Doña María Center"},
    ]
    table = SimpleNamespace(to_pylist=lambda: rows, num_rows=len(rows))
    monkeypatch.setattr(parquet_snapshots.pq, "read_table", lambda *_args, **_kwargs: table)

    result = load_gaa_snapshot("snapshot.parquet", department_id="18", fiscal_years=(2026,))

    assert len(result.issues) == 3
    assert result.records[0].budget_line_id.endswith("dona maria center")


def test_dpwh_snapshot_quarantines_invalid_rows_and_conflicts(monkeypatch) -> None:
    valid = {
        "contractId": "24XX0001",
        "description": "Sample Project",
        "budget": 100,
        "infraYear": "2024",
        "location": {"province": "Sample", "region": "Region X"},
        "sourceOfFunds": None,
    }
    rows = [
        {**valid, "contractId": ""},
        {**valid, "description": "-"},
        {**valid, "infraYear": "FY2024"},
        {**valid, "location": "Region X"},
        {**valid, "sourceOfFunds": 123},
        valid,
        {**valid, "description": "Conflicting Project"},
    ]
    table = SimpleNamespace(to_pylist=lambda: rows, num_rows=len(rows))
    monkeypatch.setattr(parquet_snapshots.pq, "read_table", lambda *_args, **_kwargs: table)

    result = load_dpwh_snapshot("snapshot.parquet", fiscal_years=(2024,))

    assert len(result.records) == 1
    assert len(result.issues) == 6
    assert "conflicting contractId" in result.issues[-1].detail
    assert result.records[0].source_of_funds == ""


def test_dpwh_snapshot_wraps_parquet_schema_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(parquet_snapshots.pq, "read_table", lambda *_args, **_kwargs: 1 / 0)

    with pytest.raises(SnapshotSchemaError, match="DPWH Parquet schema"):
        load_dpwh_snapshot(tmp_path / "broken.parquet", fiscal_years=(2024,))
