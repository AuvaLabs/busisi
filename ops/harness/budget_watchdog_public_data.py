"""Build the verified public D1 explorer bundle from archived snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.public_data_bundle import build_public_data_bundle

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    result = build_public_data_bundle(
        ROOT / "data" / "budget_watchdog" / "watchdog.sqlite3",
        ROOT / "data" / "budget_watchdog" / "review-candidates.json",
        ROOT / "data" / "budget_watchdog" / "public-d1-bundle",
    )
    print(
        json.dumps(
            {
                "passed": True,
                "output": str(result.output_dir),
                "budget_records": result.budget_records,
                "delivery_records": result.delivery_records,
                "candidate_links": result.candidate_links,
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
