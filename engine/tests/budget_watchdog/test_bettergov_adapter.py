import json

import pytest

from engine.budget_watchdog.adapters.bettergov import (
    SourceSchemaError,
    parse_dpwh_detail,
    parse_dpwh_search,
    parse_gaa_search,
)
from engine.budget_watchdog.delivery_flags import evaluate_delivery_flags
from engine.budget_watchdog.identity import LinkConfidence, match_candidates

EXPECTED_ABC_CENTAVOS = 990_000_000
EXPECTED_AWARD_CENTAVOS = 960_300_000


GAA_RESPONSE = {
    "meta": {"dataset": "gaa", "currency": "PHP", "scale": "pesos"},
    "data": [
        {
            "fam_key": "18-001|rehabilitation of multipurpose facilities agoncillo",
            "name": (
                "Rehabilitation of Multi-Purpose Facilities (Doña Corazon Agoncillo "
                "Sports and Cultural Center), Brgy. Tierra Alta, Taal, Batangas"
            ),
            "years": {"2023": {"count": 1, "amount": 10000000}},
        }
    ],
}

DPWH_SEARCH_RESPONSE = {
    "status": 200,
    "data": {
        "data": [
            {
                "contractId": "23DB0126",
                "description": (
                    "CONVERGENCE AND SPECIAL SUPPORT PROGRAM - REHABILITATION OF "
                    "MULTI-PURPOSE FACILITIES (DOÑA CORAZON AGONCILLO SPORTS AND "
                    "CULTURAL CENTER), BRGY. TIERRA ALTA, TAAL"
                ),
                "budget": 9900000,
                "infraYear": "2023",
                "sourceOfFunds": "Regular Infra - GAA 2023 CSSP",
                "location": {"province": "Batangas 1st DEO", "region": "Region IV-A"},
            }
        ]
    },
}

DPWH_DETAIL_RESPONSE = {
    "data": {
        "contractId": "23DB0126",
        "budget": 9900000,
        "status": "Completed",
        "progress": 100,
        "procurement": {"abc": "9900000.00", "awardAmount": "9603000"},
    }
}


def _payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def test_live_shape_adapters_produce_a_high_confidence_trace() -> None:
    budgets = parse_gaa_search(_payload(GAA_RESPONSE), fiscal_year=2023)
    deliveries = parse_dpwh_search(_payload(DPWH_SEARCH_RESPONSE))

    decision = match_candidates(budgets[0], deliveries)

    assert decision.confidence is LinkConfidence.HIGH
    assert decision.selected_contract_id == "23DB0126"


def test_detail_adapter_preserves_procurement_amounts_for_flags() -> None:
    snapshot = parse_dpwh_detail(
        _payload(DPWH_DETAIL_RESPONSE),
        appropriation_centavos=1_000_000_000,
    )

    assert snapshot.abc_centavos == EXPECTED_ABC_CENTAVOS
    assert snapshot.award_centavos == EXPECTED_AWARD_CENTAVOS
    assert evaluate_delivery_flags(snapshot) == ()


def test_gaa_adapter_rejects_wrong_currency_and_missing_year() -> None:
    wrong_currency = {**GAA_RESPONSE, "meta": {**GAA_RESPONSE["meta"], "currency": "USD"}}
    with pytest.raises(SourceSchemaError, match="currency"):
        parse_gaa_search(_payload(wrong_currency), fiscal_year=2023)

    with pytest.raises(SourceSchemaError, match="fiscal year"):
        parse_gaa_search(_payload(GAA_RESPONSE), fiscal_year=2024)


def test_dpwh_adapter_preserves_zero_budget_with_missing_funding_source() -> None:
    record = {
        **DPWH_SEARCH_RESPONSE["data"]["data"][0],
        "contractId": "26HI0094",
        "infraYear": "2026",
        "budget": 0,
        "sourceOfFunds": None,
    }
    payload = {**DPWH_SEARCH_RESPONSE, "data": {"data": [record]}}

    projects = parse_dpwh_search(_payload(payload))

    assert projects[0].budget_centavos == 0
    assert projects[0].source_of_funds == ""
