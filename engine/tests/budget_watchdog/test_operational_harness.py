import fcntl
from datetime import UTC, datetime

import pytest
from ops.harness import budget_watchdog_operational_audit as operational_audit
from ops.harness import budget_watchdog_scheduled_audit as scheduled_audit


def test_operational_audit_serializes_with_coverage_worker(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "cycle.lock"
    observed: list[int] = []
    monkeypatch.setattr(operational_audit, "PIPELINE_LOCK", lock_path)
    monkeypatch.setattr(operational_audit.fcntl, "flock", lambda _file, mode: observed.append(mode))
    monkeypatch.setattr(
        operational_audit,
        "_run_audit",
        lambda *, pipeline_busy, full_integrity: (
            7 if pipeline_busy is False and full_integrity is False else 1
        ),
    )

    assert operational_audit.main() == 7
    assert observed == [fcntl.LOCK_EX | fcntl.LOCK_NB]
    assert lock_path.is_file()


def test_operational_audit_continues_when_coverage_worker_is_busy(
    tmp_path, monkeypatch
) -> None:
    lock_path = tmp_path / "cycle.lock"
    observed: list[bool] = []
    monkeypatch.setattr(operational_audit, "PIPELINE_LOCK", lock_path)

    def busy(_file, _mode) -> None:
        raise BlockingIOError("coverage cycle owns the lock")

    monkeypatch.setattr(operational_audit.fcntl, "flock", busy)
    monkeypatch.setattr(
        operational_audit,
        "_run_audit",
        lambda *, pipeline_busy, full_integrity: (
            observed.append(pipeline_busy or full_integrity) or 0
        ),
    )

    assert operational_audit.main() == 0
    assert observed == [True]


def test_busisi_services_use_bounded_runtime_limits() -> None:
    root = operational_audit.ROOT
    coverage = (root / "ops/systemd/busisi-project-image-coverage.service").read_text()
    audit = (root / "ops/systemd/busisi-operational-audit.service").read_text()

    assert "TimeoutStartSec=3h" in coverage
    assert "TimeoutStartSec=15m" in audit


def test_busy_audit_does_not_open_the_coverage_queue(monkeypatch) -> None:
    def fail_if_called(_now) -> tuple[dict[str, object], bool]:
        raise AssertionError("busy audit must not open the coverage queue")

    monkeypatch.setattr(operational_audit, "_queue_facts", fail_if_called)

    queue, queue_ok = operational_audit._queue_facts_for_run(
        datetime(2026, 11, 15, tzinfo=UTC), pipeline_busy=True
    )

    assert queue == {
        "checked": False,
        "reason": "deferred while project-image publication is in progress",
    }
    assert queue_ok is True


def test_frequent_audit_is_fast_and_weekly_audit_is_thorough() -> None:
    assert operational_audit._integrity_pragma(full_integrity=False) == "PRAGMA quick_check"
    assert operational_audit._integrity_pragma(full_integrity=True) == "PRAGMA integrity_check"
    assert scheduled_audit.COMMANDS["operations"][0][-1] == "--full-integrity"


def test_release_facts_use_latest_immutable_published_release(tmp_path, monkeypatch) -> None:
    publications = tmp_path / "publications"
    releases = tmp_path / "releases"
    publications.mkdir()
    for release_id, completed, released_at in (
        ("older", 10, "2026-11-03T00:00:00+00:00"),
        ("newer", 25, "2026-11-04T00:00:00+00:00"),
    ):
        (publications / f"{release_id}.json").write_text(
            '{"release_id":"' + release_id + '"}\n', encoding="utf-8"
        )
        release_dir = releases / release_id
        release_dir.mkdir(parents=True)
        (release_dir / "manifest.json").write_text(
            "{\n"
            '  "coverage_release": {\n'
            f'    "release_id": "{release_id}",\n'
            f'    "completed_contracts": {completed},\n'
            f'    "released_at": "{released_at}"\n'
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(operational_audit, "PUBLICATIONS", publications)
    monkeypatch.setattr(operational_audit, "RELEASES", releases)

    facts = operational_audit._release_facts()

    assert facts["release_id"] == "newer"
    assert facts["completed_contracts"] == 25
    assert facts["publication_marker_exists"] is True
    assert facts["release_manifest"].endswith("newer/manifest.json")


def test_release_facts_reject_marker_without_archived_manifest(tmp_path, monkeypatch) -> None:
    publications = tmp_path / "publications"
    publications.mkdir()
    (publications / "missing.json").write_text(
        '{"release_id":"missing"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(operational_audit, "PUBLICATIONS", publications)
    monkeypatch.setattr(operational_audit, "RELEASES", tmp_path / "releases")

    with pytest.raises(
        ValueError, match="published release missing archived manifest: missing"
    ):
        operational_audit._release_facts()
