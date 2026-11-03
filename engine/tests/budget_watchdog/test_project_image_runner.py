from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.project_image_queue import (
    ImageCoverageQueue,
    ImageCoverageSeed,
    create_image_coverage_queue,
)
from engine.budget_watchdog.project_image_runner import ProjectImageRunner

NOW = datetime(2026, 11, 4, tzinfo=UTC)
JPEG = (
    b"\xff\xd8\xff\xc0\x00\x11\x08\x01\x2c\x02\x58\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9"
)


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _detail(contract_id: str) -> bytes:
    return _detail_with_count(contract_id, 1)


def _detail_with_count(contract_id: str, count: int) -> bytes:
    return _json(
        {
            "data": {
                "contractId": contract_id,
                "imageSummary": {"totalImages": count, "hasImages": count > 0},
            }
        }
    )


def _images(contract_id: str = "24HI0148") -> bytes:
    source = f"https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/{contract_id}/photo.jpg"
    return _json(
        {
            "data": {
                "images": [
                    {
                        "componentId": "component-1",
                        "url": source,
                        "thumbnailUrl": (
                            "https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/width=400/" + source
                        ),
                        "purpose": "progress",
                        "status": "published",
                        "capturedAt": "2026-01-01T00:00:00",
                        "fiscalYear": "FY2024",
                        "photoNumber": 1,
                        "coordinates": {"latitude": 14.5, "longitude": 121.0},
                    }
                ]
            }
        }
    )


def _duplicate_content_images(contract_id: str) -> bytes:
    records = []
    for number in (1, 2):
        source = (
            "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/"
            f"fy2024/{contract_id}/photo-{number}.jpg"
        )
        records.append(
            {
                "componentId": f"component-{number}",
                "url": source,
                "thumbnailUrl": (
                    "https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/width=400/" + source
                ),
                "purpose": "progress",
                "status": "published",
                "capturedAt": "2026-01-01T00:00:00",
                "fiscalYear": "FY2024",
                "photoNumber": number,
                "coordinates": {"latitude": 14.5, "longitude": 121.0},
            }
        )
    return _json({"data": {"images": records}})


class FakeFetcher:
    def __init__(self, *, fail: bool = False, invalid: bool = False, status: int = 503) -> None:
        self.fail = fail
        self.invalid = invalid
        self.status = status

    def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition:
        if self.fail:
            raise AcquisitionError("temporary", http_status=self.status)
        if self.invalid:
            payload, media_type = b"not-json", "application/json"
            return Acquisition(
                source_id=source_id,
                source_url="https://api.dpwh.bettergov.ph" + path,
                retrieved_at=retrieved_at,
                media_type=media_type,
                payload=payload,
            )
        if path.endswith("/images"):
            payload, media_type = _images(path.split("/")[-2]), "application/json"
        elif source_id == "bettergov-dpwh":
            payload, media_type = _detail(path.rsplit("/", 1)[-1]), "application/json"
        else:
            payload, media_type = JPEG, "image/jpeg"
        return Acquisition(
            source_id=source_id,
            source_url=(
                "https://api.dpwh.bettergov.ph" + path
                if source_id == "bettergov-dpwh"
                else "https://s3.transparency.dpwh.gov.ph" + path
            ),
            retrieved_at=retrieved_at,
            media_type=media_type,
            payload=payload,
        )


def _queue(tmp_path: Path) -> ImageCoverageQueue:
    path = tmp_path / "queue.sqlite3"
    create_image_coverage_queue(
        path,
        (ImageCoverageSeed("24HI0148", 2024, True),),
        source_sha256="a" * 64,
    )
    return ImageCoverageQueue(path)


def _multi_queue(tmp_path: Path, count: int = 8) -> ImageCoverageQueue:
    path = tmp_path / "queue.sqlite3"
    create_image_coverage_queue(
        path,
        tuple(ImageCoverageSeed(f"24TEST{index:02d}", 2024, True) for index in range(count)),
        source_sha256="a" * 64,
    )
    return ImageCoverageQueue(path)


def test_runner_archives_and_records_exact_image_evidence(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.claimed == 1
    assert result.verified_exact == 1
    assert result.images_archived == 1
    assert queue.summary().status_counts == {"verified_exact": 1}


def test_runner_retries_transient_source_failure(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(fail=True),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.retry == 1
    assert result.server_failure == 1
    assert queue.summary().status_counts == {"retry": 1}


def test_runner_retries_validation_failure_before_blocking(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(invalid=True),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.retry == 1
    assert result.validation_failure == 1
    assert queue.summary().status_counts == {"retry": 1}


def test_runner_classifies_rate_limits_for_the_cycle_controller(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(fail=True, status=429),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.retry == 1
    assert result.rate_limited == 1


def test_runner_separates_non_server_source_failures(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(fail=True, status=404),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.blocked == 1
    assert result.source_failure == 1
    assert result.server_failure == 0


def test_runner_blocks_forbidden_official_media_without_retrying(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(fail=True, status=403),
        image_fetcher=FakeFetcher(),
    ).run_batch(limit=1, now=NOW)

    assert result.blocked == 1
    assert result.retry == 0
    assert result.source_failure == 1


def test_runner_quarantines_distinct_records_with_duplicate_image_bytes(tmp_path: Path) -> None:
    queue = _queue(tmp_path)

    class DuplicateContentFetcher(FakeFetcher):
        def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition:
            if path.endswith("/images"):
                payload = _duplicate_content_images(path.split("/")[-2])
            elif source_id == "bettergov-dpwh":
                payload = _detail_with_count(path.rsplit("/", 1)[-1], 2)
            else:
                payload = JPEG
            return Acquisition(
                source_id=source_id,
                source_url=(
                    "https://api.dpwh.bettergov.ph" + path
                    if source_id == "bettergov-dpwh"
                    else "https://s3.transparency.dpwh.gov.ph" + path
                ),
                retrieved_at=retrieved_at,
                media_type="application/json" if source_id == "bettergov-dpwh" else "image/jpeg",
                payload=payload,
            )

    fetcher = DuplicateContentFetcher()
    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=fetcher,
        image_fetcher=fetcher,
    ).run_batch(limit=1, now=NOW)

    assert result.count_conflict == 1
    assert result.verified_exact == 0
    assert queue.summary().status_counts == {"count_conflict": 1}
    coverage, images = queue.publication_records()
    assert "duplicate JPEG content" in coverage[0].note
    assert len({item.archive_key for item in images}) == 2
    assert len({item.inspection.sha256 for item in images}) == 1


def test_runner_acquires_in_parallel_with_worker_local_fetchers(tmp_path: Path) -> None:
    queue = _multi_queue(tmp_path)
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    factory_calls = 0

    class ConcurrentFetcher(FakeFetcher):
        def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.005)
                return super().fetch(source_id, path, retrieved_at=retrieved_at)
            finally:
                with lock:
                    active -= 1

    def factory() -> tuple[FakeFetcher, FakeFetcher]:
        nonlocal factory_calls
        with lock:
            factory_calls += 1
        return ConcurrentFetcher(), ConcurrentFetcher()

    result = ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        metadata_fetcher=FakeFetcher(),
        image_fetcher=FakeFetcher(),
        fetcher_factory=factory,
    ).run_batch(limit=8, now=NOW, workers=4)

    assert result.verified_exact == 8
    assert maximum_active > 1
    assert 2 <= factory_calls <= 4
