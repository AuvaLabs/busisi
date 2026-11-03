from __future__ import annotations

import json
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
    return _json(
        {
            "data": {
                "contractId": contract_id,
                "imageSummary": {"totalImages": 1, "hasImages": True},
            }
        }
    )


def _images() -> bytes:
    source = "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/photo.jpg"
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


class FakeFetcher:
    def __init__(self, *, fail: bool = False, invalid: bool = False) -> None:
        self.fail = fail
        self.invalid = invalid

    def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition:
        if self.fail:
            raise AcquisitionError("temporary", http_status=503)
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
            payload, media_type = _images(), "application/json"
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
    assert queue.summary().status_counts == {"retry": 1}
