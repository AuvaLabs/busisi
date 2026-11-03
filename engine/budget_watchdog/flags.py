"""Transparent deterministic review signals for budget records."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from engine.budget_watchdog.models import (
    BUDGET_STAGE_ORDER,
    BudgetStage,
    BudgetStageAmount,
    ProjectYearAmount,
)


class FlagCode(StrEnum):
    INTRODUCED_AFTER_NEP = "introduced_after_nep"
    STAGE_AMOUNT_INCREASE = "stage_amount_increase"
    REPEATED_POSITIVE_FUNDING = "repeated_positive_funding"


MINIMUM_REPEATED_FUNDING_YEARS = 2


@dataclass(frozen=True, slots=True)
class ReviewFlag:
    code: FlagCode
    summary: str
    evidence: Mapping[str, Any]
    limitations: str


def _flag(
    code: FlagCode,
    summary: str,
    evidence: dict[str, Any],
    limitations: str,
) -> ReviewFlag:
    return ReviewFlag(code, summary, MappingProxyType(evidence), limitations)


def _stage_flags(stages: tuple[BudgetStageAmount, ...]) -> list[ReviewFlag]:
    if not stages:
        return []
    by_stage = {record.stage: record for record in stages}
    flags: list[ReviewFlag] = []
    nep = by_stage.get(BudgetStage.NEP)
    later_positive = [
        by_stage[stage]
        for stage in BUDGET_STAGE_ORDER[BUDGET_STAGE_ORDER.index(BudgetStage.NEP) + 1 :]
        if stage in by_stage and (by_stage[stage].amount_centavos or 0) > 0
    ]
    if nep is not None and (nep.amount_centavos or 0) == 0 and later_positive:
        first = later_positive[0]
        flags.append(
            _flag(
                FlagCode.INTRODUCED_AFTER_NEP,
                "A positive appropriation first appears after the NEP stage.",
                {
                    "nep_amount_centavos": nep.amount_centavos,
                    "first_positive_stage": first.stage.value,
                    "first_positive_amount_centavos": first.amount_centavos,
                    "source_record_ids": [nep.source_record_id, first.source_record_id],
                },
                "A missing or zero NEP value can also reflect incomplete source coverage.",
            )
        )

    known = [
        by_stage[stage]
        for stage in BUDGET_STAGE_ORDER
        if stage in by_stage and by_stage[stage].amount_centavos is not None
    ]
    increases = []
    for previous, current in zip(known, known[1:], strict=False):
        assert previous.amount_centavos is not None
        assert current.amount_centavos is not None
        if current.amount_centavos > previous.amount_centavos:
            increases.append((previous, current))
    if increases:
        previous, current = increases[-1]
        previous_amount = previous.amount_centavos
        current_amount = current.amount_centavos
        assert previous_amount is not None
        assert current_amount is not None
        flags.append(
            _flag(
                FlagCode.STAGE_AMOUNT_INCREASE,
                "The appropriation increased between documented budget stages.",
                {
                    "from_stage": previous.stage.value,
                    "to_stage": current.stage.value,
                    "from_amount_centavos": previous_amount,
                    "to_amount_centavos": current_amount,
                    "increase_centavos": current_amount - previous_amount,
                    "source_record_ids": [
                        previous.source_record_id,
                        current.source_record_id,
                    ],
                },
                "An increase is a legislative change signal, not evidence of misconduct.",
            )
        )
    return flags


def _repeated_funding_flags(
    yearly_amounts: tuple[ProjectYearAmount, ...],
) -> list[ReviewFlag]:
    positive = tuple(record for record in yearly_amounts if record.amount_centavos > 0)
    by_year: dict[int, list[ProjectYearAmount]] = {}
    for record in positive:
        by_year.setdefault(record.fiscal_year, []).append(record)
    if len(by_year) < MINIMUM_REPEATED_FUNDING_YEARS:
        return []
    years = sorted(by_year)
    records = [record for year in years for record in by_year[year]]
    return [
        _flag(
            FlagCode.REPEATED_POSITIVE_FUNDING,
            "A related project family has positive appropriations in multiple years.",
            {
                "project_family_id": records[0].project_family_id,
                "positive_years": years,
                "amounts_centavos": [
                    sum(record.amount_centavos for record in by_year[year]) for year in years
                ],
                "source_record_ids": [record.source_record_id for record in records],
            },
            "A project family can contain separate phases, contracts, or physical assets.",
        )
    ]


def evaluate_budget_flags(
    *,
    stages: tuple[BudgetStageAmount, ...],
    yearly_amounts: tuple[ProjectYearAmount, ...],
) -> tuple[ReviewFlag, ...]:
    """Return stable, evidence-carrying flags without an opaque risk score."""

    return tuple(_stage_flags(stages) + _repeated_funding_flags(yearly_amounts))
