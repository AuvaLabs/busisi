"""Build and verify the local Cloudflare Worker publication bundle."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.cloudflare_bundle import build_cloudflare_bundle

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
DEFAULT_MIGRATION = ROOT / "cloudflare" / "busisi" / "migrations" / "0001_publication.sql"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "cloudflare-preview"
CATMON_RECORDS = 5


def _database_checks(migration: Path, seed: Path) -> dict[str, object]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.executescript(seed.read_text(encoding="utf-8"))
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        records = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        search_records = connection.execute(
            "SELECT COUNT(*) FROM project_search WHERE project_search MATCH ?",
            ('"catmon"*',),
        ).fetchone()[0]
    finally:
        connection.close()
    return {"integrity": integrity, "records": records, "catmon_records": search_records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--migration", type=Path, default=DEFAULT_MIGRATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = build_cloudflare_bundle(args.golden, args.migration, args.output)
    checks = _database_checks(args.migration, args.output / "reviewed-seed.sql")
    passed = (
        checks["integrity"] == "ok"
        and checks["records"] == result.reviewed_records
        and checks["catmon_records"] == CATMON_RECORDS
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "output": str(result.output_dir),
                "reviewed_records": result.reviewed_records,
                "static_pages": result.static_pages,
                "seed_sha256": result.seed_sha256,
                **checks,
            },
            indent=2,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
