import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.budget_watchdog.acquisition_queue import AcquisitionQueue, create_acquisition_queue
from engine.budget_watchdog.acquisition_release import (
    AcquisitionReleaseError,
    build_acquisition_release,
    load_acquisition_release,
)
from engine.budget_watchdog.acquisition_universe import build_acquisition_universe
from engine.tests.budget_watchdog.test_acquisition_universe import _awards, _delivery


def _release(tmp_path: Path):
    delivery = tmp_path / "delivery.parquet"
    awards = tmp_path / "awards.parquet"
    _delivery(delivery)
    _awards(awards)
    snapshot = build_acquisition_universe(
        delivery,
        awards,
        fiscal_years=(2024, 2025),
        delivery_sha256="d" * 64,
        award_sha256="a" * 64,
        award_revision="b" * 40,
        checked_on=date(2026, 11, 3),
    )
    queue_path = tmp_path / "queue.sqlite3"
    create_acquisition_queue(queue_path, snapshot)
    queue = AcquisitionQueue(queue_path)
    task = queue.claim_batch(
        limit=1,
        now=datetime(2026, 11, 3, 14, 0, tzinfo=UTC),
        lease_seconds=60,
    )[0]
    return build_acquisition_release(snapshot, queue.summary(), award_byte_size=1234), task


def test_release_reconciles_universe_states_years_and_queue(tmp_path) -> None:
    release, _ = _release(tmp_path)
    loaded = load_acquisition_release((json.dumps(release) + "\n").encode())

    assert loaded["summary"]["contract_count"] == 3
    assert loaded["summary"]["examined_contracts"] == 3
    assert loaded["summary"]["lifecycle_task_count"] == 27
    assert loaded["summary"]["accepted_match_rows"] == 3
    assert loaded["summary"]["quarantined_source_rows"] == 1
    assert sum(item["total_contracts"] for item in loaded["year_breakdowns"]) == 3
    assert loaded["source"]["award_byte_size"] == 1234


def test_release_rejects_mismatched_control_totals(tmp_path) -> None:
    release, _ = _release(tmp_path)
    release["summary"]["contract_count"] = 4

    with pytest.raises(AcquisitionReleaseError, match="contract control total"):
        load_acquisition_release(json.dumps(release).encode())


def test_release_rejects_unfinished_leases_from_published_queue_counts(tmp_path) -> None:
    release, _ = _release(tmp_path)

    assert release["queue_status_counts"]["in_progress"] == 1
    assert sum(release["queue_status_counts"].values()) == 27


def _set_year_control_total(raw: dict) -> None:
    item = raw["year_breakdowns"][0]
    item["total_contracts"] += 1
    item["state_counts"]["structured_exact"] += 1


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda raw: raw.update(schema_version=2), "unsupported acquisition release schema"),
    (lambda raw: raw.update(source=[]), "source and summary must be objects"),
    (lambda raw: raw["source"].update(delivery_sha256="bad"), "fingerprints"),
    (lambda raw: raw["summary"].update(contract_count=True), "non-negative integer"),
    (lambda raw: raw["summary"].update(match_state_counts=[]), "must be an object"),
    (lambda raw: raw["summary"].update(lifecycle_task_count=1), "lifecycle task"),
    (lambda raw: raw.update(queue_status_counts={"pending": 0}), "queue control"),
    (lambda raw: raw.update(year_breakdowns=[]), "non-empty array"),
    (lambda raw: raw["year_breakdowns"].__setitem__(0, {}), "entries must have a value"),
    (
        lambda raw: raw["year_breakdowns"][0]["state_counts"].pop("structured_exact"),
        "state totals",
    ),
    (
        lambda raw: raw["year_breakdowns"][0].update(total_contracts=-1),
        "non-negative integer",
    ),
    (_set_year_control_total, "control total does not reconcile"),
])
def test_release_rejects_invalid_boundaries(tmp_path, mutate, message) -> None:
    release, _ = _release(tmp_path)
    invalid = deepcopy(release)
    mutate(invalid)

    with pytest.raises(AcquisitionReleaseError, match=message):
        load_acquisition_release(json.dumps(invalid).encode())


def test_release_rejects_invalid_json_and_nonpositive_archive_size(tmp_path) -> None:
    _release(tmp_path)
    with pytest.raises(AcquisitionReleaseError, match="JSON is invalid"):
        load_acquisition_release(b"{broken")
    with pytest.raises(ValueError, match="award_byte_size"):
        build_acquisition_release(
            SimpleNamespace(), SimpleNamespace(), award_byte_size=0
        )
