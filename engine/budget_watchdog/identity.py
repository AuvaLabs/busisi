"""Deterministic, confidence-aware links between budget and delivery records."""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from engine.budget_watchdog.models import validate_fiscal_year

GENERIC_TOKENS = frozenset(
    {
        "a",
        "and",
        "at",
        "barangay",
        "brgy",
        "for",
        "in",
        "of",
        "the",
        "to",
    }
)


class LinkConfidence(StrEnum):
    EXACT = "exact"
    HIGH = "high"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    UNLINKED = "unlinked"


@dataclass(frozen=True, slots=True)
class MatchThresholds:
    high_score: int = 80
    candidate_score: int = 55
    ambiguity_margin: int = 5
    strong_title_recall: float = 0.75
    moderate_title_recall: float = 0.5
    compatible_amount_floor: float = 0.8
    nearby_amount_delta: float = 0.1


DEFAULT_MATCH_THRESHOLDS = MatchThresholds()


@dataclass(frozen=True, slots=True)
class BudgetProject:
    budget_line_id: str
    fiscal_year: int
    description: str
    amount_centavos: int
    location: str
    source_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.budget_line_id, "budget_line_id")
        validate_fiscal_year(self.fiscal_year)
        _require_text(self.description, "description")
        if self.amount_centavos < 0:
            raise ValueError("amount_centavos must not be negative")
        _validate_references(self.source_references)


@dataclass(frozen=True, slots=True)
class DeliveryProject:
    contract_id: str
    fiscal_year: int
    description: str
    budget_centavos: int
    location: str
    source_of_funds: str
    source_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.contract_id, "contract_id")
        validate_fiscal_year(self.fiscal_year)
        _require_text(self.description, "description")
        if self.budget_centavos < 0:
            raise ValueError("budget_centavos must not be negative")
        _validate_references(self.source_references)


@dataclass(frozen=True, slots=True)
class CandidateScore:
    contract_id: str
    score: int
    signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchDecision:
    confidence: LinkConfidence
    selected_contract_id: str | None
    candidates: tuple[CandidateScore, ...]
    limitations: str


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _validate_references(references: tuple[str, ...]) -> None:
    if any(not reference.strip() for reference in references):
        raise ValueError("source_references must not contain empty values")


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        token for token in re.findall(r"[a-z0-9]+", without_marks) if token not in GENERIC_TOKENS
    }


def _score_candidate(
    budget: BudgetProject,
    delivery: DeliveryProject,
    thresholds: MatchThresholds,
) -> CandidateScore:
    if budget.fiscal_year != delivery.fiscal_year:
        return CandidateScore(delivery.contract_id, 0, ("year_conflict",))

    score = 20
    signals = ["year_match"]
    budget_tokens = _tokens(budget.description)
    delivery_tokens = _tokens(delivery.description)
    title_recall = len(budget_tokens & delivery_tokens) / max(len(budget_tokens), 1)
    if title_recall >= thresholds.strong_title_recall:
        score += 40
        signals.append("strong_title_match")
    elif title_recall >= thresholds.moderate_title_recall:
        score += 25
        signals.append("moderate_title_match")

    if budget.amount_centavos > 0:
        amount_ratio = delivery.budget_centavos / budget.amount_centavos
        if thresholds.compatible_amount_floor <= amount_ratio <= 1:
            score += 20
            signals.append("amount_compatible")
        elif abs(amount_ratio - 1) <= thresholds.nearby_amount_delta:
            score += 15
            signals.append("amount_nearby")

    funding_tokens = _tokens(delivery.source_of_funds)
    if "gaa" in funding_tokens and str(budget.fiscal_year) in funding_tokens:
        score += 10
        signals.append("funding_year_match")

    location_tokens = _tokens(budget.location)
    delivery_place_tokens = _tokens(f"{delivery.description} {delivery.location}")
    if location_tokens and location_tokens <= delivery_place_tokens:
        score += 10
        signals.append("location_match")
    return CandidateScore(delivery.contract_id, score, tuple(signals))


def _has_shared_reference(budget: BudgetProject, delivery: DeliveryProject) -> bool:
    return bool(set(budget.source_references) & set(delivery.source_references))


def match_candidates(
    budget: BudgetProject,
    deliveries: tuple[DeliveryProject, ...],
    thresholds: MatchThresholds = DEFAULT_MATCH_THRESHOLDS,
) -> MatchDecision:
    """Select only unique exact or high-confidence links; quarantine ambiguity."""

    exact = [delivery for delivery in deliveries if _has_shared_reference(budget, delivery)]
    scored = tuple(
        sorted(
            (_score_candidate(budget, delivery, thresholds) for delivery in deliveries),
            key=lambda candidate: (-candidate.score, candidate.contract_id),
        )
    )
    if len(exact) == 1:
        return MatchDecision(
            LinkConfidence.EXACT,
            exact[0].contract_id,
            scored,
            "The records share an explicit official reference.",
        )
    if len(exact) > 1:
        return MatchDecision(
            LinkConfidence.AMBIGUOUS,
            None,
            scored,
            "Multiple delivery records share the same reference and require review.",
        )
    if not scored or scored[0].score < thresholds.candidate_score:
        return MatchDecision(
            LinkConfidence.UNLINKED,
            None,
            scored,
            "No candidate meets the deterministic publication threshold.",
        )

    best = scored[0]
    competing = [
        candidate
        for candidate in scored[1:]
        if best.score - candidate.score <= thresholds.ambiguity_margin
    ]
    if competing:
        return MatchDecision(
            LinkConfidence.AMBIGUOUS,
            None,
            scored,
            "Multiple similarly scored candidates are quarantined for review.",
        )
    if best.score >= thresholds.high_score:
        return MatchDecision(
            LinkConfidence.HIGH,
            best.contract_id,
            scored,
            "This is a derived link and does not share an official identifier.",
        )
    return MatchDecision(
        LinkConfidence.CANDIDATE,
        None,
        scored,
        "The candidate requires documentary or human verification.",
    )
