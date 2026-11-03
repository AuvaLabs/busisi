from engine.budget_watchdog.flags import FlagCode, evaluate_budget_flags
from engine.budget_watchdog.models import BudgetStage, BudgetStageAmount, ProjectYearAmount

EXPECTED_STAGE_INCREASE_CENTAVOS = 1_500_000_000


def _stage(stage: BudgetStage, amount: int | None) -> BudgetStageAmount:
    return BudgetStageAmount(
        project_key="dpwh|sample-project",
        fiscal_year=2026,
        stage=stage,
        amount_centavos=amount,
        source_id=f"source-{stage.value}",
        source_record_id=f"record-{stage.value}",
    )


def test_flags_project_introduced_after_nep_and_later_increased() -> None:
    flags = evaluate_budget_flags(
        stages=(
            _stage(BudgetStage.NEP, None),
            _stage(BudgetStage.HOUSE_GAB, 2_000_000_000),
            _stage(BudgetStage.GAA, 3_500_000_000),
        ),
        yearly_amounts=(),
    )

    assert [flag.code for flag in flags] == [
        FlagCode.INTRODUCED_AFTER_NEP,
        FlagCode.STAGE_AMOUNT_INCREASE,
    ]
    assert flags[0].evidence["first_positive_stage"] == "house_gab"
    assert flags[1].evidence["increase_centavos"] == EXPECTED_STAGE_INCREASE_CENTAVOS


def test_flags_repeated_positive_funding_without_calling_it_one_contract() -> None:
    flags = evaluate_budget_flags(
        stages=(),
        yearly_amounts=(
            ProjectYearAmount("family-1", 2024, 500_000_000, "gaa-2024"),
            ProjectYearAmount("family-1", 2025, 200_000_000, "gaa-2025"),
            ProjectYearAmount("family-1", 2026, 0, "gaa-2026"),
        ),
    )

    assert len(flags) == 1
    assert flags[0].code is FlagCode.REPEATED_POSITIVE_FUNDING
    assert flags[0].evidence["positive_years"] == [2024, 2025]
    assert "project family" in flags[0].limitations.lower()


def test_same_year_phases_do_not_count_as_repeated_years() -> None:
    flags = evaluate_budget_flags(
        stages=(),
        yearly_amounts=(
            ProjectYearAmount("family-1", 2025, 200_000_000, "gaa-2025-phase-1"),
            ProjectYearAmount("family-1", 2025, 300_000_000, "gaa-2025-phase-2"),
        ),
    )

    assert flags == ()


def test_repeated_funding_aggregates_phases_by_year() -> None:
    flags = evaluate_budget_flags(
        stages=(),
        yearly_amounts=(
            ProjectYearAmount("family-1", 2024, 200_000_000, "gaa-2024-phase-1"),
            ProjectYearAmount("family-1", 2024, 300_000_000, "gaa-2024-phase-2"),
            ProjectYearAmount("family-1", 2025, 400_000_000, "gaa-2025"),
        ),
    )

    assert len(flags) == 1
    assert flags[0].evidence["positive_years"] == [2024, 2025]
    assert flags[0].evidence["amounts_centavos"] == [500_000_000, 400_000_000]
    assert flags[0].evidence["source_record_ids"] == [
        "gaa-2024-phase-1",
        "gaa-2024-phase-2",
        "gaa-2025",
    ]


def test_zero_placeholder_does_not_count_as_new_funding() -> None:
    flags = evaluate_budget_flags(
        stages=(),
        yearly_amounts=(
            ProjectYearAmount("family-1", 2025, 200_000_000, "gaa-2025"),
            ProjectYearAmount("family-1", 2026, 0, "gaa-2026"),
        ),
    )

    assert flags == ()
