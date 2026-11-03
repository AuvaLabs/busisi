from decimal import Decimal

from engine.budget_watchdog.delivery_flags import (
    DeliveryFlagCode,
    DeliverySnapshot,
    evaluate_delivery_flags,
)


def test_flags_zero_downstream_budget_against_positive_appropriation() -> None:
    snapshot = DeliverySnapshot(
        contract_id="26HI0094",
        appropriation_centavos=2_500_000_000,
        project_budget_centavos=0,
        abc_centavos=None,
        award_centavos=None,
        status="For Procurement",
        progress_percent=Decimal("0"),
    )

    flags = evaluate_delivery_flags(snapshot)

    assert [flag.code for flag in flags] == [DeliveryFlagCode.ZERO_DOWNSTREAM_BUDGET]
    assert "not proof" in flags[0].limitations.lower()


def test_flags_progress_status_conflict_and_award_above_abc() -> None:
    snapshot = DeliverySnapshot(
        contract_id="sample-contract",
        appropriation_centavos=1_000_000_000,
        project_budget_centavos=990_000_000,
        abc_centavos=990_000_000,
        award_centavos=1_000_000_000,
        status="On-Going",
        progress_percent=Decimal("100"),
    )

    flags = evaluate_delivery_flags(snapshot)

    assert [flag.code for flag in flags] == [
        DeliveryFlagCode.STATUS_PROGRESS_CONFLICT,
        DeliveryFlagCode.AWARD_ABOVE_ABC,
    ]


def test_completed_project_with_compatible_award_has_no_delivery_flag() -> None:
    snapshot = DeliverySnapshot(
        contract_id="23DB0126",
        appropriation_centavos=1_000_000_000,
        project_budget_centavos=990_000_000,
        abc_centavos=990_000_000,
        award_centavos=960_300_000,
        status="Completed",
        progress_percent=Decimal("100"),
    )

    assert evaluate_delivery_flags(snapshot) == ()
