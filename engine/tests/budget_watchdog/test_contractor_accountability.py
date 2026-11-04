from __future__ import annotations

import json

import pytest

from engine.budget_watchdog.contractor_accountability import (
    AwardRecord,
    ContractorRecord,
    build_accountability_snapshot,
    parse_blacklist_index_pages,
    parse_blacklist_order_pages,
    parse_cpes_low_ratings,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64


def _payload(**updates: object) -> bytes:
    document = {
        "count": 2,
        "per_page": 20,
        "next_page": None,
        "previous_page": None,
        "total_pages": 1,
        "data": [
            {
                "blacklisted_entity": "Exact Builders, Inc.",
                "bo_issued": "1",
                "min_date": "2025-01-01",
                "max_date": "2025-12-31",
            },
            {
                "blacklisted_entity": "Name Only Construction",
                "bo_issued": "1",
                "min_date": "2025-02-01",
                "max_date": "PERMANENT",
            },
        ],
    }
    document.update(updates)
    return json.dumps(document).encode()


def test_blacklist_index_validates_control_totals_and_unique_entities() -> None:
    index = parse_blacklist_index_pages((_payload(),), (SHA,))

    assert index.reported_count == 2
    assert index.entities[0].reported_name == "Exact Builders, Inc."
    assert index.source_sha256 == (SHA,)

    with pytest.raises(ValueError, match="control total"):
        parse_blacklist_index_pages((_payload(count=3),), (SHA,))


def test_blacklist_index_quarantines_reversed_summary_date() -> None:
    payload = _payload()
    document = json.loads(payload)
    document["data"][0]["max_date"] = "2024-12-31"

    index = parse_blacklist_index_pages((json.dumps(document).encode(),), (SHA,))

    assert index.date_anomaly_count == 1
    assert index.entities[0].date_valid is False
    assert len(index.entities) == index.reported_count


def test_blacklist_orders_preserve_dates_and_permanent_state() -> None:
    payload = json.dumps(
        {
            "count": 1,
            "per_page": 20,
            "next_page": None,
            "previous_page": None,
            "total_pages": 1,
            "data": [
                {
                    "procuring_entity": "Example Department",
                    "start_date": "2025-01-01",
                    "end_date": "PERMANENT",
                    "project": "Example public project",
                }
            ],
        }
    ).encode()

    orders = parse_blacklist_order_pages("Exact Builders, Inc.", ((payload, SHA),))

    assert len(orders) == 1
    assert orders[0].permanent is True
    assert orders[0].end_date is None
    assert orders[0].source_sha256 == SHA


def test_blacklist_orders_quarantine_exact_duplicate_source_rows() -> None:
    row = {
        "procuring_entity": "Example Department",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "project": "Example public project",
    }
    payload = json.dumps(
        {
            "count": 2,
            "per_page": 20,
            "next_page": None,
            "previous_page": None,
            "total_pages": 1,
            "data": [row, row],
        }
    ).encode()

    orders = parse_blacklist_order_pages("Exact Builders, Inc.", ((payload, SHA),))

    assert len(orders) == 1


def test_cpes_parser_keeps_only_low_ratings_with_page_and_pcab_id() -> None:
    header = (
        "NAME OF CONSTRUCTOR".ljust(35)
        + "LICENSE NO.".ljust(15)
        + "PROJECT".ljust(55)
        + "EVALUATION".ljust(15)
        + "AGENCY".ljust(12)
        + "CONTRACT"
    )
    poor = (
        "Exact Builders, Inc.".ljust(35)
        + "12345".ljust(15)
        + "Construction of Example School".ljust(55)
        + "03/10/2026".ljust(15)
        + "DPWH".ljust(12)
        + "1,000.000 120 C 0.4000 0.2000 0.0000 60.00% 71.56% Poor"
    )
    satisfactory = (
        "Other Builder".ljust(35)
        + "67890".ljust(15)
        + "Other Project".ljust(55)
        + "03/11/2026".ljust(15)
        + "DA".ljust(12)
        + "1,000.000 120 C 0.4000 0.2000 0.3000 90.00% 90.00% Satisfactory"
    )
    no_license = (
        "No License Builder".ljust(35)
        + "-".ljust(15)
        + "Housing Project".ljust(55)
        + "03/12/2026".ljust(15)
        + "NHA".ljust(12)
        + "1,000.000 120 C 0.4000 0.2000 0.0000 60.00% 70.00% Unsatisfactory"
    )

    ratings = parse_cpes_low_ratings(
        f"{header}\n{poor}\n{satisfactory}\n\f{header}\n{no_license}\n",
        source_sha256=SHA,
        source_url="https://www.gppb.gov.ph/example.pdf",
        release_label="41st Release",
    )

    assert len(ratings) == 2
    assert ratings[0].pcab_id == "12345"
    assert ratings[0].final_rating_bps == 7_156
    assert ratings[0].page_number == 1
    assert ratings[1].pcab_id is None
    assert ratings[1].page_number == 2


def test_snapshot_links_strong_identities_and_quarantines_name_only_matches() -> None:
    contractors = (
        ContractorRecord(
            contractor_key="pcab:12345",
            contractor_name="EXACT BUILDERS, INC.",
            pcab_id="12345",
            pcab_name="EXACT BUILDERS, INC.",
        ),
        ContractorRecord(
            contractor_key="pcab:99999",
            contractor_name="NAME ONLY CONSTRUCTION",
            pcab_id="99999",
            pcab_name="",
        ),
    )

    def order_payload(project: str, start: str, end: str) -> bytes:
        return json.dumps(
            {
                "count": 1,
                "per_page": 20,
                "next_page": None,
                "previous_page": None,
                "total_pages": 1,
                "data": [
                    {
                        "procuring_entity": "Example Department",
                        "start_date": start,
                        "end_date": end,
                        "project": project,
                    }
                ],
            }
        ).encode()

    orders = (
        *parse_blacklist_order_pages(
            "Exact Builders, Inc.",
            ((order_payload("Restricted project", "2025-01-01", "2025-12-31"), SHA),),
        ),
        *parse_blacklist_order_pages(
            "Name Only Construction",
            ((order_payload("Other project", "2025-01-01", "PERMANENT"), OTHER_SHA),),
        ),
    )
    cpes = parse_cpes_low_ratings(
        "NAME OF CONSTRUCTOR".ljust(35)
        + "LICENSE NO.".ljust(15)
        + "PROJECT".ljust(55)
        + "DATE OF".ljust(15)
        + "*IMPL.".ljust(12)
        + "CONTRACT\n"
        + "Exact Builders, Inc.".ljust(35)
        + "12345".ljust(15)
        + "Poor project".ljust(55)
        + "02/01/2025".ljust(15)
        + "DPWH".ljust(12)
        + "1,000.000 120 C 60.00% 70.00% Poor\n",
        source_sha256=SHA,
        source_url="https://www.gppb.gov.ph/cpes.pdf",
        release_label="41st Release",
    )
    awards = (
        AwardRecord(
            source_row_id="award-1",
            contract_id="25AA0001",
            contractor_key="pcab:12345",
            relationship="sole",
            match_basis="structured_exact",
            awardee_name="Exact Builders, Inc.",
            award_date="2025-03-01",
            contract_amount_centavos=100_000_00,
            row_sha256=OTHER_SHA,
        ),
        AwardRecord(
            source_row_id="award-2",
            contract_id="25AA0002",
            contractor_key="pcab:12345",
            relationship="sole",
            match_basis="structured_exact",
            awardee_name="Different Company",
            award_date="2025-04-01",
            contract_amount_centavos=200_000_00,
            row_sha256=SHA,
        ),
    )

    snapshot = build_accountability_snapshot(
        contractors,
        orders,
        cpes,
        awards,
        checked_on="2026-11-04",
        blacklist_index_sha256=(SHA,),
        award_source_sha256=OTHER_SHA,
        award_source_revision="1" * 40,
    )

    assert len(snapshot.blacklist_events) == 1
    assert snapshot.blacklist_events[0].contractor_key == "pcab:12345"
    assert len(snapshot.cpes_events) == 1
    assert snapshot.cpes_events[0].identity_state == "pcab_id_exact"
    assert {item.signal_type for item in snapshot.award_signals} == {
        "award_after_low_cpes",
        "award_during_blacklist",
    }
    assert snapshot.quarantine_counts == {
        "blacklist_name_only": 1,
        "cpes_missing_or_unmatched_pcab": 0,
    }
