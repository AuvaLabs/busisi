"""Bounded acquisition runner for queue tasks with known official source URLs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from engine.budget_watchdog.acquisition import AcquisitionError, SourceFetcher
from engine.budget_watchdog.acquisition_queue import AcquisitionQueue, QueueResult
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.sources import default_source_registry

URL_SOURCE_IDS = {
    "dpwh.gov.ph": "dpwh-documents-apex",
    "www.dpwh.gov.ph": "dpwh-documents",
}
RETRYABLE_HTTP_STATUSES = frozenset({403, 408, 425, 429})
NOT_LOCATED_HTTP_STATUSES = frozenset({404, 410})
SERVER_ERROR_MINIMUM = 500


class UrlFetcher(Protocol):
    def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition: ...


class RegisteredUrlFetcher:
    """Resolve a complete URL to a registered source without widening its origin."""

    def __init__(self, *, max_response_bytes: int = 64 * 1024 * 1024) -> None:
        self._fetcher = SourceFetcher(
            default_source_registry(), max_response_bytes=max_response_bytes
        )

    def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in URL_SOURCE_IDS
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise AcquisitionError("queue source URL is not an allowlisted official origin")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return self._fetcher.fetch(
            URL_SOURCE_IDS[parsed.hostname], path, retrieved_at=retrieved_at
        )


@dataclass(frozen=True, slots=True)
class RunnerResult:
    claimed: int
    verified_archived: int
    retry: int
    blocked: int
    not_located: int


class AcquisitionRunner:
    def __init__(
        self,
        *,
        queue: AcquisitionQueue,
        archive: ArtifactArchive,
        fetcher: UrlFetcher,
        lease_seconds: int = 300,
        max_attempts: int = 5,
        base_retry_seconds: int = 3600,
    ) -> None:
        if min(lease_seconds, max_attempts, base_retry_seconds) <= 0:
            raise ValueError("runner limits must be positive")
        self._queue = queue
        self._archive = archive
        self._fetcher = fetcher
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._base_retry_seconds = base_retry_seconds

    def run_batch(self, *, limit: int, now: datetime) -> RunnerResult:
        tasks = self._queue.claim_batch(
            limit=limit,
            now=now,
            lease_seconds=self._lease_seconds,
            require_source_url=True,
        )
        counts: Counter[str] = Counter()
        for task in tasks:
            if task.source_url is None:
                raise RuntimeError("source-constrained queue returned a task without a URL")
            result = self._acquire(task.source_url, task.attempts, now)
            self._queue.record_result(task.task_id, result, now=now)
            counts[result.status] += 1
        return RunnerResult(
            claimed=len(tasks),
            verified_archived=counts["verified_archived"],
            retry=counts["retry"],
            blocked=counts["blocked"],
            not_located=counts["not_located"],
        )

    def _acquire(self, source_url: str, attempts: int, now: datetime) -> QueueResult:
        try:
            acquisition = self._fetcher.fetch_url(source_url, now)
            artifact = self._archive.store(acquisition)
        except AcquisitionError as error:
            return self._failure(source_url, attempts, error.http_status)
        except Exception:
            return QueueResult(
                status="blocked",
                source_url=source_url,
                note="Local validation or archival failed; the task requires review.",
            )
        return QueueResult(
            status="verified_archived",
            source_url=acquisition.source_url,
            artifact_sha256=artifact.sha256,
            note="Official source bytes archived and SHA-256 verified.",
        )

    def _failure(
        self, source_url: str, attempts: int, http_status: int | None
    ) -> QueueResult:
        if http_status in NOT_LOCATED_HTTP_STATUSES:
            return QueueResult(
                status="not_located",
                source_url=source_url,
                http_status=http_status,
                note="The exact official source URL returned a terminal not-found response.",
            )
        retryable = http_status in RETRYABLE_HTTP_STATUSES or (
            http_status is not None and http_status >= SERVER_ERROR_MINIMUM
        )
        if retryable and attempts + 1 < self._max_attempts:
            delay = self._base_retry_seconds * (2 ** min(attempts, 4))
            return QueueResult(
                status="retry",
                source_url=source_url,
                http_status=http_status,
                retry_after_seconds=delay,
                note="Official source request failed; a bounded retry was scheduled.",
            )
        return QueueResult(
            status="blocked",
            source_url=source_url,
            http_status=http_status,
            note="Official source acquisition requires review after bounded attempts.",
        )
