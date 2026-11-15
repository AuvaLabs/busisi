"""Bounded acquisition runner for project-image coverage tasks."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from threading import local
from typing import Protocol, cast

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.project_image_queue import ImageCoverageQueue, ImageCoverageTask
from engine.budget_watchdog.project_images import (
    ImageInspection,
    ProjectImageCoverage,
    ProjectImageRecord,
    inspect_jpeg,
    parse_project_image_evidence,
    project_image_acquisition_target,
)


class ProjectImageFetcher(Protocol):
    def fetch(self, source_id: str, path: str, *, retrieved_at: datetime) -> Acquisition: ...


type AcquiredEvidence = tuple[
    ProjectImageCoverage,
    tuple[tuple[ProjectImageRecord, ImageInspection, str, str], ...],
]
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR_MINIMUM = 500
HTTP_PERMANENT_SOURCE_FAILURES = frozenset({401, 403, 404, 410})
HTTP_ACCESS_DENIED = frozenset({401, 403})
HTTP_NOT_FOUND = frozenset({404, 410})


class StagedAcquisitionError(AcquisitionError):
    """Preserve which project-image source boundary failed."""

    def __init__(self, stage: str, error: AcquisitionError) -> None:
        super().__init__(
            str(error),
            http_status=error.http_status,
            retry_after_seconds=error.retry_after_seconds,
            response_body=error.response_body,
        )
        self.stage = stage


@dataclass(frozen=True, slots=True)
class FailureClassification:
    code: str
    kind: str
    controller_failure: bool


@dataclass(frozen=True, slots=True)
class ProjectImageBatchResult:
    claimed: int
    verified_exact: int
    no_images: int
    count_conflict: int
    retry: int
    blocked: int
    images_archived: int
    rate_limited: int
    source_failure: int
    server_failure: int
    validation_failure: int
    controller_failures: int


def merge_batch_results(
    results: tuple[ProjectImageBatchResult, ...],
) -> ProjectImageBatchResult:
    return ProjectImageBatchResult(
        **{
            field: sum(getattr(result, field) for result in results)
            for field in ProjectImageBatchResult.__dataclass_fields__
        }
    )


class ProjectImageRunner:
    def __init__(
        self,
        *,
        queue: ImageCoverageQueue,
        archive: ArtifactArchive,
        metadata_fetcher: ProjectImageFetcher,
        image_fetcher: ProjectImageFetcher,
        fetcher_factory: Callable[[], tuple[ProjectImageFetcher, ProjectImageFetcher]]
        | None = None,
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
        self._fetcher_factory = fetcher_factory
        self._max_attempts = max_attempts
        self._retry_after_seconds = retry_after_seconds
        self._lease_seconds = lease_seconds

    def run_batch(self, *, limit: int, now: datetime, workers: int = 1) -> ProjectImageBatchResult:
        if workers <= 0:
            raise ValueError("project-image worker count must be positive")
        if workers > 1 and self._fetcher_factory is None:
            raise ValueError("parallel acquisition requires a fetcher factory")
        tasks = self._queue.claim_batch(limit=limit, now=now, lease_seconds=self._lease_seconds)
        counts = {
            "verified_exact": 0,
            "no_images": 0,
            "count_conflict": 0,
            "retry": 0,
            "blocked": 0,
            "images_archived": 0,
            "rate_limited": 0,
            "source_failure": 0,
            "server_failure": 0,
            "validation_failure": 0,
            "controller_failures": 0,
        }
        thread_state = local()

        def acquire(
            task: ImageCoverageTask,
        ) -> tuple[ImageCoverageTask, AcquiredEvidence | None, Exception | None]:
            try:
                metadata_fetcher, image_fetcher = self._fetchers(thread_state, workers)
                evidence = self._collect(task.contract_id, now, metadata_fetcher, image_fetcher)
                return task, evidence, None
            except Exception as exc:  # Boundary returns failures for serialized recording.
                return task, None, exc

        if workers == 1:
            outcomes = tuple(acquire(task) for task in tasks)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                outcomes = tuple(executor.map(acquire, tasks))

        for task, evidence, error in outcomes:
            if error is None:
                assert evidence is not None
                coverage, acquired = evidence
                self._queue.record_evidence(task.contract_id, coverage, acquired, now=now)
                counts[coverage.state] += 1
                counts["images_archived"] += len(acquired)
            else:
                exc = error
                state = self._failure_state(exc, task.attempts + 1)
                classification = self._classify_failure(exc)
                self._queue.record_failure(
                    task.contract_id,
                    status=state,
                    reason_code=classification.code,
                    reason_stage=self._failure_stage(exc),
                    note=self._failure_note(exc, state),
                    now=now,
                    retry_after_seconds=(
                        max(
                            self._retry_after_seconds,
                            exc.retry_after_seconds or 0,
                        )
                        if state == "retry" and isinstance(exc, AcquisitionError)
                        else self._retry_after_seconds
                        if state == "retry"
                        else None
                    ),
                )
                counts[state] += 1
                counts[classification.kind] += 1
                counts["controller_failures"] += int(classification.controller_failure)
        return ProjectImageBatchResult(claimed=len(tasks), **counts)

    def _fetchers(
        self, thread_state: local, workers: int
    ) -> tuple[ProjectImageFetcher, ProjectImageFetcher]:
        if workers == 1:
            return self._metadata_fetcher, self._image_fetcher
        fetchers = getattr(thread_state, "fetchers", None)
        if fetchers is None:
            if self._fetcher_factory is None:  # pragma: no cover - guarded by run_batch.
                raise ValueError("parallel acquisition requires a fetcher factory")
            fetchers = self._fetcher_factory()
            thread_state.fetchers = fetchers
        return cast(tuple[ProjectImageFetcher, ProjectImageFetcher], fetchers)

    def _collect(
        self,
        contract_id: str,
        now: datetime,
        metadata_fetcher: ProjectImageFetcher,
        image_fetcher: ProjectImageFetcher,
    ) -> AcquiredEvidence:
        detail = self._fetch(
            metadata_fetcher,
            "bettergov-dpwh",
            f"/projects/{contract_id}",
            now,
            stage="metadata",
        )
        image_list = self._fetch(
            metadata_fetcher,
            "bettergov-dpwh",
            f"/projects/{contract_id}/images",
            now,
            stage="metadata",
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
            source_id, path = project_image_acquisition_target(record.source_url)
            image = self._fetch(
                image_fetcher, source_id, path, now, stage="media"
            )
            inspection = inspect_jpeg(image.payload, image.media_type)
            artifact = self._archive.store(image)
            if inspection.sha256 != artifact.sha256:
                raise ValueError("archived project image identity mismatch")
            acquired.append(
                (
                    record,
                    inspection,
                    (f"project-images/{contract_id}/{record.image_id}-{inspection.sha256}.jpg"),
                    str(artifact.blob_path),
                )
            )
        unique_payloads = len({inspection.sha256 for _, inspection, _, _ in acquired})
        if unique_payloads < len(acquired):
            coverage = replace(
                coverage,
                state="count_conflict",
                note=(
                    f"The image endpoint returned {len(acquired)} distinct records but only "
                    f"{unique_payloads} unique JPEG payloads; duplicate JPEG content is "
                    "quarantined."
                ),
            )
        return coverage, tuple(acquired)

    @staticmethod
    def _fetch(
        fetcher: ProjectImageFetcher,
        source_id: str,
        path: str,
        now: datetime,
        *,
        stage: str,
    ) -> Acquisition:
        try:
            return fetcher.fetch(source_id, path, retrieved_at=now)
        except AcquisitionError as exc:
            raise StagedAcquisitionError(stage, exc) from exc

    def _failure_state(self, error: Exception, attempts: int) -> str:
        if attempts >= self._max_attempts:
            return "blocked"
        if (
            isinstance(error, AcquisitionError)
            and error.http_status in HTTP_PERMANENT_SOURCE_FAILURES
        ):
            return "blocked"
        return "retry"

    @staticmethod
    def _classify_failure(error: Exception) -> FailureClassification:
        if not isinstance(error, AcquisitionError):
            return FailureClassification(
                "evidence_validation", "validation_failure", True
            )
        status = error.http_status
        if status == HTTP_TOO_MANY_REQUESTS:
            classification = ("source_rate_limited", "rate_limited", True)
        elif status in HTTP_ACCESS_DENIED:
            classification = (
                "source_access_denied",
                "source_failure",
                getattr(error, "stage", "unknown") != "media",
            )
        elif status in HTTP_NOT_FOUND:
            classification = ("source_not_found", "source_failure", False)
        elif status is not None and status >= HTTP_SERVER_ERROR_MINIMUM:
            classification = ("source_server_error", "server_failure", True)
        elif status is None:
            classification = ("source_network_error", "source_failure", True)
        else:
            classification = ("source_client_error", "source_failure", True)
        return FailureClassification(*classification)

    @staticmethod
    def _failure_stage(error: Exception) -> str:
        if isinstance(error, StagedAcquisitionError):
            return error.stage
        return "evidence" if not isinstance(error, AcquisitionError) else "unknown"

    @staticmethod
    def _failure_note(error: Exception, state: str) -> str:
        if isinstance(error, AcquisitionError):
            status = f" HTTP {error.http_status}" if error.http_status else ""
            stage = getattr(error, "stage", "source")
            return f"Project {stage} download failed{status}; task marked {state}."
        return f"Evidence validation failed; task marked {state}."
