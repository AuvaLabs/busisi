"""Validate and build the reviewed COA evidence publication bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.coa_bundle import build_coa_bundle

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "ops" / "harness" / "fixtures" / "coa_audit_catalog.json"
OUTPUT_DIR = ROOT / "data" / "budget_watchdog" / "coa-d1-bundle"


def main() -> int:
    result = build_coa_bundle(CATALOG_PATH, OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "output_dir": str(result.output_dir),
                "report_count": result.report_count,
                "archived_reports": result.archived_reports,
                "checked_projects": result.checked_projects,
                "project_matches": result.project_matches,
                "catalog_sha256": result.catalog_sha256,
                "bundle_sha256": result.bundle_sha256,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
