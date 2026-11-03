import json
from datetime import UTC, datetime

import pytest

from engine.budget_watchdog.archive import (
    Acquisition,
    ArtifactArchive,
    ArtifactConflictError,
)


def test_archive_preserves_bytes_and_reproducible_manifest(tmp_path) -> None:
    archive = ArtifactArchive(tmp_path)
    acquisition = Acquisition(
        source_id="dbm-gaa",
        source_url="https://www.dbm.gov.ph/example.xlsx",
        retrieved_at=datetime(2026, 11, 2, 12, 30, tzinfo=UTC),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        payload=b"official workbook bytes",
        source_version="dbm-release-2026",
        source_last_modified=datetime(2026, 10, 31, 8, 0, tzinfo=UTC),
    )

    first = archive.store(acquisition)
    second = archive.store(acquisition)

    assert first == second
    assert first.blob_path.read_bytes() == acquisition.payload
    assert first.blob_path.name == first.sha256
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["sha256"] == first.sha256
    assert manifest["byte_size"] == len(acquisition.payload)
    assert manifest["source_id"] == "dbm-gaa"
    assert manifest["retrieved_at"] == "2026-11-02T12:30:00+00:00"
    assert manifest["source_version"] == "dbm-release-2026"
    assert manifest["source_last_modified"] == "2026-10-31T08:00:00+00:00"


def test_archive_refuses_manifest_reuse_with_different_evidence(tmp_path) -> None:
    archive = ArtifactArchive(tmp_path)
    base = Acquisition(
        source_id="dbm-gaa",
        source_url="https://www.dbm.gov.ph/example.xlsx",
        retrieved_at=datetime(2026, 11, 2, 12, 30, tzinfo=UTC),
        media_type="application/octet-stream",
        payload=b"same bytes",
    )
    archive.store(base)

    conflicting = Acquisition(
        source_id=base.source_id,
        source_url="https://www.dbm.gov.ph/changed.xlsx",
        retrieved_at=base.retrieved_at,
        media_type=base.media_type,
        payload=base.payload,
    )

    with pytest.raises(ArtifactConflictError):
        archive.store(conflicting)


def test_archive_rejects_naive_retrieval_time(tmp_path) -> None:
    archive = ArtifactArchive(tmp_path)
    acquisition = Acquisition(
        source_id="dbm-gaa",
        source_url="https://www.dbm.gov.ph/example.xlsx",
        retrieved_at=datetime(2026, 11, 2, 12, 30),
        media_type="application/octet-stream",
        payload=b"bytes",
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        archive.store(acquisition)
