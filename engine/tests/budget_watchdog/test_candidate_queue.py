from engine.budget_watchdog.candidate_queue import generate_review_candidates
from engine.budget_watchdog.identity import BudgetProject, DeliveryProject, LinkConfidence
from engine.budget_watchdog.storage import CanonicalStore

ARTIFACT_SHA = "b" * 64
HIGH_CONFIDENCE_THRESHOLD = 80


def _budget() -> BudgetProject:
    return BudgetProject(
        budget_line_id="18-001|sample-building",
        fiscal_year=2026,
        description="Construction of Sample Building, Sample City",
        amount_centavos=1_000_000_000,
        location="",
    )


def _delivery(contract_id: str = "26XX0001") -> DeliveryProject:
    return DeliveryProject(
        contract_id=contract_id,
        fiscal_year=2026,
        description="CONSTRUCTION OF SAMPLE BUILDING, SAMPLE CITY",
        budget_centavos=990_000_000,
        location="Sample DEO",
        source_of_funds="Regular Infra - GAA 2026",
    )


def test_candidate_queue_emits_unique_high_confidence_family(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    with CanonicalStore(database) as store:
        store.store_budget_projects((_budget(),), ARTIFACT_SHA)
        store.store_delivery_projects((_delivery(),), ARTIFACT_SHA)

    candidates = generate_review_candidates(database, fiscal_years=(2026,), limit=10)

    assert len(candidates) == 1
    assert candidates[0].confidence is LinkConfidence.HIGH
    assert candidates[0].contract_id == "26XX0001"
    assert candidates[0].score >= HIGH_CONFIDENCE_THRESHOLD
    assert candidates[0].budget_evidence_url.startswith("https://budget.bettergov.ph/")
    assert candidates[0].delivery_evidence_url.endswith("/26XX0001")


def test_candidate_queue_excludes_non_unique_delivery_family(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    with CanonicalStore(database) as store:
        store.store_budget_projects((_budget(),), ARTIFACT_SHA)
        store.store_delivery_projects(
            (_delivery("26XX0001"), _delivery("26XX0002")),
            ARTIFACT_SHA,
        )

    assert generate_review_candidates(database, fiscal_years=(2026,), limit=10) == ()
