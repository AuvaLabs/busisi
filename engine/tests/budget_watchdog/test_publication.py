from pathlib import Path

from engine.budget_watchdog.publication import build_publication

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
REVIEWED_CASES = 6
REQUIRED_CASES = 100
CONFIRMED_LINKS = 5
RELATED_DOSSIERS = 3
EVIDENCE_URLS = 2
TOTAL_APPROPRIATION_CENTAVOS = 5_400_000_000
TOTAL_CONTRACT_BUDGET_CENTAVOS = 2_865_806_373


def test_publication_exposes_reviewed_cases_and_closed_release_gate() -> None:
    publication = build_publication(GOLDEN_PATH)

    assert publication.release_gate.reviewed_cases == REVIEWED_CASES
    assert publication.release_gate.required_cases == REQUIRED_CASES
    assert publication.release_gate.release_ready is False
    assert len(publication.dossiers) == REVIEWED_CASES
    assert sum(dossier.is_confirmed_link for dossier in publication.dossiers) == CONFIRMED_LINKS
    assert sum(dossier.is_quarantined for dossier in publication.dossiers) == 1
    assert publication.available_years == (2022, 2023, 2024, 2025, 2026)
    assert publication.total_appropriation_centavos == TOTAL_APPROPRIATION_CENTAVOS
    assert publication.total_contract_budget_centavos == TOTAL_CONTRACT_BUDGET_CENTAVOS


def test_publication_builds_transparent_repeated_funding_signal() -> None:
    publication = build_publication(GOLDEN_PATH)

    assert len(publication.watchlist) == 1
    item = publication.watchlist[0]
    assert item.code == "repeated_positive_funding"
    assert item.years == (2024, 2025)
    assert item.amounts_centavos == (1_000_000_000, 200_000_000)
    assert len(item.dossier_slugs) == RELATED_DOSSIERS
    assert "separate phases" in item.limitations.lower()


def test_quarantined_dossier_never_claims_a_link() -> None:
    publication = build_publication(GOLDEN_PATH)
    dossier = next(item for item in publication.dossiers if item.is_quarantined)

    assert dossier.case_id == "corazon-2026-completion"
    assert dossier.contract_id == "26HI0094"
    assert dossier.is_confirmed_link is False
    assert dossier.status_label == "Quarantined candidate"
    assert "requires" in dossier.match_limitations.lower()
    assert len(dossier.evidence_urls) == EVIDENCE_URLS
