"""Build the verified public delivery-integrity D1 bundle."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from engine.budget_watchdog.integrity_bundle import build_integrity_bundle

ROOT = Path(__file__).resolve().parents[2]
DPWH_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
PCAB_SHA256 = "016bc9e3427b55e7744558f7726eb773f02f496f88279987c473546d6edb97d2"


def main() -> None:
    result = build_integrity_bundle(
        ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / DPWH_SHA256,
        ROOT / "data" / "budget_watchdog" / "integrity-d1-bundle",
        pcab_snapshot_path=(ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / PCAB_SHA256),
        pcab_retrieved_on=date(2026, 11, 3),
        source_as_of=date(2026, 1, 22),
    )
    print(
        json.dumps(
            {
                "passed": True,
                "output": str(result.output_dir),
                "source_records": result.source_records,
                "integrity_signals": result.integrity_signals,
                "contractors": result.contractors,
                "concentrations": result.concentrations,
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
