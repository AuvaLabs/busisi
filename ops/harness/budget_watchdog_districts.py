"""Acquire and validate congressional district context for DPWH offices."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.districts import acquire_district_snapshot
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    artifacts, snapshot = acquire_district_snapshot(
        SourceFetcher(default_source_registry()),
        ArtifactArchive(ROOT / "data" / "budget_watchdog" / "archive"),
    )
    print(
        json.dumps(
            {
                "passed": True,
                "retrieved_on": snapshot.retrieved_on.isoformat(),
                "source_commit": snapshot.source_commit,
                "districts": snapshot.district_count,
                "offices": snapshot.office_count,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "source_artifacts": [
                    {
                        "sha256": artifact.sha256,
                        "blob_path": str(artifact.blob_path),
                        "manifest_path": str(artifact.manifest_path),
                    }
                    for artifact in artifacts
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
