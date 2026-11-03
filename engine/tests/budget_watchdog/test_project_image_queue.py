from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
        note="temporary source failure",
        now=NOW + timedelta(seconds=61),
        retry_after_seconds=300,
    )
    assert queue.claim_batch(limit=2, now=NOW + timedelta(seconds=120), lease_seconds=60) == ()


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
        queue.record_failure("25HI0028", status="blocked", note="bad", now=NOW)


def test_existing_queue_must_match_source_identity(tmp_path: Path) -> None:
    path = tmp_path / "queue.sqlite3"
    seeds = (ImageCoverageSeed("24HI0148", 2024, True, 0),)
    create_image_coverage_queue(path, seeds, source_sha256="a" * 64)
    with pytest.raises(ValueError, match="different source snapshot"):
        create_image_coverage_queue(path, seeds, source_sha256="b" * 64)
