"""Build the full FY2024-FY2026 contract acquisition universe and queue."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition_queue import (
    AcquisitionQueue,
    apply_reviewed_evidence,
    create_acquisition_queue,
)
from engine.budget_watchdog.acquisition_release import build_acquisition_release
from engine.budget_watchdog.acquisition_universe import build_acquisition_universe
from engine.budget_watchdog.archive import ArtifactArchive, FileAcquisition
from engine.budget_watchdog.contract_evidence import load_contract_evidence_catalog

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "budget_watchdog"
ARCHIVE = DATA / "archive"
OUTPUT = DATA / "acquisition-universe"
STAGING = DATA / "full-universe" / "staging" / "philgeps.parquet.partial"
DELIVERY_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
AWARD_SHA256 = "9bfa9e7cbf5041dc3b51a4c2742e60a43d1615f119955581d4b155bf3a6d4a8b"
AWARD_REVISION = "b98de579579e8c7e79bac2a22ac7491549db6d0d"
AWARD_BYTES = 492_869_009
AWARD_URL = (
    "https://huggingface.co/datasets/bettergovph/philgeps-data/resolve/"
    f"{AWARD_REVISION}/philgeps.parquet"
)
RETRIEVED_AT = datetime(2026, 11, 3, 13, 24, 25, tzinfo=UTC)


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _archive_award_source() -> Path:
    blob = ARCHIVE / "blobs" / AWARD_SHA256
    if blob.is_file():
        if blob.stat().st_size != AWARD_BYTES or _digest(blob) != AWARD_SHA256:
            raise ValueError("archived award mirror does not match its recorded identity")
        return blob
    if not STAGING.is_file():
        raise ValueError("version-pinned PhilGEPS mirror has not been downloaded")
    archived = ArtifactArchive(ARCHIVE).store_file(FileAcquisition(
        source_id="bettergov-philgeps-snapshot",
        source_url=AWARD_URL,
        retrieved_at=RETRIEVED_AT,
        media_type="application/vnd.apache.parquet",
        path=STAGING,
        source_version=AWARD_REVISION,
        source_last_modified=datetime(2026, 1, 6, 8, 31, 6, tzinfo=UTC),
    ))
    if archived.sha256 != AWARD_SHA256 or archived.byte_size != AWARD_BYTES:
        raise ValueError("downloaded award mirror does not match its pinned fingerprint")
    return archived.blob_path


def main() -> int:
    award_path = _archive_award_source()
    snapshot = build_acquisition_universe(
        ARCHIVE / "blobs" / DELIVERY_SHA256,
        award_path,
        fiscal_years=(2024, 2025, 2026),
        delivery_sha256=DELIVERY_SHA256,
        award_sha256=AWARD_SHA256,
        award_revision=AWARD_REVISION,
        checked_on=date(2026, 11, 3),
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    queue_path = OUTPUT / "acquisition-queue.sqlite3"
    create_acquisition_queue(queue_path, snapshot)
    reviewed = load_contract_evidence_catalog(
        (ROOT / "ops" / "harness" / "fixtures" / "contract_evidence_catalog.json").read_bytes()
    )
    apply_reviewed_evidence(queue_path, reviewed)
    queue_summary = AcquisitionQueue(queue_path).summary()
    release = build_acquisition_release(
        snapshot, queue_summary, award_byte_size=award_path.stat().st_size
    )
    release_path = OUTPUT / "release.json"
    release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
    result = {
        "passed": True,
        "queue": str(queue_path),
        "release": str(release_path),
        "contract_count": snapshot.summary.contract_count,
        "source_row_count": snapshot.summary.source_row_count,
        "accepted_match_rows": snapshot.summary.accepted_match_rows,
        "quarantined_rows": snapshot.summary.quarantined_rows,
        "lifecycle_task_count": snapshot.summary.lifecycle_task_count,
        "state_counts": dict(snapshot.summary.state_counts),
        "queue_status_counts": queue_summary.status_counts,
        "award_sha256": AWARD_SHA256,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
