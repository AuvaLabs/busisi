"""Bounded acquisition runner for project-image coverage tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.project_image_queue import ImageCoverageQueue
from engine.budget_watchdog.project_images import inspect_jpeg, parse_project_image_evidence


class ProjectImageFetcher(Protocol):
    def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition: ...


@dataclass(frozen=True, slots=True)
class ProjectImageBatchResult:
    claimed: int
    verified_exact: int
    no_images: int
    count_conflict: int
    retry: int
    blocked: int
    images_archived: int


class ProjectImageRunner:
    def __init__(
        self,
        *,
        queue: ImageCoverageQueue,
        archive: ArtifactArchive,
        metadata_fetcher: ProjectImageFetcher,
        image_fetcher: ProjectImageFetcher,
        max_attempts: int = 5,
        retry_after_seconds: int = 21_600,
        lease_seconds: int = 7_200,
    ) -> None:
        if min(max_attempts, retry_after_seconds, lease_seconds) <= 0:
            raise ValueError("project-image runner limits must be positive")
        self._queue = queue
        self._archive = archive
        self._metadata_fetcher = metadata_fetcher
        self._image_fetcher = image_fetcher
        self._max_attempts = max_attempts
        self._retry_after_seconds = retry_after_seconds
        self._lease_seconds = lease_seconds

    def run_batch(self, *, limit: int, now: datetime) -> ProjectImageBatchResult:
        tasks = self._queue.claim_batch(limit=limit, now=now, lease_seconds=self._lease_seconds)
        counts = {
            "verified_exact": 0,
            "no_images": 0,
            "count_conflict": 0,
            "retry": 0,
            "blocked": 0,
            "images_archived": 0,
        }
        for task in tasks:
            try:
                image_count, state = self._acquire(task.contract_id, now)
                counts[state] += 1
                counts["images_archived"] += image_count
            except Exception as exc:  # Boundary converts all failures into queue state.
                state = self._failure_state(exc, task.attempts + 1)
                self._queue.record_failure(
                    task.contract_id,
                    status=state,
                    note=self._failure_note(exc, state),
                    now=now,
                    retry_after_seconds=(self._retry_after_seconds if state == "retry" else None),
                )
                counts[state] += 1
        return ProjectImageBatchResult(claimed=len(tasks), **counts)

    def _acquire(self, contract_id: str, now: datetime) -> tuple[int, str]:
        detail = self._metadata_fetcher.fetch(
            "bettergov-dpwh", f"/projects/{contract_id}", retrieved_at=now
        )
        image_list = self._metadata_fetcher.fetch(
            "bettergov-dpwh", f"/projects/{contract_id}/images", retrieved_at=now
        )
        detail_artifact = self._archive.store(detail)
        list_artifact = self._archive.store(image_list)
        coverage, records = parse_project_image_evidence(
            contract_id, detail.payload, image_list.payload
        )
        if (
            coverage.detail_sha256 != detail_artifact.sha256
            or coverage.list_sha256 != list_artifact.sha256
        ):
            raise ValueError("archived project-image metadata identity mismatch")

        acquired = []
        for record in records:
            path = urlparse(record.source_url).path
            image = self._image_fetcher.fetch("dpwh-transparency-media", path, retrieved_at=now)
            inspection = inspect_jpeg(image.payload, image.media_type)
            artifact = self._archive.store(image)
            if inspection.sha256 != artifact.sha256:
                raise ValueError("archived project image identity mismatch")
            acquired.append(
                (
                    record,
                    inspection,
                    f"project-images/{contract_id}/{inspection.sha256}.jpg",
                    str(artifact.blob_path),
                )
            )
        self._queue.record_evidence(contract_id, coverage, tuple(acquired), now=now)
        return len(acquired), coverage.state

    def _failure_state(self, error: Exception, attempts: int) -> str:
        if attempts >= self._max_attempts:
            return "blocked"
        if isinstance(error, AcquisitionError) and error.http_status in {404, 410}:
            return "blocked"
        return "retry"

    @staticmethod
    def _failure_note(error: Exception, state: str) -> str:
        if isinstance(error, AcquisitionError):
            status = f" HTTP {error.http_status}" if error.http_status else ""
            return f"Source acquisition failed{status}; task marked {state}."
        return f"Evidence validation failed; task marked {state}."
