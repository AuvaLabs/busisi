"""Validate and build the FY2027 Senate budget-cycle publication bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.senate_budget_bundle import build_senate_budget_bundle
from engine.budget_watchdog.senate_committee_bundle import build_senate_committee_bundle

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "ops" / "harness" / "fixtures" / "senate_2027_catalog.json"
OUTPUT_DIR = ROOT / "data" / "budget_watchdog" / "senate-d1-bundle"
COMMITTEE_PATH = ROOT / "ops" / "harness" / "fixtures" / "senate_2027_committee_watch.json"
COMMITTEE_OUTPUT_DIR = ROOT / "data" / "budget_watchdog" / "senate-committee-d1-bundle"


def main() -> int:
    result = build_senate_budget_bundle(CATALOG_PATH, OUTPUT_DIR)
    committee = build_senate_committee_bundle(COMMITTEE_PATH, COMMITTEE_OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "output_dir": str(result.output_dir),
                "document_count": result.document_count,
                "verified_document_count": result.verified_document_count,
                "catalog_sha256": result.catalog_sha256,
                "bundle_sha256": result.bundle_sha256,
                "committee_state": committee.state,
                "committee_item_count": committee.item_count,
                "committee_bundle_sha256": committee.bundle_sha256,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
