"""Build, verify and optionally serve the reviewed Busisi publication store."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import uvicorn
from engine.budget_watchdog.publication_api import create_app
from engine.budget_watchdog.publication_store import (
    RegisterQuery,
    build_publication_store,
    query_register,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
DEFAULT_DATABASE = ROOT / "data" / "budget_watchdog" / "busisi-publication.sqlite3"


def _database_checks(database: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
    finally:
        connection.close()
    default_page = query_register(database, RegisterQuery(limit=2))
    search_page = query_register(database, RegisterQuery(q="Catmon", limit=100))
    return {
        "integrity": integrity,
        "metadata": metadata,
        "records": default_page.total,
        "default_page_records": len(default_page.records),
        "default_page_has_cursor": default_page.next_cursor is not None,
        "catmon_records": search_page.total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    build_publication_store(args.golden, args.database)
    with args.database.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    checks = _database_checks(args.database)
    passed = checks["integrity"] == "ok"
    print(
        json.dumps(
            {
                "passed": passed,
                "database": str(args.database),
                "bytes": args.database.stat().st_size,
                "sha256": digest,
                **checks,
            },
            indent=2,
        )
    )
    if not passed:
        return 2
    if args.serve:
        uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
