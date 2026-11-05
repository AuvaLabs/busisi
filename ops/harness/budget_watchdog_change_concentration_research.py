"""Build the FY2027 project-list concentration research release."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from engine.budget_watchdog.research_change_concentration import (
    build_change_concentration_release,
)
from engine.budget_watchdog.research_editor import write_research_release
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
    / "fy2027-change-concentration"
    / "v1"
)
PUBLISHED_AT = "2026-11-05"
EXPECTED_CLAIMS = {
    "concentration-total-rows": 20_431,
    "concentration-changed-rows": 9_283,
    "concentration-house-only": 6_954,
    "concentration-top-region": 782,
    "concentration-top-program": 5_053,
    "concentration-quarantined": 426,
}


def main() -> None:
    if not SNAPSHOT_DIR.is_dir():
        raise FileNotFoundError(
            f"authenticated stage-change snapshot is unavailable: {SNAPSHOT_DIR}"
        )
    records, overview, manifest = load_stage_change_snapshot(SNAPSHOT_DIR)
    release = build_change_concentration_release(
        records,
        overview=overview,
        snapshot_manifest=manifest,
        published_at=PUBLISHED_AT,
    )
    observed = {item["id"]: item["value"] for item in release["claims"]}
    if observed != EXPECTED_CLAIMS:
        raise ValueError(f"change-concentration controls changed: {observed!r}")
    if release["chart_data"]["regions"][0]["label"] != "Region IV-A":
        raise ValueError("top regional concentration changed")
    if release["chart_data"]["programs"][0]["label"] != (
        "Convergence and Special Support Program"
    ):
        raise ValueError("top program concentration changed")

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
