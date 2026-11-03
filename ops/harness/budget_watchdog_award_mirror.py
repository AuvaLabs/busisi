"""Validate and build the versioned PhilGEPS award mirror publication bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.award_mirror_bundle import build_award_mirror_bundle

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "ops" / "harness" / "fixtures" / "philgeps_award_mirror.json"
OUTPUT = ROOT / "data" / "budget_watchdog" / "award-mirror-d1-bundle"


def main() -> int:
    result = build_award_mirror_bundle(CATALOG, OUTPUT)
    print(json.dumps({
        "passed": True,
        "output_dir": str(result.output_dir),
        "record_count": result.record_count,
        "catalog_sha256": result.catalog_sha256,
        "bundle_sha256": result.bundle_sha256,
        "source_file_archived": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
