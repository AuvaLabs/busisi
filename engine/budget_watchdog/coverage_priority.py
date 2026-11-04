"""Transparent priority rules for bounded evidence-coverage acquisition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoveragePriorityFacts:
    reviewed: bool = False
    source_image_hint: bool = False
    high_value: bool = False
    joint_venture: bool = False
    repeated_contractor: bool = False
    integrity_question: bool = False
    coa_evidence: bool = False


@dataclass(frozen=True, slots=True)
class CoveragePriority:
    score: int
    reasons: tuple[str, ...]


_WEIGHTS = (
    ("source_image_hint", 30),
    ("high_value", 20),
    ("joint_venture", 20),
    ("repeated_contractor", 15),
    ("integrity_question", 10),
    ("coa_evidence", 25),
)


def classify_coverage_priority(facts: CoveragePriorityFacts) -> CoveragePriority:
    """Return a lower-is-earlier score and every disclosed reason used."""
    if facts.reviewed:
        return CoveragePriority(0, ("reviewed_dossier",))
    reasons = tuple(name for name, _ in _WEIGHTS if getattr(facts, name))
    reduction = sum(weight for name, weight in _WEIGHTS if getattr(facts, name))
    return CoveragePriority(max(5, 100 - reduction), reasons)
