"""Review signals for procurement and implementation inconsistencies."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

FULL_PROGRESS_PERCENT = Decimal("100")


class DeliveryFlagCode(StrEnum):
    ZERO_DOWNSTREAM_BUDGET = "zero_downstream_budget"
    STATUS_PROGRESS_CONFLICT = "status_progress_conflict"
    AWARD_ABOVE_ABC = "award_above_abc"


@dataclass(frozen=True, slots=True)
class DeliverySnapshot:
    contract_id: str
    appropriation_centavos: int
    project_budget_centavos: int | None
    abc_centavos: int | None
    award_centavos: int | None
    status: str
    progress_percent: Decimal

    def __post_init__(self) -> None:
        if not self.contract_id.strip():
            raise ValueError("contract_id must not be empty")
        amounts = (
            self.appropriation_centavos,
            self.project_budget_centavos,
            self.abc_centavos,
            self.award_centavos,
        )
        if any(amount is not None and amount < 0 for amount in amounts):
            raise ValueError("amounts must not be negative")
        if not self.status.strip():
            raise ValueError("status must not be empty")
        if not Decimal("0") <= self.progress_percent <= FULL_PROGRESS_PERCENT:
            raise ValueError("progress_percent must be between zero and 100")


@dataclass(frozen=True, slots=True)
class DeliveryFlag:
    code: DeliveryFlagCode
    summary: str
    evidence: Mapping[str, Any]
    limitations: str


def _flag(
    code: DeliveryFlagCode,
    summary: str,
    evidence: dict[str, Any],
    limitations: str,
) -> DeliveryFlag:
    return DeliveryFlag(code, summary, MappingProxyType(evidence), limitations)


def evaluate_delivery_flags(snapshot: DeliverySnapshot) -> tuple[DeliveryFlag, ...]:
    flags: list[DeliveryFlag] = []
    if snapshot.appropriation_centavos > 0 and snapshot.project_budget_centavos == 0:
        flags.append(
            _flag(
                DeliveryFlagCode.ZERO_DOWNSTREAM_BUDGET,
                "A positive appropriation is linked to a zero downstream project budget.",
                {
                    "contract_id": snapshot.contract_id,
                    "appropriation_centavos": snapshot.appropriation_centavos,
                    "project_budget_centavos": snapshot.project_budget_centavos,
                },
                "This can reflect publication lag or an incorrect link and is not proof of missing funds.",
            )
        )

    normalized_status = snapshot.status.casefold().replace("-", " ")
    if (
        normalized_status in {"ongoing", "on going"}
        and snapshot.progress_percent >= FULL_PROGRESS_PERCENT
    ):
        flags.append(
            _flag(
                DeliveryFlagCode.STATUS_PROGRESS_CONFLICT,
                "The project is marked ongoing while reported progress is 100 percent.",
                {
                    "contract_id": snapshot.contract_id,
                    "status": snapshot.status,
                    "progress_percent": str(snapshot.progress_percent),
                },
                "The status field may update later than the progress field.",
            )
        )

    if (
        snapshot.abc_centavos is not None
        and snapshot.award_centavos is not None
        and snapshot.award_centavos > snapshot.abc_centavos
    ):
        flags.append(
            _flag(
                DeliveryFlagCode.AWARD_ABOVE_ABC,
                "The reported award amount exceeds the approved budget for the contract.",
                {
                    "contract_id": snapshot.contract_id,
                    "abc_centavos": snapshot.abc_centavos,
                    "award_centavos": snapshot.award_centavos,
                    "difference_centavos": snapshot.award_centavos - snapshot.abc_centavos,
                },
                "Source amendments and corrected procurement records must be checked.",
            )
        )
    return tuple(flags)
