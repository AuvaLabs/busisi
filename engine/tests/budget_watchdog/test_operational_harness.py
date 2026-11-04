import fcntl

import pytest
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
