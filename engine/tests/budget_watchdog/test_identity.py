from dataclasses import replace

import pytest

from engine.budget_watchdog.identity import (
    BudgetProject,
    DeliveryProject,
    LinkConfidence,
    match_candidates,
)

HIGH_CONFIDENCE_THRESHOLD = 80


def _agoncillo_budget() -> BudgetProject:
    return BudgetProject(
        budget_line_id="gaa-2023-agoncillo",
        fiscal_year=2023,
        description=(
            "Rehabilitation of Multi-Purpose Facilities (Doña Corazon Agoncillo "
            "Sports and Cultural Center), Brgy. Tierra Alta, Taal, Batangas"
        ),
        amount_centavos=1_000_000_000,
        location="Taal, Batangas",
    )


def _agoncillo_contract(contract_id: str = "23DB0126") -> DeliveryProject:
    return DeliveryProject(
        contract_id=contract_id,
        fiscal_year=2023,
        description=(
            "CONVERGENCE AND SPECIAL SUPPORT PROGRAM - BASIC INFRASTRUCTURE "
            "PROGRAM - REHABILITATION OF MULTI-PURPOSE FACILITIES (DOÑA CORAZON "
            "AGONCILLO SPORTS AND CULTURAL CENTER), BRGY. TIERRA ALTA, TAAL"
        ),
        budget_centavos=990_000_000,
        location="Batangas 1st DEO, Region IV-A",
        source_of_funds="Regular Infra - GAA 2023 CSSP",
    )


def test_authentic_gaa_to_dpwh_shape_is_high_confidence() -> None:
    decision = match_candidates(_agoncillo_budget(), (_agoncillo_contract(),))

    assert decision.confidence is LinkConfidence.HIGH
    assert decision.selected_contract_id == "23DB0126"
    assert decision.candidates[0].score >= HIGH_CONFIDENCE_THRESHOLD
    assert "year_match" in decision.candidates[0].signals
    assert "amount_compatible" in decision.candidates[0].signals


def test_shared_official_reference_is_exact() -> None:
    budget = replace(
        _agoncillo_budget(),
        source_references=("official-reference-123",),
    )
    contract = replace(
        _agoncillo_contract(),
        source_references=("official-reference-123",),
    )

    decision = match_candidates(budget, (contract,))

    assert decision.confidence is LinkConfidence.EXACT
    assert decision.selected_contract_id == "23DB0126"


def test_multiple_equally_strong_candidates_are_quarantined() -> None:
    decision = match_candidates(
        _agoncillo_budget(),
        (
            _agoncillo_contract("23DB0126"),
            _agoncillo_contract("23DB0999"),
        ),
    )

    assert decision.confidence is LinkConfidence.AMBIGUOUS
    assert decision.selected_contract_id is None


def test_year_conflict_prevents_automatic_link() -> None:
    old_contract = replace(_agoncillo_contract(), fiscal_year=2022)

    decision = match_candidates(_agoncillo_budget(), (old_contract,))

    assert decision.confidence is LinkConfidence.UNLINKED
    assert decision.selected_contract_id is None


def test_identity_models_reject_invalid_boundary_values() -> None:
    with pytest.raises(ValueError, match="fiscal_year"):
        replace(_agoncillo_budget(), fiscal_year=0)
    with pytest.raises(ValueError, match="amount_centavos"):
        replace(_agoncillo_budget(), amount_centavos=-1)
    with pytest.raises(ValueError, match="contract_id"):
        replace(_agoncillo_contract(), contract_id="")
