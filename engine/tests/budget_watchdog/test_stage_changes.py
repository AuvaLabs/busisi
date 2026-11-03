import json

import pytest

from engine.budget_watchdog.stage_changes import (
    StageChangeSchemaError,
    parse_hgab_page,
    reconcile_hgab_dataset,
)


def _payload(rows: list[dict], *, total: int | None = None, sums: dict | None = None) -> bytes:
    return json.dumps(
        {
            "meta": {
                "dataset": "hgab",
                "fiscal_year": 2027,
                "currency": "PHP",
                "scale": "pesos",
                "source_commit": "a" * 40,
                "dataset_key": "dpwh",
                "house_stage": "hgab3",
            },
            "data": {
                "total": total if total is not None else len(rows),
                "sums": sums
                or {
                    "nep_php": sum(row.get("nep_php") or 0 for row in rows),
                    "hgab3_php": sum(row.get("house_php") or 0 for row in rows),
                    "unconfirmed_rows": sum(bool(row.get("held")) for row in rows),
                },
                "rows": rows,
                "next_offset": None,
            },
        }
    ).encode()


def _row(**overrides) -> dict:
    row = {
        "id": "record:1",
        "dataset": "dpwh",
        "title": "Construction of Sample Bridge",
        "program": "Network Development Program",
        "pap": "Bridge Program",
        "region": "Region III",
        "office": "Sample District Engineering Office",
        "bridge_group": "increased",
        "group_label": "Higher in the House bill",
        "held": False,
        "confidence": 1,
        "nep_php": 100,
        "house_php": 150,
        "delta_php": 50,
        "nep_page": 10,
        "hgab3_page": 20,
        "pdf_url": {
            "nep": "https://budget-assets.bettergov.ph/nep.pdf#page=10",
            "hgab3": "https://budget-assets.bettergov.ph/house.pdf#page=20",
        },
        "url": "https://budget.bettergov.ph/hgab/2027/dpwh/p/record%3A1",
    }
    return {**row, **overrides}


def test_parses_traceable_stage_change_and_normalizes_centavos() -> None:
    result = parse_hgab_page(_payload([_row()]), artifact_sha256="b" * 64)

    assert len(result.records) == 1
    record = result.records[0]
    assert record.record_id == "dpwh:record:1"
    assert record.change_type == "increased"
    assert record.review_status == "candidate"
    assert record.nep_centavos == 10_000
    assert record.house_centavos == 15_000
    assert record.difference_centavos == 5_000
    assert record.house_pdf_url.endswith("#page=20")


def test_quarantines_held_and_scope_review_rows() -> None:
    result = parse_hgab_page(
        _payload(
            [
                _row(
                    id="record:held",
                    bridge_group="house_only",
                    held=True,
                    confidence=None,
                    nep_php=None,
                    delta_php=None,
                ),
                _row(id="record:scope", bridge_group="scope_review"),
            ]
        ),
        artifact_sha256="b" * 64,
    )

    assert [record.review_status for record in result.records] == ["quarantine", "quarantine"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bridge_group": "accusation"}, "change type"),
        ({"delta_php": 51}, "difference"),
        ({"title": ""}, "title"),
        ({"confidence": 2}, "confidence"),
        ({"pdf_url": {"nep": "http://private/nep.pdf", "hgab3": "https://example/house"}}, "HTTPS"),
    ],
)
def test_rejects_malformed_or_inconsistent_rows(overrides: dict, message: str) -> None:
    with pytest.raises(StageChangeSchemaError, match=message):
        parse_hgab_page(_payload([_row(**overrides)]), artifact_sha256="b" * 64)


def test_reconciles_complete_dataset_counts_and_totals() -> None:
    rows = [
        _row(id="record:1"),
        _row(
            id="record:2",
            bridge_group="decreased",
            nep_php=200,
            house_php=120,
            delta_php=-80,
        ),
    ]
    parsed = parse_hgab_page(_payload(rows), artifact_sha256="b" * 64)

    summary = reconcile_hgab_dataset(
        parsed.records,
        expected_count=2,
        expected_nep_centavos=30_000,
        expected_house_centavos=27_000,
        expected_quarantine_count=0,
    )

    assert summary.record_count == 2
    assert summary.net_difference_centavos == -3_000


def test_reconciliation_rejects_control_total_mismatch() -> None:
    parsed = parse_hgab_page(_payload([_row()]), artifact_sha256="b" * 64)

    with pytest.raises(StageChangeSchemaError, match="House control total"):
        reconcile_hgab_dataset(
            parsed.records,
            expected_count=1,
            expected_nep_centavos=10_000,
            expected_house_centavos=99_000,
            expected_quarantine_count=0,
        )
