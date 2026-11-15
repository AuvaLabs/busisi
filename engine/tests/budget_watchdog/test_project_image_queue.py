from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.budget_watchdog import project_image_queue as queue_module
from engine.budget_watchdog.project_image_queue import (
    ImageCoverageQueue,
    ImageCoverageSeed,
    create_image_coverage_queue,
)
from engine.budget_watchdog.project_images import (
    ImageInspection,
    ProjectImageCoverage,
    ProjectImageRecord,
)

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def test_queue_connections_wait_for_transient_database_contention(tmp_path: Path) -> None:
    path = tmp_path / "queue.sqlite3"
    connection = queue_module._connect(path)
    try:
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        connection.close()

    assert busy_timeout == 30_000


def _coverage(state: str = "verified_exact") -> ProjectImageCoverage:
    return ProjectImageCoverage(
        contract_id="24HI0148",
        summary_count=1,
        endpoint_count=1,
        has_images=True,
        state=state,
        detail_sha256="a" * 64,
        list_sha256="b" * 64,
        note="Counts reconcile exactly.",
    )


def _record() -> ProjectImageRecord:
    return ProjectImageRecord(
        image_id="c" * 64,
        contract_id="24HI0148",
        component_id="component-1",
        source_url="https://s3.transparency.dpwh.gov.ph/dpwh-gallery/photo.jpg",
        thumbnail_source_url=(
            "https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/width=400/"
            "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/photo.jpg"
        ),
        purpose="Progress",
        status="published",
        captured_at="2026-01-01T00:00:00",
        fiscal_year="2024",
        photo_number=1,
        latitude=14.5,
        longitude=121.0,
        coordinate_status="within_broad_philippine_bounds",
    )


def _inspection() -> ImageInspection:
    return ImageInspection(
        sha256="d" * 64,
        byte_size=123,
        width=640,
        height=480,
        content_type="image/jpeg",
    )


def _queue(tmp_path: Path) -> ImageCoverageQueue:
    path = tmp_path / "queue.sqlite3"
    create_image_coverage_queue(
        path,
        (
            ImageCoverageSeed("24HI0148", 2024, True, 0),
            ImageCoverageSeed("25HI0028", 2025, True, 1),
        ),
        source_sha256="e" * 64,
    )
    return ImageCoverageQueue(path)


