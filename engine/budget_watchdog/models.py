"""Canonical immutable records shared by ingestion and analysis."""

from dataclasses import dataclass
from enum import StrEnum


class BudgetStage(StrEnum):
    PREVIOUS_GAA = "previous_gaa"
    NEP = "nep"
    HOUSE_GAB = "house_gab"
    SENATE_GAB = "senate_gab"
    BICAM = "bicam"
    GAA = "gaa"


BUDGET_STAGE_ORDER = (
    BudgetStage.PREVIOUS_GAA,
    BudgetStage.NEP,
    BudgetStage.HOUSE_GAB,
    BudgetStage.SENATE_GAB,
    BudgetStage.BICAM,
    BudgetStage.GAA,
)

MINIMUM_FISCAL_YEAR = 1900
MAXIMUM_FISCAL_YEAR = 2200


def validate_fiscal_year(fiscal_year: int) -> None:
    if (
        isinstance(fiscal_year, bool)
        or not MINIMUM_FISCAL_YEAR <= fiscal_year <= MAXIMUM_FISCAL_YEAR
    ):
        raise ValueError("fiscal_year must be between 1900 and 2200")


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class BudgetStageAmount:
    project_key: str
    fiscal_year: int
    stage: BudgetStage
    amount_centavos: int | None
    source_id: str
    source_record_id: str

    def __post_init__(self) -> None:
        _require_text(self.project_key, "project_key")
        validate_fiscal_year(self.fiscal_year)
        if self.amount_centavos is not None and self.amount_centavos < 0:
            raise ValueError("amount_centavos must not be negative")
        _require_text(self.source_id, "source_id")
        _require_text(self.source_record_id, "source_record_id")


@dataclass(frozen=True, slots=True)
class ProjectYearAmount:
    project_family_id: str
    fiscal_year: int
    amount_centavos: int
    source_record_id: str

    def __post_init__(self) -> None:
        _require_text(self.project_family_id, "project_family_id")
        validate_fiscal_year(self.fiscal_year)
        if self.amount_centavos < 0:
            raise ValueError("amount_centavos must not be negative")
        _require_text(self.source_record_id, "source_record_id")
