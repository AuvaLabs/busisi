from pathlib import Path

from engine.budget_watchdog.golden import evaluate_golden_cases, load_golden_cases
from engine.budget_watchdog.identity import LinkConfidence

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
SEEDED_REVIEWED_CASES = 6


def test_seeded_golden_cases_match_reviewed_expectations() -> None:
    cases = load_golden_cases(GOLDEN_PATH)
    summary = evaluate_golden_cases(cases)

    assert summary.total == SEEDED_REVIEWED_CASES
    assert summary.passed == SEEDED_REVIEWED_CASES
    assert summary.agreement == 1
    assert summary.meets_agreement_gate is True
    assert summary.meets_minimum_size is False
    assert summary.release_ready is False


def test_zero_budget_case_stays_quarantined_as_candidate() -> None:
    cases = load_golden_cases(GOLDEN_PATH)
    case = next(item for item in cases if item.case_id == "corazon-2026-completion")
    result = evaluate_golden_cases((case,)).results[0]

    assert result.actual_confidence is LinkConfidence.CANDIDATE
    assert result.actual_selected_contract_id is None
    assert result.actual_top_contract_id == "26HI0094"
    assert result.passed is True
