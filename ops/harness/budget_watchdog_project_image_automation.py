"""Run one bounded, gated project-image coverage expansion cycle."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.coverage_controller import (
    MAX_WORKERS,
    CoverageCycleMetrics,
    advance_controller,
    load_controller,
    save_controller,
    should_halt_cycle,
)
from engine.budget_watchdog.coverage_priority import (
    CoveragePriorityFacts,
    classify_coverage_priority,
)
from engine.budget_watchdog.integrity import contractor_identities
from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.project_image_bundle import build_project_image_bundle
from engine.budget_watchdog.project_image_queue import (
    ImageCoverageQueue,
    ImageCoverageSeed,
    create_image_coverage_queue,
)
from engine.budget_watchdog.project_image_release import finalize_coverage_release
from engine.budget_watchdog.project_image_runner import (
    ProjectImageBatchResult,
    ProjectImageRunner,
    merge_batch_results,
)
from engine.budget_watchdog.rate_limit import HostRateLimiter
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
CONTROLLER = DATA / "project-image-automation" / "controller.json"
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
MAX_BATCH_SIZE = 2000
CANARY_BATCH_SIZE = 25
ACQUISITION_CHUNK_SIZE = 100
REQUESTS_PER_SECOND_PER_HOST = 2.0
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
REPEATED_CONTRACTOR_MINIMUM = 10
HIGH_VALUE_PERCENTILE_NUMERATOR = 9
HIGH_VALUE_PERCENTILE_DENOMINATOR = 10
COMPLETE_PROGRESS = Decimal("100")
PRIORITY_COLUMNS = (
    "contractId",
    "infraYear",
    "hasSatelliteImage",
    "budget",
    "contractor",
    "status",
    "progress",
    "latitude",
    "longitude",
    "startDate",
    "completionDate",
)
COA_CATALOG = ROOT / "ops" / "harness" / "fixtures" / "coa_audit_catalog.json"


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integrity_question(row: dict[str, object]) -> bool:
    status = _text(row.get("status")).casefold().replace("-", " ")
    progress = Decimal(str(row.get("progress") or 0))
    missing_coordinate = row.get("latitude") is None or row.get("longitude") is None
    date_conflict = bool(
        row.get("startDate")
        and row.get("completionDate")
        and row["startDate"] > row["completionDate"]
    )
    status_conflict = (
        status in {"ongoing", "on going"} and progress >= COMPLETE_PROGRESS
    ) or (status == "completed" and progress < COMPLETE_PROGRESS)
    image_gap = status == "completed" and not bool(row.get("hasSatelliteImage"))
    return missing_coordinate or date_conflict or status_conflict or image_gap


def _coa_contracts() -> frozenset[str]:
    document = json.loads(COA_CATALOG.read_text(encoding="utf-8"))
    return frozenset(
        item["contract_id"]
        for item in document["project_coverage"]
        if item["status"] != "not_covered"
    )


def _priority_inputs(
    rows: tuple[dict[str, object], ...],
) -> tuple[int, Counter[str], frozenset[str]]:
    amounts = sorted(parse_centavos(Decimal(str(row["budget"]))) for row in rows)
    threshold_index = len(amounts) * HIGH_VALUE_PERCENTILE_NUMERATOR // (
        HIGH_VALUE_PERCENTILE_DENOMINATOR
    )
    threshold = amounts[min(threshold_index, len(amounts) - 1)]
    contractor_counts: Counter[str] = Counter()
    for row in rows:
        contractor_counts.update(
            item.key for item in contractor_identities(_text(row.get("contractor")))
        )
    repeated = frozenset(
        key for key, count in contractor_counts.items() if count >= REPEATED_CONTRACTOR_MINIMUM
    )
    return threshold, contractor_counts, repeated


def _row_seed(
    row: dict[str, object],
    *,
    high_value_threshold: int,
    repeated_contractors: frozenset[str],
    coa_contracts: frozenset[str],
) -> ImageCoverageSeed:
    contract_id = _text(row["contractId"]).upper()
    identities = contractor_identities(_text(row.get("contractor")))
    facts = CoveragePriorityFacts(
        reviewed=contract_id in REVIEWED_CONTRACTS,
        source_image_hint=bool(row.get("hasSatelliteImage")),
        high_value=parse_centavos(Decimal(str(row["budget"]))) >= high_value_threshold,
        joint_venture=len(identities) > 1,
        repeated_contractor=any(item.key in repeated_contractors for item in identities),
        integrity_question=_integrity_question(row),
        coa_evidence=contract_id in coa_contracts,
    )
    return ImageCoverageSeed(
        contract_id=contract_id,
        fiscal_year=int(_text(row["infraYear"])),
        source_image_hint=bool(row.get("hasSatelliteImage")),
        priority=classify_coverage_priority(facts).score,
    )


def _seeds() -> tuple[ImageCoverageSeed, ...]:
    if not SOURCE.is_file() or _digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("delivery source snapshot identity does not match")
    table = pq.read_table(
        SOURCE,
        columns=list(PRIORITY_COLUMNS),
        filters=[("infraYear", "in", ["2024", "2025", "2026"])],
    )
    rows = tuple(table.to_pylist())
    high_value_threshold, _, repeated_contractors = _priority_inputs(rows)
    coa_contracts = _coa_contracts()
    source_seeds = tuple(
        _row_seed(
            row,
            high_value_threshold=high_value_threshold,
            repeated_contractors=repeated_contractors,
            coa_contracts=coa_contracts,
        )
        for row in rows
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


def _metrics(batch: ProjectImageBatchResult) -> CoverageCycleMetrics:
    return CoverageCycleMetrics(
        claimed=batch.claimed,
        failures=batch.retry,
        rate_limited=batch.rate_limited,
    )


def _runner(queue: ImageCoverageQueue) -> ProjectImageRunner:
    registry = default_source_registry()
    limiter = HostRateLimiter(requests_per_second=REQUESTS_PER_SECOND_PER_HOST)

    def fetchers() -> tuple[SourceFetcher, SourceFetcher]:
        return (
            SourceFetcher(
                registry,
                max_response_bytes=MAX_METADATA_BYTES,
                request_gate=limiter.wait_for_url,
            ),
            SourceFetcher(
                registry,
                max_response_bytes=MAX_IMAGE_BYTES,
                request_gate=limiter.wait_for_url,
            ),
        )

    metadata_fetcher, image_fetcher = fetchers()
    return ProjectImageRunner(
        queue=queue,
        archive=ArtifactArchive(ARCHIVE),
        metadata_fetcher=metadata_fetcher,
        image_fetcher=image_fetcher,
        fetcher_factory=fetchers,
    )


def run_cycle(*, limit: int | None, publish: bool, workers: int | None = None) -> dict[str, object]:
    controller = load_controller(CONTROLLER)
    selected_limit = limit if limit is not None else controller.batch_limit
    selected_workers = workers if workers is not None else controller.workers
    if selected_limit <= 0 or selected_limit > MAX_BATCH_SIZE:
        raise ValueError("coverage batch limit must be between 1 and 2000")
    if selected_workers <= 0 or selected_workers > MAX_WORKERS:
        raise ValueError("coverage worker count must be between 1 and 4")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = datetime.now(UTC)
        create_image_coverage_queue(QUEUE, _seeds(), source_sha256=SOURCE_SHA256)
        queue = ImageCoverageQueue(QUEUE)
        runner = _runner(queue)
        batches: list[ProjectImageBatchResult] = []
        remaining = selected_limit
        first_batch = True
        while remaining > 0:
            chunk_limit = min(
                CANARY_BATCH_SIZE if first_batch else ACQUISITION_CHUNK_SIZE,
                remaining,
            )
            first_batch = False
            batch = runner.run_batch(
                limit=chunk_limit,
                now=now,
                workers=selected_workers,
            )
            if batch.claimed == 0:
                break
            batches.append(batch)
            remaining -= batch.claimed
            total = merge_batch_results(tuple(batches))
            if should_halt_cycle(_metrics(batch)) or should_halt_cycle(_metrics(total)):
                degraded = advance_controller(controller, _metrics(total))
                save_controller(CONTROLLER, degraded)
                raise RuntimeError(
                    "project-image cycle halted by the source-failure circuit breaker"
                )
            if batch.claimed < chunk_limit:
                break

        total = (
            merge_batch_results(tuple(batches))
            if batches
            else ProjectImageBatchResult(
                claimed=0,
                verified_exact=0,
                no_images=0,
                count_conflict=0,
                retry=0,
                blocked=0,
                images_archived=0,
                rate_limited=0,
                source_failure=0,
                server_failure=0,
                validation_failure=0,
            )
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
        next_controller = advance_controller(controller, _metrics(total))
        save_controller(CONTROLLER, next_controller)
        return {
            "passed": True,
            "batch": asdict(total),
            "controller": {
                "workers": selected_workers,
                "batch_limit": selected_limit,
                "healthy_streak": next_controller.healthy_streak,
                "next_workers": next_controller.workers,
                "next_batch_limit": next_controller.batch_limit,
            },
            "queue": queue.summary().status_counts,
            "release_id": release.release_id,
            "published_release_id": published,
        }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--publish", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = arguments()
    print(
        json.dumps(
            run_cycle(
                limit=options.limit,
                workers=options.workers,
                publish=options.publish,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
