from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.acquisition_queue import (
    AcquisitionQueue,
    apply_reviewed_evidence,
    create_acquisition_queue,
)
from engine.budget_watchdog.acquisition_runner import AcquisitionRunner, RegisteredUrlFetcher
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.tests.budget_watchdog.test_acquisition_queue import _snapshot


class FakeFetcher:
    def __init__(self, payload: bytes | None = b"official document") -> None:
        self.payload = payload

    def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
        if self.payload is None:
            raise AcquisitionError("bounded source request failed", http_status=403)
        return Acquisition(
            source_id="dpwh-documents",
            source_url=url,
            retrieved_at=retrieved_at,
            media_type="application/pdf",
            payload=self.payload,
        )


class FailureFetcher:
    def __init__(self, status: int | None, *, generic: bool = False) -> None:
        self.status = status
        self.generic = generic

    def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
        if self.generic:
            raise RuntimeError("local archive failure")
        raise AcquisitionError("bounded source request failed", http_status=self.status)


def _queue(tmp_path: Path) -> AcquisitionQueue:
    database = tmp_path / "queue.sqlite3"
    create_acquisition_queue(database, _snapshot(tmp_path))
    apply_reviewed_evidence(database, SimpleNamespace(items=(SimpleNamespace(
        contract_id="25BB0002",
        stage="procurement_monitoring_report",
        status="blocked",
        retry_eligible=True,
        source_url="https://www.dpwh.gov.ph/report.pdf",
        artifact_sha256=None,
        http_status=403,
        limitation="Official source blocked the archive runner.",
        last_checked_at="2026-11-03",
    ),)))
    return AcquisitionQueue(database)


def test_runner_archives_verified_source_and_updates_queue(tmp_path) -> None:
    queue = _queue(tmp_path)
    runner = AcquisitionRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        fetcher=FakeFetcher(),
    )

    result = runner.run_batch(limit=5, now=datetime(2026, 11, 4, tzinfo=UTC))

    assert result.claimed == 1
    assert result.verified_archived == 1
    assert queue.summary().status_counts["verified_archived"] == 1
    assert len(list((tmp_path / "archive" / "blobs").iterdir())) == 1


def test_runner_backs_off_bounded_http_failure(tmp_path) -> None:
    queue = _queue(tmp_path)
    runner = AcquisitionRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        fetcher=FakeFetcher(None),
    )

    result = runner.run_batch(limit=5, now=datetime(2026, 11, 4, tzinfo=UTC))

    assert result.claimed == 1
    assert result.retry == 1
    assert queue.summary().status_counts["retry"] == 1


@pytest.mark.parametrize(("fetcher", "expected"), [
    (FailureFetcher(404), "not_located"),
    (FailureFetcher(500), "retry"),
    (FailureFetcher(None), "blocked"),
    (FailureFetcher(None, generic=True), "blocked"),
])
def test_runner_classifies_bounded_failures(tmp_path, fetcher, expected) -> None:
    queue = _queue(tmp_path)
    runner = AcquisitionRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        fetcher=fetcher,
    )

    result = runner.run_batch(limit=1, now=datetime(2026, 11, 4, tzinfo=UTC))

    assert getattr(result, expected) == 1


def test_runner_blocks_after_attempt_limit_and_validates_configuration(tmp_path) -> None:
    queue = _queue(tmp_path)
    with pytest.raises(ValueError, match="runner limits"):
        AcquisitionRunner(
            queue=queue,
            archive=ArtifactArchive(tmp_path / "archive"),
            fetcher=FailureFetcher(403),
            max_attempts=0,
        )
    runner = AcquisitionRunner(
        queue=queue,
        archive=ArtifactArchive(tmp_path / "archive"),
        fetcher=FailureFetcher(403),
        max_attempts=1,
    )

    result = runner.run_batch(limit=1, now=datetime(2026, 11, 4, tzinfo=UTC))

    assert result.blocked == 1


class CapturingFetcher:
    def __init__(self) -> None:
        self.arguments = None

    def fetch(self, source_id, path, *, retrieved_at):
        self.arguments = (source_id, path, retrieved_at)
        return "acquired"


def test_registered_url_fetcher_preserves_allowlisted_path_and_query() -> None:
    fetcher = object.__new__(RegisteredUrlFetcher)
    fetcher._fetcher = CapturingFetcher()
    now = datetime(2026, 11, 4, tzinfo=UTC)

    result = fetcher.fetch_url("https://www.dpwh.gov.ph/report.pdf?version=1", now)

    assert result == "acquired"
    assert fetcher._fetcher.arguments == (
        "dpwh-documents", "/report.pdf?version=1", now,
    )


@pytest.mark.parametrize("url", [
    "http://www.dpwh.gov.ph/report.pdf",
    "https://example.com/report.pdf",
    "https://user@www.dpwh.gov.ph/report.pdf",
    "https://www.dpwh.gov.ph/report.pdf#section",
])
def test_registered_url_fetcher_rejects_unapproved_urls(url) -> None:
    fetcher = object.__new__(RegisteredUrlFetcher)
    fetcher._fetcher = CapturingFetcher()

    with pytest.raises(AcquisitionError, match="allowlisted"):
        fetcher.fetch_url(url, datetime(2026, 11, 4, tzinfo=UTC))
