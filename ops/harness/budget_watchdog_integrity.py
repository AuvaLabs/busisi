"""Build the verified public delivery-integrity D1 bundle."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.integrity_bundle import build_integrity_bundle

ROOT = Path(__file__).resolve().parents[2]
DPWH_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"


def main() -> None:
    result = build_integrity_bundle(
        ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / DPWH_SHA256,
        ROOT / "data" / "budget_watchdog" / "integrity-d1-bundle",
    )
    print(
        json.dumps(
            {
                "passed": True,
                "output": str(result.output_dir),
                "source_records": result.source_records,
                "integrity_signals": result.integrity_signals,
                "contractors": result.contractors,
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
