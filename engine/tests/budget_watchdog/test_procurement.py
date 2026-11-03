import json

import pytest

from engine.budget_watchdog.procurement import (
    ProcurementCatalogError,
    load_procurement_catalog,
    summarize_procurement_catalog,
)


def _payload() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "checked_at": "2026-11-03T15:00:00+04:00",
            "sources": [
                {
                    "source_id": "philgeps-25hi0028",
                    "title": "PhilGEPS bid notice 11439469",
                    "publisher": "PhilGEPS",
                    "document_type": "bid_notice",
                    "fiscal_year": 2025,
                    "reporting_cutoff": None,
                    "source_url": "https://notices.philgeps.gov.ph/notice?refid=11439469",
                    "acquisition_status": "verified_archived",
                    "artifact_sha256": "a" * 64,
                    "byte_size": 25473,
                    "page_count": None,
                    "evidence_note": "Original official HTML archived.",
                }
            ],
            "records": [
                {
                    "evidence_id": "philgeps-25hi0028-bid",
                    "case_id": "corazon-2025-completion",
                    "contract_id": "25HI0028",
                    "fiscal_year": 2025,
                    "source_id": "philgeps-25hi0028",
                    "evidence_type": "bid_notice",
                    "match_basis": "exact_contract_id",
                    "project_title": "Construction completion of multi-purpose building",
                    "procuring_entity": "DPWH Cebu 5th DEO",
                    "procurement_mode": "Public Bidding",
                    "procurement_status": "Awarded",
                    "page_number": None,
                    "reference_number": "11439469",
                    "abc_centavos": 198000000,
                    "contract_cost_centavos": None,
                    "savings_centavos": None,
                    "observers": [],
                    "events": [
                        {"stage": "advertisement", "event_date": "2024-11-06", "date_kind": "actual"},
                        {"stage": "pre_bid", "event_date": "2024-11-13", "date_kind": "actual"},
                        {"stage": "bid_opening", "event_date": "2024-11-26", "date_kind": "actual"},
                    ],
                    "reviewed_at": "2026-11-03",
                    "boundary_note": "A bid notice is not payment or proof of completion.",
                }
            ],
            "coverage": [
                {
                    "case_id": "corazon-2025-completion",
                    "contract_id": "25HI0028",
                    "fiscal_year": 2025,
                    "status": "exact_evidence",
                    "record_count": 1,
                    "review_note": "Exact solicitation number located.",
                    "reviewed_at": "2026-11-03",
                }
            ],
        }
    ).encode()


def test_loads_exact_procurement_evidence_and_summary() -> None:
    catalog = load_procurement_catalog(_payload())
    summary = summarize_procurement_catalog(catalog)

    assert summary.checked_projects == 1
    assert summary.projects_with_evidence == 1
    assert summary.archived_sources == 1
    assert summary.exact_records == 1
    assert catalog.records[0].events[2].stage == "bid_opening"


def _mutate(mutator) -> bytes:
    payload = json.loads(_payload())
    mutator(payload)
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", "JSON is invalid"),
        (_mutate(lambda root: root.update(schema_version=2)), "schema version"),
        (
            _mutate(lambda root: root["sources"][0].update(artifact_sha256=None)),
            "verified source",
        ),
        (
            _mutate(lambda root: root["records"][0].update(source_id="missing")),
            "unknown source",
        ),
        (
            _mutate(lambda root: root["records"][0].update(savings_centavos=1)),
            "savings",
        ),
        (
            _mutate(lambda root: root["records"][0].update(abc_centavos=1.5)),
            "integer centavos",
        ),
        (
            _mutate(
                lambda root: root["records"][0].update(
                    events=[
                        {"stage": "notice_to_proceed", "event_date": "2024-01-01", "date_kind": "actual"},
                        {"stage": "advertisement", "event_date": "2024-02-01", "date_kind": "actual"},
                    ]
                )
            ),
            "event order",
        ),
        (
            _mutate(lambda root: root["coverage"][0].update(record_count=0)),
            "record_count",
        ),
        (
            _mutate(lambda root: root["coverage"][0].update(status="not_located")),
            "not_located",
        ),
        (
            _mutate(
                lambda root: root["sources"][0].update(artifact_sha256="z" * 64)
            ),
            "SHA-256",
        ),
        (
            _mutate(
                lambda root: root["sources"][0].update(
                    document_type="annual_procurement_plan"
                )
            ),
            "source type",
        ),
        (
            _mutate(
                lambda root: root["records"][0].update(case_id="unreviewed-case")
            ),
            "coverage row",
        ),
        (
            _mutate(
                lambda root: root["coverage"].append(
                    {
                        **root["coverage"][0],
                        "case_id": "duplicate-contract-case",
                        "record_count": 0,
                        "status": "not_located",
                    }
                )
            ),
            "duplicate contract_id",
        ),
    ],
)
def test_rejects_unverifiable_or_contradictory_procurement_claims(
    payload: bytes, message: str
) -> None:
    with pytest.raises(ProcurementCatalogError, match=message):
        load_procurement_catalog(payload)
