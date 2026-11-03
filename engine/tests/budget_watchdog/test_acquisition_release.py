import json
from datetime import UTC, date, datetime
from pathlib import Path

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
