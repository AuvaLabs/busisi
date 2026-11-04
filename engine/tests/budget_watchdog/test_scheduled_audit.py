from engine.budget_watchdog.scheduled_audit import audit_command_results


def test_scheduled_audit_accepts_only_complete_success() -> None:
    assert audit_command_results({"operations": 0, "python": 0, "worker": 0}) == ()


def test_scheduled_audit_names_every_failed_or_missing_check() -> None:
    assert audit_command_results({"operations": 1, "python": 0, "worker": None}) == (
        "operations check failed with exit code 1",
        "worker check did not complete",
    )
