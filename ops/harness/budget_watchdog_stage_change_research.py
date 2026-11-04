"""Build the FY2027 NEP-to-House research story from its authenticated snapshot."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from engine.budget_watchdog.research_editor import write_research_release
from engine.budget_watchdog.research_stage_changes import (
    build_stage_change_release,
    load_stage_change_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = ROOT / "data" / "budget_watchdog" / "hgab-2027-snapshot"
OUTPUT_DIR = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "fy2027-nep-house-changes"
    / "v1"
)
PUBLISHED_AT = "2026-11-04"
EXPECTED_CLAIMS = {
    "stage-total-records": 20_431,
    "stage-dataset-count": 4,
    "stage-house-only": 6_954,
    "stage-publishable-house-only": 6_565,
    "stage-nep-only": 1_784,
    "stage-amount-changes": 508,
    "stage-quarantined": 426,
    "stage-net-movement": 1_372_995_100_000,
}


def main() -> None:
    if not SNAPSHOT_DIR.is_dir():
        raise FileNotFoundError(f"authenticated stage-change snapshot is unavailable: {SNAPSHOT_DIR}")
    records, overview, manifest = load_stage_change_snapshot(SNAPSHOT_DIR)
    release = build_stage_change_release(
        records,
        overview=overview,
        snapshot_manifest=manifest,
        published_at=PUBLISHED_AT,
    )
    observed = {item["id"]: item["value"] for item in release["claims"]}
    if observed != EXPECTED_CLAIMS:
        raise ValueError(f"stage-change research controls changed: {observed!r}")

    building = OUTPUT_DIR.with_name(f".{OUTPUT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    package = write_research_release(release, building)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    building.replace(OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "story_id": package["story_id"],
                "version": package["version"],
                "package_sha256": package["package_sha256"],
                "claims": observed,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
