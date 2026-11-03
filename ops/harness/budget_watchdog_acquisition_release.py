"""Validate and build the frozen acquisition-universe publication summary."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.acquisition_release_bundle import (
    build_acquisition_release_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "ops" / "harness" / "fixtures" / "acquisition_universe_release.json"
OUTPUT = ROOT / "data" / "budget_watchdog" / "acquisition-universe-d1-bundle"


def main() -> int:
    result = build_acquisition_release_bundle(CATALOG, OUTPUT)
    print(json.dumps({
        "passed": True,
        "output_dir": str(result.output_dir),
        "contract_count": result.contract_count,
        "lifecycle_task_count": result.lifecycle_task_count,
        "catalog_sha256": result.catalog_sha256,
        "bundle_sha256": result.bundle_sha256,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
