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
