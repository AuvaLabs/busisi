"""Run one bounded batch of official-source acquisition retries."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition_queue import AcquisitionQueue
from engine.budget_watchdog.acquisition_runner import (
    AcquisitionRunner,
    RegisteredUrlFetcher,
)
from engine.budget_watchdog.archive import ArtifactArchive

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = (
    ROOT / "data" / "budget_watchdog" / "acquisition-universe"
    / "acquisition-queue.sqlite3"
)
DEFAULT_ARCHIVE = ROOT / "data" / "budget_watchdog" / "archive"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    return parser.parse_args()


def main() -> int:
    options = arguments()
    runner = AcquisitionRunner(
        queue=AcquisitionQueue(options.queue),
        archive=ArtifactArchive(options.archive),
        fetcher=RegisteredUrlFetcher(),
    )
    result = runner.run_batch(limit=options.limit, now=datetime.now(UTC))
    print(json.dumps({
        "passed": True,
        "claimed": result.claimed,
        "verified_archived": result.verified_archived,
        "retry": result.retry,
        "blocked": result.blocked,
        "not_located": result.not_located,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
