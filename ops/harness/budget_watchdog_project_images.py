"""Acquire, archive, reconcile, inspect and bundle reviewed DPWH project images."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.project_image_bundle import (
    AcquiredProjectImage,
    build_project_image_bundle,
)
from engine.budget_watchdog.project_images import inspect_jpeg, parse_project_image_evidence
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
ARCHIVE_DIR = DATA_ROOT / "archive"
OUTPUT_DIR = DATA_ROOT / "project-image-d1-bundle"
CONTRACT_IDS = (
    "22HI0028",
    "23DB0126",
    "24HI0131",
    "24HI0148",
    "25HI0028",
    "26HI0094",
)
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def main() -> int:
    retrieved_at = datetime.now(UTC)
    registry = default_source_registry()
    metadata_fetcher = SourceFetcher(registry, max_response_bytes=MAX_METADATA_BYTES)
    image_fetcher = SourceFetcher(registry, max_response_bytes=MAX_IMAGE_BYTES)
    archive = ArtifactArchive(ARCHIVE_DIR)
    coverage_records = []
    acquired_images = []

    for contract_id in CONTRACT_IDS:
        detail = metadata_fetcher.fetch(
            "bettergov-dpwh", f"/projects/{contract_id}", retrieved_at=retrieved_at
        )
        image_list = metadata_fetcher.fetch(
            "bettergov-dpwh", f"/projects/{contract_id}/images", retrieved_at=retrieved_at
        )
        detail_artifact = archive.store(detail)
        list_artifact = archive.store(image_list)
        coverage, records = parse_project_image_evidence(
            contract_id, detail.payload, image_list.payload
        )
        if coverage.detail_sha256 != detail_artifact.sha256:
            raise ValueError("project detail archive digest mismatch")
        if coverage.list_sha256 != list_artifact.sha256:
            raise ValueError("project image-list archive digest mismatch")
        coverage_records.append(coverage)

        for record in records:
            source_path = urlparse(record.source_url).path
            acquisition = image_fetcher.fetch(
                "dpwh-transparency-media", source_path, retrieved_at=retrieved_at
            )
            inspection = inspect_jpeg(acquisition.payload, acquisition.media_type)
            artifact = archive.store(acquisition)
            if inspection.sha256 != artifact.sha256:
                raise ValueError("project image archive digest mismatch")
            acquired_images.append(
                AcquiredProjectImage(
                    metadata=record,
                    inspection=inspection,
                    archive_key=(f"project-images/{contract_id}/{inspection.sha256}.jpg"),
                    source_path=artifact.blob_path,
                )
            )

    result = build_project_image_bundle(
        tuple(coverage_records),
        tuple(acquired_images),
        retrieved_at.isoformat(),
        OUTPUT_DIR,
    )
    print(
        json.dumps(
            {
                "passed": True,
                "contract_count": result.contract_count,
                "verified_image_count": result.verified_image_count,
                "quarantined_image_count": result.quarantined_image_count,
                "sql_sha256": result.sql_sha256,
                "manifest_sha256": result.manifest_sha256,
                "output_dir": str(result.output_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
