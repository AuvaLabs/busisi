"""Validate and build the contract-lifecycle evidence publication bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.contract_evidence_bundle import build_contract_evidence_bundle

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "ops" / "harness" / "fixtures" / "contract_evidence_catalog.json"
OUTPUT = ROOT / "data" / "budget_watchdog" / "contract-evidence-d1-bundle"


def main() -> int:
    result = build_contract_evidence_bundle(CATALOG, OUTPUT)
    print(
        json.dumps(
            {
                "passed": True,
                "output_dir": str(result.output_dir),
                "contract_count": result.contract_count,
                "item_count": result.item_count,
                "retry_item_count": result.retry_item_count,
                "catalog_sha256": result.catalog_sha256,
                "bundle_sha256": result.bundle_sha256,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
