"""Build the FY2027 health-facility research story from checked source files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from engine.budget_watchdog.research_editor import write_research_release
from engine.budget_watchdog.research_health_facilities import (
    build_health_facility_release,
)
from engine.budget_watchdog.research_stage_changes import load_stage_change_snapshot

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = ROOT / "data" / "budget_watchdog" / "hgab-2027-snapshot"
OUTPUT_DIR = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "fy2027-health-facility-changes"
    / "v1"
)
PUBLISHED_AT = "2026-11-25"
EXPECTED_CLAIMS = {
    "health-total-records": 746,
    "health-nep-total": 1_447_251_900_000,
    "health-house-total": 1_002_165_900_000,
    "health-net-movement": -445_086_000_000,
    "health-house-only": 184,
    "health-nep-only": 163,
    "health-amount-changes": 118,
    "health-unchanged": 281,
    "health-largest-regional-movement": -239_970_000_000,
}


def main() -> None:
    if not SNAPSHOT_DIR.is_dir():
        raise FileNotFoundError(
            f"checked stage-change source files are unavailable: {SNAPSHOT_DIR}"
        )
    records, overview, manifest = load_stage_change_snapshot(SNAPSHOT_DIR)
    release = build_health_facility_release(
        records,
        overview=overview,
        snapshot_manifest=manifest,
        published_at=PUBLISHED_AT,
    )
    observed = {item["id"]: item["value"] for item in release["claims"]}
    if observed != EXPECTED_CLAIMS:
        raise ValueError(f"health-facility research controls changed: {observed!r}")

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
