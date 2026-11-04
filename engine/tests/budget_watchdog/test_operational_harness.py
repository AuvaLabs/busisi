import fcntl

from ops.harness import budget_watchdog_operational_audit as operational_audit


def test_operational_audit_serializes_with_coverage_worker(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "cycle.lock"
    observed: list[int] = []
    monkeypatch.setattr(operational_audit, "PIPELINE_LOCK", lock_path)
    monkeypatch.setattr(operational_audit.fcntl, "flock", lambda _file, mode: observed.append(mode))
    monkeypatch.setattr(operational_audit, "_run_audit", lambda: 7)

    assert operational_audit.main() == 7
    assert observed == [fcntl.LOCK_EX]
    assert lock_path.is_file()
