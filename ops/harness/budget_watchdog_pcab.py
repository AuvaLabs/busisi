"""Acquire and validate the official PCAB regular-license table."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.pcab import acquire_pcab_regular_licenses
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    archive = ArtifactArchive(ROOT / "data" / "budget_watchdog" / "archive")
    artifact, snapshot = acquire_pcab_regular_licenses(
        SourceFetcher(default_source_registry()),
        archive,
    )
    print(
        json.dumps(
            {
                "passed": True,
                "snapshot_date": snapshot.retrieved_on.isoformat(),
                "records": snapshot.record_count,
                "unique_license_numbers": len(snapshot.licenses_by_number),
                "sha256": artifact.sha256,
                "blob_path": str(artifact.blob_path),
                "manifest_path": str(artifact.manifest_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
