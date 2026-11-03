"""Export deterministic linkage candidates for manual evidence review."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from engine.budget_watchdog.candidate_queue import generate_review_candidates

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT / "data" / "budget_watchdog" / "watchdog.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    candidates = generate_review_candidates(
        args.database,
        fiscal_years=tuple(args.years),
        limit=args.limit,
    )
    payload = []
    for candidate in candidates:
        record = asdict(candidate)
        record["confidence"] = candidate.confidence.value
        payload.append(record)
    document = json.dumps(
        {"count": len(payload), "candidates": payload},
        indent=2,
        ensure_ascii=False,
    )
    if args.output is None:
        print(document)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{document}\n", encoding="utf-8")
        print(json.dumps({"count": len(payload), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
