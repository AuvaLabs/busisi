from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from engine.budget_watchdog.acquisition_universe import build_acquisition_universe


def _delivery(path: Path) -> None:
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "contractId": "24AA0001",
                    "description": "School building",
                    "category": "Buildings",
                    "status": "Completed",
                    "budget": 1_000_000.25,
                    "location": {"province": "Cebu", "region": "Region VII"},
                    "infraYear": "2024",
                },
                {
                    "contractId": "25BB0002",
                    "description": "Hospital wing",
                    "category": "Buildings",
                    "status": "On-Going",
                    "budget": 2_000_000.50,
                    "location": {"province": "Bohol", "region": "Region VII"},
                    "infraYear": "2025",
                },
                {
                    "contractId": "25CC0003",
                    "description": "Road repair",
                    "category": "Roads",
                    "status": "On-Going",
                    "budget": 3_000_000,
                    "location": {"province": "Leyte", "region": "Region VIII"},
                    "infraYear": "2025",
                },
            ]
        ),
        path,
    )


def _award(
    row_id: str,
    *,
    reference_id: str | None,
    contract_no: str | None,
    award_title: str | None,
    amount: float = 900_000.25,
) -> dict:
    return {
        "id": row_id,
        "reference_id": reference_id,
        "contract_no": contract_no,
        "award_title": award_title,
        "notice_title": "Reviewed award row",
        "awardee_name": "PUBLIC BUILDER",
        "organization_name": "DPWH TEST OFFICE",
        "area_of_delivery": "Cebu",
        "business_category": "Construction Projects",
        "contract_amount": amount,
        "award_date": datetime(2025, 2, 1),
        "award_status": "active",
    }


def _awards(path: Path) -> None:
    rows = [
        _award(
            "00000000-0000-0000-0000-000000000001",
            reference_id="24AA0001",
            contract_no="24AA0001",
            award_title="24AA0001",
        ),
        _award(
            "00000000-0000-0000-0000-000000000002",
            reference_id=None,
            contract_no=None,
            award_title="25BB0002",
        ),
        _award(
            "00000000-0000-0000-0000-000000000003",
            reference_id=None,
            contract_no=None,
            award_title="25BB0002",
            amount=800_000,
        ),
        _award(
            "00000000-0000-0000-0000-000000000004",
            reference_id="24AA0001",
            contract_no="24AA0001",
            award_title="25CC0003",
        ),
        _award(
            "00000000-0000-0000-0000-000000000005",
            reference_id="UNRELATED",
            contract_no="UNRELATED",
            award_title="UNRELATED",
        ),
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_builds_complete_exact_match_universe_and_quarantines_conflicts(tmp_path) -> None:
    delivery = tmp_path / "delivery.parquet"
    awards = tmp_path / "awards.parquet"
    _delivery(delivery)
    _awards(awards)

    snapshot = build_acquisition_universe(
        delivery,
        awards,
        fiscal_years=(2024, 2025),
        delivery_sha256="d" * 64,
        award_sha256="a" * 64,
        award_revision="b" * 40,
        checked_on=date(2026, 11, 3),
    )

    assert snapshot.summary.contract_count == 3
    assert snapshot.summary.source_row_count == 5
    assert snapshot.summary.accepted_match_rows == 3
    assert snapshot.summary.quarantined_rows == 1
    assert snapshot.summary.lifecycle_task_count == 27
    assert snapshot.summary.state_counts == {
        "conflict_review": 2,
        "multiple_exact_rows": 1,
    }
    assert [row.match_basis for row in snapshot.matches] == [
        "structured_exact",
        "title_exact",
        "title_exact",
    ]
    assert snapshot.contracts[0].budget_centavos == 100_000_025
    assert snapshot.quarantine[0].candidate_contract_ids == ("24AA0001", "25CC0003")
    assert snapshot.quarantine[0].reference_id == "24AA0001"
    assert snapshot.quarantine[0].contract_no == "24AA0001"
    assert snapshot.quarantine[0].award_title == "25CC0003"
    assert snapshot.quarantine[0].notice_title == "Reviewed award row"


def test_full_universe_snapshot_is_deterministic(tmp_path) -> None:
    delivery = tmp_path / "delivery.parquet"
    awards = tmp_path / "awards.parquet"
    _delivery(delivery)
    _awards(awards)
    arguments = {
        "fiscal_years": (2024, 2025),
        "delivery_sha256": "d" * 64,
        "award_sha256": "a" * 64,
        "award_revision": "b" * 40,
        "checked_on": date(2026, 11, 3),
    }

    first = build_acquisition_universe(delivery, awards, **arguments)
    second = build_acquisition_universe(delivery, awards, **arguments)

    assert first == second
