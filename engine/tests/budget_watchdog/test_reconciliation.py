from engine.budget_watchdog.reconciliation import ReconciliationStatus, reconcile_total

EXPECTED_TOTAL_CENTAVOS = 1_000_000_000


def test_reconcile_total_records_exact_control_total() -> None:
    result = reconcile_total(
        expected_centavos=1_000_000_000,
        observed_centavos=(400_000_000, 600_000_000),
    )

    assert result.status is ReconciliationStatus.EXACT
    assert result.observed_centavos == EXPECTED_TOTAL_CENTAVOS
    assert result.difference_centavos == 0


def test_reconcile_total_never_hides_a_difference() -> None:
    result = reconcile_total(
        expected_centavos=1_000_000_000,
        observed_centavos=(400_000_000, 599_999_999),
        tolerance_centavos=0,
    )

    assert result.status is ReconciliationStatus.MISMATCH
    assert result.difference_centavos == -1