def test_queue_is_resumable_and_records_verified_evidence(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = queue.claim_batch(limit=1, now=NOW, lease_seconds=60)[0]
    assert task.contract_id == "24HI0148"

    queue.record_evidence(
        task.contract_id,
        _coverage(),
        ((_record(), _inspection(), "project-images/24HI0148/image.jpg", "/archive/image"),),
        now=NOW,
    )

    summary = queue.summary()
    assert summary.status_counts == {"pending": 1, "verified_exact": 1}
    coverage, images = queue.publication_records()
    assert coverage[0].contract_id == "24HI0148"
    assert images[0].metadata.image_id == "c" * 64


def test_queue_reclaims_expired_lease_and_applies_retry_delay(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = queue.claim_batch(limit=1, now=NOW, lease_seconds=60)[0]
    assert queue.claim_batch(limit=1, now=NOW, lease_seconds=600)[0].contract_id == "25HI0028"
    reclaimed = queue.claim_batch(limit=1, now=NOW + timedelta(seconds=61), lease_seconds=60)
    assert reclaimed[0].contract_id == task.contract_id

    queue.record_failure(
        task.contract_id,
        status="retry",
        reason_code="source_server_error",
        reason_stage="metadata",
        note="temporary source failure",
        now=NOW + timedelta(seconds=61),
        retry_after_seconds=300,
    )
    assert queue.claim_batch(limit=2, now=NOW + timedelta(seconds=120), lease_seconds=60) == ()


def test_queue_recovers_interrupted_cycle_leases(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    interrupted = queue.claim_batch(limit=1, now=NOW, lease_seconds=7_200)[0]

    recovered = queue.recover_interrupted_leases(now=NOW + timedelta(seconds=30))

    assert recovered == 1
    reclaimed = queue.claim_batch(
        limit=1,
        now=NOW + timedelta(seconds=30),
        lease_seconds=7_200,
    )
    assert reclaimed[0].contract_id == interrupted.contract_id


def test_queue_rejects_mismatched_or_unleased_results(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    queue.claim_batch(limit=1, now=NOW, lease_seconds=60)
    wrong = ProjectImageCoverage(
        contract_id="25HI0028",
        summary_count=0,
        endpoint_count=0,
        has_images=False,
        state="no_images",
        detail_sha256="a" * 64,
        list_sha256="b" * 64,
        note="No images.",
    )
    with pytest.raises(ValueError, match="contract"):
        queue.record_evidence("24HI0148", wrong, (), now=NOW)
    with pytest.raises(ValueError, match="active lease"):
        queue.record_failure(
            "25HI0028",
            status="blocked",
            reason_code="source_not_found",
            reason_stage="metadata",
            note="bad",
            now=NOW,
        )


def test_existing_queue_must_match_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "queue.sqlite3"
    seeds = (ImageCoverageSeed("24HI0148", 2024, True, 0),)
    create_image_coverage_queue(path, seeds, source_sha256="a" * 64)
    with pytest.raises(ValueError, match="different source snapshot"):
        create_image_coverage_queue(path, seeds, source_sha256="b" * 64)


def test_existing_queue_safely_refreshes_priorities_for_same_source_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.sqlite3"
    original = (
        ImageCoverageSeed("24HI0148", 2024, True, 50),
        ImageCoverageSeed("25HI0028", 2025, True, 50),
    )
    refreshed = (
        ImageCoverageSeed("24HI0148", 2024, True, 40),
        ImageCoverageSeed("25HI0028", 2025, True, 10),
    )
    create_image_coverage_queue(path, original, source_sha256="a" * 64)

    create_image_coverage_queue(path, refreshed, source_sha256="a" * 64)

    queue = ImageCoverageQueue(path)
    selected = queue.claim_batch(limit=1, now=NOW, lease_seconds=60)
    assert selected[0].contract_id == "25HI0028"


def test_queue_selection_is_deterministic_and_mixes_year_and_image_strata(
    tmp_path: Path,
) -> None:
    seeds = tuple(
        ImageCoverageSeed(f"{year % 100:02d}TEST{index:03d}", year, bool(index % 2), 50)
        for year in (2024, 2025, 2026)
        for index in range(40)
    )
    selected: list[tuple[str, int, bool]] = []
    for name in ("one.sqlite3", "two.sqlite3"):
        path = tmp_path / name
        create_image_coverage_queue(path, seeds, source_sha256="f" * 64)
        selected.append(
            tuple(
                (task.contract_id, task.fiscal_year, task.source_image_hint)
                for task in ImageCoverageQueue(path).claim_batch(
                    limit=30, now=NOW, lease_seconds=60
                )
            )
        )

    assert selected[0] == selected[1]
    assert {year for _, year, _ in selected[0]} == {2024, 2025, 2026}
    assert {hint for _, _, hint in selected[0]} == {False, True}


def test_queue_honors_every_priority_band_before_stable_stratification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "priority.sqlite3"
    create_image_coverage_queue(
        path,
        (
            ImageCoverageSeed("24TEST001", 2024, True, 60),
            ImageCoverageSeed("25TEST001", 2025, False, 20),
            ImageCoverageSeed("26TEST001", 2026, True, 40),
        ),
        source_sha256="f" * 64,
    )

    selected = ImageCoverageQueue(path).claim_batch(
        limit=3, now=NOW, lease_seconds=60
    )

    assert [task.contract_id for task in selected] == [
        "25TEST001",
        "26TEST001",
        "24TEST001",
    ]


def test_queue_claims_a_ready_retry_before_new_pending_work(tmp_path: Path) -> None:
    path = tmp_path / "priority.sqlite3"
    create_image_coverage_queue(
        path,
        (
            ImageCoverageSeed("24PENDING", 2024, True, 0),
            ImageCoverageSeed("25RETRY", 2025, True, 100),
        ),
        source_sha256="f" * 64,
    )
    queue = ImageCoverageQueue(path)
    tasks = queue.claim_batch(limit=2, now=NOW, lease_seconds=60)
    retry_task = next(task for task in tasks if task.contract_id == "25RETRY")
    queue.record_failure(
        retry_task.contract_id,
        status="retry",
        reason_code="source_server_error",
        reason_stage="metadata",
        note="temporary source failure",
        now=NOW,
        retry_after_seconds=60,
    )

    selected = queue.claim_batch(
        limit=1, now=NOW + timedelta(seconds=61), lease_seconds=60
    )

    assert selected[0].contract_id == "25RETRY"


def test_queue_rechecks_a_conflict_once_after_a_cooling_period(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    task = queue.claim_batch(limit=1, now=NOW, lease_seconds=60)[0]
    conflict = ProjectImageCoverage(
        contract_id=task.contract_id,
        summary_count=2,
        endpoint_count=1,
        has_images=True,
        state="count_conflict",
        detail_sha256="a" * 64,
        list_sha256="b" * 64,
        note="Source image summary and image endpoint do not reconcile.",
    )
    queue.record_evidence(
        task.contract_id,
        conflict,
        (
            (
                _record(),
                _inspection(),
                "project-images/24HI0148/legacy-image.jpg",
                "/archive/image",
            ),
        ),
        now=NOW,
    )

    assert queue.requeue_count_conflicts(now=NOW + timedelta(hours=23)) == 0
    assert queue.requeue_count_conflicts(now=NOW + timedelta(hours=25)) == 1
    held_coverage, held_images = queue.publication_records()
    assert held_coverage == ()
    assert held_images == ()
    retry = queue.claim_batch(
        limit=1, now=NOW + timedelta(hours=25), lease_seconds=60
    )[0]
    assert retry.contract_id == task.contract_id
    queue.record_evidence(
        task.contract_id,
        conflict,
        (
            (
                _record(),
                _inspection(),
                "project-images/24HI0148/new-image-name.jpg",
                "/archive/image",
            ),
        ),
        now=NOW + timedelta(hours=25),
    )

    assert queue.requeue_count_conflicts(now=NOW + timedelta(days=3)) == 0
    assert queue.outcome_counts()["source_count_mismatch"] == 1
    _, refreshed_images = queue.publication_records()
    assert refreshed_images[0].archive_key == "project-images/24HI0148/legacy-image.jpg"


def test_queue_rechecks_only_recoverable_blocked_failures(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    tasks = queue.claim_batch(limit=2, now=NOW, lease_seconds=60)
    by_contract = {task.contract_id: task for task in tasks}
    queue.record_failure(
        by_contract["24HI0148"].contract_id,
        status="blocked",
        reason_code="source_access_denied",
        reason_stage="metadata",
        note="official source denied access",
        now=NOW,
    )
    queue.record_failure(
        by_contract["25HI0028"].contract_id,
        status="blocked",
        reason_code="source_not_found",
        reason_stage="metadata",
        note="official source returned no record",
        now=NOW,
    )

    assert queue.requeue_recoverable_blocked(now=NOW + timedelta(days=6)) == 0
    assert queue.requeue_recoverable_blocked(now=NOW + timedelta(days=8)) == 1
    selected = queue.claim_batch(
        limit=2, now=NOW + timedelta(days=8), lease_seconds=60
    )

    assert [task.contract_id for task in selected] == ["24HI0148"]
    assert queue.outcome_counts() == {
        "source_access_denied": 1,
        "source_not_found": 1,
    }


def test_existing_queue_adds_and_backfills_outcome_taxonomy(tmp_path: Path) -> None:
    path = tmp_path / "queue.sqlite3"
    seeds = (ImageCoverageSeed("24HI0148", 2024, True, 0),)
    create_image_coverage_queue(path, seeds, source_sha256="a" * 64)
    with queue_module._connect(path) as connection:
        connection.execute("DROP TABLE image_task_outcomes")
        connection.execute(
            "UPDATE queue_metadata SET value = '2' WHERE key = 'schema_version'"
        )
        connection.execute(
            "UPDATE image_tasks SET status = 'blocked', last_note = ?",
            ("Source acquisition failed HTTP 404; task marked blocked.",),
        )

    create_image_coverage_queue(path, seeds, source_sha256="a" * 64)

    assert ImageCoverageQueue(path).outcome_counts() == {"source_not_found": 1}
