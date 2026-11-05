"""Build the private targeted acquisition queue and public-safe snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from engine.budget_watchdog.public_value_acquisition import (
    build_public_value_acquisition,
    write_private_acquisition_queue,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "budget_watchdog"
V4 = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v4"
)
SOURCE_QUEUE = DATA / "acquisition-universe" / "acquisition-queue.sqlite3"
IMAGE_MANIFEST = DATA / "project-image-d1-bundle" / "manifest.json"
OUTPUT = DATA / "public-value-acquisition"
SNAPSHOT_PATH = OUTPUT / "snapshot.json"
QUEUE_PATH = OUTPUT / "queue.sqlite3"
OFFICIAL_REVIEW = DATA / "official-procurement-evidence" / "review.json"
DELIVERY_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
AWARD_SHA256 = "9bfa9e7cbf5041dc3b51a4c2742e60a43d1615f119955581d4b155bf3a6d4a8b"
ARCHIVE_HASH = re.compile(r"-([0-9a-f]{64})\.jpg$")


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _candidates() -> list[dict[str, Any]]:
    payload = json.loads((V4 / "project-examples.json").read_text(encoding="utf-8"))
    return payload["public_value_candidates"]


def _lifecycle_tasks(candidate_ids: list[str]) -> list[dict[str, Any]]:
    if not SOURCE_QUEUE.is_file():
        raise FileNotFoundError(f"acquisition universe queue is unavailable: {SOURCE_QUEUE}")
    connection = sqlite3.connect(f"file:{SOURCE_QUEUE}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = []
        for contract_id in sorted(candidate_ids):
            rows.extend(
                connection.execute(
                    "SELECT contract_id, stage, status, source_url, artifact_sha256 "
                    "FROM acquisition_tasks WHERE contract_id = ? "
                    "ORDER BY stage_order",
                    (contract_id,),
                ).fetchall()
            )
    finally:
        connection.close()
    return [dict(row) for row in rows]


def _project_media(candidate_ids: set[str]) -> tuple[dict[str, dict[str, Any]], str, str]:
    if not IMAGE_MANIFEST.is_file():
        raise FileNotFoundError(f"project-image manifest is unavailable: {IMAGE_MANIFEST}")
    manifest = json.loads(IMAGE_MANIFEST.read_text(encoding="utf-8"))
    release = manifest["coverage_release"]
    result: dict[str, dict[str, Any]] = {}
    archived_media = sorted(manifest.get("media", []), key=lambda item: item.get("archive_key", ""))
    for contract_id in sorted(candidate_ids):
        coverage = manifest["contracts"].get(contract_id)
        if not coverage or coverage.get("state") != "verified_exact":
            continue
        items = [
            item
            for item in archived_media
            if item.get("archive_key", "").startswith(f"project-images/{contract_id}/")
        ]
        if not items:
            raise ValueError(f"verified project media lacks a published artifact: {contract_id}")
        match = ARCHIVE_HASH.search(items[0]["archive_key"])
        if match is None:
            raise ValueError(
                f"project media key lacks an artifact digest: {items[0]['archive_key']}"
            )
        if items[0].get("sha256") != match.group(1):
            raise ValueError(f"project media digest does not reconcile: {contract_id}")
        result[contract_id] = {
            "coverage_state": "verified_exact",
            "artifact_sha256": match.group(1),
            "reader_url": f"/contracts/{contract_id}/#project-images",
        }
    return result, release["release_id"], release["released_at"]


def build_snapshot() -> dict[str, Any]:
    candidates = _candidates()
    candidate_ids = [item["contract_id"] for item in candidates]
    lifecycle = _lifecycle_tasks(candidate_ids)
    project_media, image_release_id, released_at = _project_media(set(candidate_ids))
    lifecycle_digest = _canonical_digest(lifecycle)
    official_review = None
    checked_at = released_at
    official_identities: dict[str, str] = {}
    if OFFICIAL_REVIEW.is_file():
        official_review = json.loads(OFFICIAL_REVIEW.read_text(encoding="utf-8"))
        checked_at = str(official_review["checked_at"])
        official_identities = {
            "official_procurement_catalog_sha256": str(official_review["catalog_sha256"]),
            "official_procurement_review_sha256": _canonical_digest(official_review),
        }
    return build_public_value_acquisition(
        candidates,
        lifecycle,
        project_media=project_media,
        checked_at=checked_at,
        source_identities={
            "award_snapshot_sha256": AWARD_SHA256,
            "delivery_snapshot_sha256": DELIVERY_SHA256,
            "project_image_release_id": image_release_id,
            "targeted_lifecycle_state_sha256": lifecycle_digest,
            **official_identities,
        },
        official_review=official_review,
    )


def main() -> int:
    snapshot = build_snapshot()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_private_acquisition_queue(QUEUE_PATH, snapshot)
    result = {
        "passed": True,
        "snapshot": str(SNAPSHOT_PATH),
        "private_queue": str(QUEUE_PATH),
        "summary": snapshot["summary"],
        "gate_counts": snapshot["gate_counts"],
        "source_identities": snapshot["source_identities"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
