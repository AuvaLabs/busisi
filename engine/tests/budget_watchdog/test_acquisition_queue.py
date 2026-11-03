import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.budget_watchdog.acquisition_queue import (
    AcquisitionQueue,
    QueueResult,
    apply_reviewed_evidence,
    create_acquisition_queue,
)
from engine.budget_watchdog.acquisition_universe import build_acquisition_universe
from engine.tests.budget_watchdog.test_acquisition_universe import _awards, _delivery


def _snapshot(tmp_path: Path):
    delivery = tmp_path / "delivery.parquet"
    awards = tmp_path / "awards.parquet"
    _delivery(delivery)
    _awards(awards)
    return build_acquisition_universe(
        delivery,
        awards,
        fiscal_years=(2024, 2025),
        delivery_sha256="d" * 64,
        award_sha256="a" * 64,
        award_revision="b" * 40,
        checked_on=datetime(2026, 11, 3, tzinfo=UTC).date(),
    )


def test_queue_registers_every_stage_and_resumes_leased_batches(tmp_path) -> None:
    database = tmp_path / "queue.sqlite3"
    create_acquisition_queue(database, _snapshot(tmp_path))
    queue = AcquisitionQueue(database)
    now = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)

    assert queue.summary().total_tasks == 27
    assert queue.summary().status_counts["quarantined"] == 2
    first = queue.claim_batch(limit=4, now=now, lease_seconds=60)
    assert len(first) == 4
    assert len({item.task_id for item in first}) == 4
    assert queue.claim_batch(limit=4, now=now, lease_seconds=60)[0].task_id not in {
        item.task_id for item in first
    }

    resumed = queue.claim_batch(limit=4, now=now + timedelta(seconds=61), lease_seconds=60)
    assert resumed[0].task_id == first[0].task_id


def test_queue_records_verified_retry_and_quarantine_results(tmp_path) -> None:
    database = tmp_path / "queue.sqlite3"
    create_acquisition_queue(database, _snapshot(tmp_path))
    queue = AcquisitionQueue(database)
    now = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)
    task = queue.claim_batch(limit=1, now=now, lease_seconds=60)[0]

    with pytest.raises(ValueError, match="verified result"):
        queue.record_result(task.task_id, QueueResult(status="verified_archived"), now=now)

    queue.record_result(
        task.task_id,
        QueueResult(
            status="verified_archived",
            source_url="https://example.gov.ph/document.pdf",
            artifact_sha256="f" * 64,
        ),
        now=now,
    )
    retry = queue.claim_batch(limit=1, now=now, lease_seconds=60)[0]
    queue.record_result(
        retry.task_id,
        QueueResult(status="retry", http_status=403, retry_after_seconds=300),
        now=now,
    )

    summary = queue.summary()
    assert summary.status_counts["verified_archived"] == 1
    assert summary.status_counts["retry"] == 1
    assert queue.claim_batch(limit=27, now=now, lease_seconds=60)
    assert retry.task_id not in {
        item.task_id
        for item in queue.claim_batch(
            limit=27,
            now=now + timedelta(seconds=299),
            lease_seconds=60,
        )
    }


def test_reviewed_blocked_source_becomes_a_retryable_acquisition_task(tmp_path) -> None:
    database = tmp_path / "queue.sqlite3"
    create_acquisition_queue(database, _snapshot(tmp_path))
    catalog = SimpleNamespace(items=(SimpleNamespace(
        contract_id="25BB0002",
        stage="procurement_monitoring_report",
        status="blocked",
        retry_eligible=True,
        source_url="https://www.dpwh.gov.ph/report.pdf",
        artifact_sha256=None,
        http_status=403,
        limitation="Official source blocked the archive runner.",
        last_checked_at="2026-11-03",
    ),))

    apply_reviewed_evidence(database, catalog)
    queue = AcquisitionQueue(database)
    batch = queue.claim_batch(
        limit=5,
        now=datetime(2026, 11, 4, tzinfo=UTC),
        lease_seconds=60,
        require_source_url=True,
    )

    assert [item.task_id for item in batch] == [
        "25BB0002:procurement_monitoring_report"
    ]
    assert batch[0].source_url == "https://www.dpwh.gov.ph/report.pdf"


def test_queue_rejects_invalid_boundaries_and_foreign_results(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        AcquisitionQueue(tmp_path / "missing.sqlite3")
    database = tmp_path / "queue.sqlite3"
    create_acquisition_queue(database, _snapshot(tmp_path))
    queue = AcquisitionQueue(database)
    now = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="positive"):
        queue.claim_batch(limit=0, now=now, lease_seconds=60)
    with pytest.raises(ValueError, match="timezone-aware"):
        queue.claim_batch(limit=1, now=datetime(2026, 11, 3), lease_seconds=60)
    with pytest.raises(ValueError, match="active lease"):
        queue.record_result("unknown", QueueResult(status="blocked"), now=now)
    task = queue.claim_batch(limit=1, now=now, lease_seconds=60)[0]
    with pytest.raises(ValueError, match="unsupported"):
        queue.record_result(task.task_id, QueueResult(status="invalid"), now=now)
    with pytest.raises(ValueError, match="retry result"):
        queue.record_result(task.task_id, QueueResult(status="retry"), now=now)


def test_existing_queue_must_match_source_snapshot(tmp_path) -> None:
    database = tmp_path / "queue.sqlite3"
    snapshot = _snapshot(tmp_path)
    create_acquisition_queue(database, snapshot)
    create_acquisition_queue(database, snapshot)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE queue_metadata SET value = 'wrong' WHERE key = 'award_sha256'"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="different source snapshot"):
        create_acquisition_queue(database, snapshot)
