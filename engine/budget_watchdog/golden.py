"""Reviewed linkage cases and release-gate evaluation."""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.identity import (
    BudgetProject,
    DeliveryProject,
    LinkConfidence,
    match_candidates,
)

MINIMUM_GOLDEN_CASES = 100
MINIMUM_AGREEMENT = Decimal("0.95")


class GoldenSetError(ValueError):
    """Raised when reviewed fixtures do not satisfy the golden-set schema."""


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    evidence_urls: tuple[str, ...]
    budget: BudgetProject
    candidates: tuple[DeliveryProject, ...]
    expected_confidence: LinkConfidence
    expected_selected_contract_id: str | None
    expected_top_contract_id: str


@dataclass(frozen=True, slots=True)
class GoldenCaseResult:
    case_id: str
    expected_confidence: LinkConfidence
    actual_confidence: LinkConfidence
    expected_selected_contract_id: str | None
    actual_selected_contract_id: str | None
    expected_top_contract_id: str
    actual_top_contract_id: str | None
    passed: bool


@dataclass(frozen=True, slots=True)
class GoldenSummary:
    total: int
    passed: int
    agreement: Decimal
    meets_minimum_size: bool
    meets_agreement_gate: bool
    release_ready: bool
    results: tuple[GoldenCaseResult, ...]


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GoldenSetError(f"{field} must be an object")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise GoldenSetError(f"{field} must be text")
    return value.strip()


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GoldenSetError(f"{field} must be an integer")
    return int(value)


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _budget(value: Any, field: str) -> BudgetProject:
    record = _object(value, field)
    return BudgetProject(
        budget_line_id=_text(record.get("budget_line_id"), f"{field}.budget_line_id"),
        fiscal_year=_integer(record.get("fiscal_year"), f"{field}.fiscal_year"),
        description=_text(record.get("description"), f"{field}.description"),
        amount_centavos=_integer(record.get("amount_centavos"), f"{field}.amount_centavos"),
        location=_text(record.get("location"), f"{field}.location", allow_empty=True),
    )


def _delivery(value: Any, field: str) -> DeliveryProject:
    record = _object(value, field)
    return DeliveryProject(
        contract_id=_text(record.get("contract_id"), f"{field}.contract_id"),
        fiscal_year=_integer(record.get("fiscal_year"), f"{field}.fiscal_year"),
        description=_text(record.get("description"), f"{field}.description"),
        budget_centavos=_integer(record.get("budget_centavos"), f"{field}.budget_centavos"),
        location=_text(record.get("location"), f"{field}.location", allow_empty=True),
        source_of_funds=_text(
            record.get("source_of_funds"),
            f"{field}.source_of_funds",
            allow_empty=True,
        ),
    )


def _case(value: Any, index: int) -> GoldenCase:
    field = f"cases[{index}]"
    record = _object(value, field)
    raw_urls = record.get("evidence_urls")
    if not isinstance(raw_urls, list) or not raw_urls:
        raise GoldenSetError(f"{field}.evidence_urls must be a non-empty array")
    evidence_urls = tuple(_text(url, f"{field}.evidence_urls") for url in raw_urls)
    if any(urlparse(url).scheme != "https" for url in evidence_urls):
        raise GoldenSetError(f"{field}.evidence_urls must use HTTPS")
    raw_candidates = record.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise GoldenSetError(f"{field}.candidates must be a non-empty array")
    try:
        expected_confidence = LinkConfidence(
            _text(record.get("expected_confidence"), f"{field}.expected_confidence")
        )
    except (TypeError, ValueError) as exc:
        raise GoldenSetError(f"{field}.expected_confidence is invalid") from exc
    return GoldenCase(
        case_id=_text(record.get("case_id"), f"{field}.case_id"),
        evidence_urls=evidence_urls,
        budget=_budget(record.get("budget"), f"{field}.budget"),
        candidates=tuple(
            _delivery(candidate, f"{field}.candidates[{candidate_index}]")
            for candidate_index, candidate in enumerate(raw_candidates)
        ),
        expected_confidence=expected_confidence,
        expected_selected_contract_id=_optional_text(
            record.get("expected_selected_contract_id"),
            f"{field}.expected_selected_contract_id",
        ),
        expected_top_contract_id=_text(
            record.get("expected_top_contract_id"),
            f"{field}.expected_top_contract_id",
        ),
    )


def load_golden_cases(path: Path) -> tuple[GoldenCase, ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldenSetError(f"cannot read golden set: {path}") from exc
    body = _object(document, "root")
    if body.get("schema_version") != 1:
        raise GoldenSetError("schema_version must be 1")
    raw_cases = body.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise GoldenSetError("cases must be a non-empty array")
    cases = tuple(_case(case, index) for index, case in enumerate(raw_cases))
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise GoldenSetError("case_id values must be unique")
    return cases


def evaluate_golden_cases(cases: tuple[GoldenCase, ...]) -> GoldenSummary:
    if not cases:
        raise GoldenSetError("cannot evaluate an empty golden set")
    results: list[GoldenCaseResult] = []
    for case in cases:
        decision = match_candidates(case.budget, case.candidates)
        actual_top = decision.candidates[0].contract_id if decision.candidates else None
        passed = (
            decision.confidence is case.expected_confidence
            and decision.selected_contract_id == case.expected_selected_contract_id
            and actual_top == case.expected_top_contract_id
        )
        results.append(
            GoldenCaseResult(
                case_id=case.case_id,
                expected_confidence=case.expected_confidence,
                actual_confidence=decision.confidence,
                expected_selected_contract_id=case.expected_selected_contract_id,
                actual_selected_contract_id=decision.selected_contract_id,
                expected_top_contract_id=case.expected_top_contract_id,
                actual_top_contract_id=actual_top,
                passed=passed,
            )
        )
    passed_count = sum(result.passed for result in results)
    agreement = Decimal(passed_count) / Decimal(len(results))
    meets_size = len(results) >= MINIMUM_GOLDEN_CASES
    meets_agreement = agreement >= MINIMUM_AGREEMENT
    return GoldenSummary(
        total=len(results),
        passed=passed_count,
        agreement=agreement,
        meets_minimum_size=meets_size,
        meets_agreement_gate=meets_agreement,
        release_ready=meets_size and meets_agreement,
        results=tuple(results),
    )
