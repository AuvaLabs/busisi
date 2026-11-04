"""Build the published Busisi research package from an immutable DPWH snapshot."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
from engine.budget_watchdog.research_package import (
    build_multipurpose_release,
    write_release_package,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
SOURCE_PATH = ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / SOURCE_SHA256
OUTPUT_DIR = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v1"
)
SOURCE_MODIFIED = "2026-01-22"
PUBLISHED_AT = "2026-11-04"
EXPECTED_CLAIMS = {
    "mpb-total-records": 12_609,
    "mpb-ongoing": 5_842,
    "mpb-active-pipeline": 7_024,
    "mpb-completed": 5_582,
    "mpb-positive-active-budget": 6_093,
    "mpb-existing-work-wording": 2_812,
    "mpb-prior-coordinate-candidates": 31,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f"archived DPWH source is unavailable: {SOURCE_PATH}")
    if _sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise ValueError("archived DPWH source digest does not match the registered identity")

    columns = [
        "contractId",
        "description",
        "status",
        "budget",
        "infraYear",
        "location",
        "latitude",
        "longitude",
        "hasSatelliteImage",
    ]
    rows = pq.read_table(SOURCE_PATH, columns=columns).to_pylist()
    release = build_multipurpose_release(
        rows,
        source_sha256=SOURCE_SHA256,
        source_modified=SOURCE_MODIFIED,
        published_at=PUBLISHED_AT,
    )
    claims = {claim["id"]: claim["value"] for claim in release["claims"]}
    observed = {key: claims.get(key) for key in EXPECTED_CLAIMS}
    if observed != EXPECTED_CLAIMS:
        raise ValueError(f"research control totals changed: {observed!r}")

    building = OUTPUT_DIR.with_name(f".{OUTPUT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    manifest = write_release_package(release, building)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    building.replace(OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "story_id": manifest["story_id"],
                "version": manifest["version"],
                "package_sha256": manifest["package_sha256"],
                "claims": observed,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
