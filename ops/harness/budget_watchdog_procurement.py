"""Validate and build the reviewed procurement evidence publication bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.procurement_bundle import build_procurement_bundle

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "ops" / "harness" / "fixtures" / "procurement_evidence_catalog.json"
OUTPUT_DIR = ROOT / "data" / "budget_watchdog" / "procurement-d1-bundle"


def main() -> int:
    result = build_procurement_bundle(CATALOG_PATH, OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "output_dir": str(result.output_dir),
                "source_count": result.source_count,
                "archived_sources": result.archived_sources,
                "record_count": result.record_count,
                "checked_projects": result.checked_projects,
                "projects_with_evidence": result.projects_with_evidence,
                "catalog_sha256": result.catalog_sha256,
                "bundle_sha256": result.bundle_sha256,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
