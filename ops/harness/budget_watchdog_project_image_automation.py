"""Run one bounded, gated project-image coverage expansion cycle."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.project_image_bundle import build_project_image_bundle
from engine.budget_watchdog.project_image_queue import (
    ImageCoverageQueue,
    ImageCoverageSeed,
    create_image_coverage_queue,
)
from engine.budget_watchdog.project_image_release import finalize_coverage_release
from engine.budget_watchdog.project_image_runner import ProjectImageRunner
from engine.budget_watchdog.sources import default_source_registry
from ops.harness.budget_watchdog_project_image_publish import publish_bundle

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "budget_watchdog"
ARCHIVE = DATA / "archive"
SOURCE_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
SOURCE = ARCHIVE / "blobs" / SOURCE_SHA256
QUEUE = DATA / "project-image-automation" / "coverage-queue.sqlite3"
OUTPUT = DATA / "project-image-d1-bundle"
CANDIDATE = DATA / ".project-image-automation-candidate"
HISTORY = DATA / "project-image-releases"
LOCK = DATA / "project-image-automation" / "cycle.lock"
REVIEWED_CONTRACTS = frozenset(
    {
        "22HI0028",
        "23DB0126",
        "24HI0131",
        "24HI0148",
        "25HI0028",
        "26HI0094",
    }
)
REVIEWED_YEARS = {
    "22HI0028": 2022,
    "23DB0126": 2023,
    "24HI0131": 2024,
    "24HI0148": 2024,
    "25HI0028": 2025,
    "26HI0094": 2026,
}
EXPECTED_SEEDS = 56_890
MAX_BATCH_SIZE = 500
SYSTEMIC_FAILURE_RATIO = 0.5
SYSTEMIC_FAILURE_MINIMUM = 10
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _seeds() -> tuple[ImageCoverageSeed, ...]:
    if not SOURCE.is_file() or _digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("delivery source snapshot identity does not match")
    table = pq.read_table(
        SOURCE,
        columns=["contractId", "infraYear", "hasSatelliteImage"],
        filters=[("infraYear", "in", ["2024", "2025", "2026"])],
    )
    source_seeds = tuple(
        ImageCoverageSeed(
            contract_id=row["contractId"].strip().upper(),
            fiscal_year=int(row["infraYear"]),
            source_image_hint=bool(row["hasSatelliteImage"]),
            priority=(
                0
                if row["contractId"].strip().upper() in REVIEWED_CONTRACTS
                else 50
                if row["hasSatelliteImage"]
                else 100
            ),
        )
        for row in table.to_pylist()
    )
    source_ids = {item.contract_id for item in source_seeds}
    legacy_seeds = tuple(
        ImageCoverageSeed(contract_id, REVIEWED_YEARS[contract_id], False, 0)
        for contract_id in sorted(REVIEWED_CONTRACTS - source_ids)
    )
    seeds = source_seeds + legacy_seeds
    if len(seeds) != EXPECTED_SEEDS or not REVIEWED_CONTRACTS.issubset(
        {item.contract_id for item in seeds}
    ):
        raise ValueError("project-image seed control total does not reconcile")
    return seeds


def _load_manifest(path: Path) -> dict[str, object] | None:
    manifest = path / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else None


def _archive_release(path: Path, identity: str) -> None:
    destination = HISTORY / identity
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "project-images.sql"):
        source = path / name
        if source.is_file() and not (destination / name).exists():
            shutil.copyfile(source, destination / name)


def _promote_candidate(release_id: str, previous: dict[str, object] | None) -> None:
    if previous is not None:
        previous_id = hashlib.sha256(
            json.dumps(previous, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        _archive_release(OUTPUT, previous_id)
    _archive_release(CANDIDATE, release_id)
    replaced = DATA / ".project-image-previous"
    shutil.rmtree(replaced, ignore_errors=True)
    if OUTPUT.exists():
        OUTPUT.replace(replaced)
    CANDIDATE.replace(OUTPUT)
    shutil.rmtree(replaced, ignore_errors=True)


def run_cycle(*, limit: int, publish: bool) -> dict[str, object]:
    if limit <= 0 or limit > MAX_BATCH_SIZE:
        raise ValueError("coverage batch limit must be between 1 and 500")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = datetime.now(UTC)
        create_image_coverage_queue(QUEUE, _seeds(), source_sha256=SOURCE_SHA256)
        queue = ImageCoverageQueue(QUEUE)
        registry = default_source_registry()
        batch = ProjectImageRunner(
            queue=queue,
            archive=ArtifactArchive(ARCHIVE),
            metadata_fetcher=SourceFetcher(registry, max_response_bytes=MAX_METADATA_BYTES),
            image_fetcher=SourceFetcher(registry, max_response_bytes=MAX_IMAGE_BYTES),
        ).run_batch(limit=limit, now=now)
        if (
            batch.claimed >= SYSTEMIC_FAILURE_MINIMUM
            and (batch.retry / batch.claimed) > SYSTEMIC_FAILURE_RATIO
        ):
            raise RuntimeError(
                "project-image cycle halted because source or validation failures are systemic"
            )
        coverage, images = queue.publication_records()
        previous = _load_manifest(OUTPUT)
        build_project_image_bundle(coverage, images, now.isoformat(), CANDIDATE)
        release = finalize_coverage_release(
            CANDIDATE,
            summary=queue.summary(),
            source_sha256=SOURCE_SHA256,
            released_at=now,
            previous_manifest=previous,
        )
        _promote_candidate(release.release_id, previous)
        published = publish_bundle(OUTPUT) if publish else None
        return {
            "passed": True,
            "batch": {
                "claimed": batch.claimed,
                "verified_exact": batch.verified_exact,
                "no_images": batch.no_images,
                "count_conflict": batch.count_conflict,
                "retry": batch.retry,
                "blocked": batch.blocked,
                "images_archived": batch.images_archived,
            },
            "queue": queue.summary().status_counts,
            "release_id": release.release_id,
            "published_release_id": published,
        }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--publish", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = arguments()
    print(json.dumps(run_cycle(limit=options.limit, publish=options.publish), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
