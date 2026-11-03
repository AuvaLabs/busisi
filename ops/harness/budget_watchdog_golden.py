"""Evaluate reviewed budget-to-project links and the release gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from engine.budget_watchdog.golden import evaluate_golden_cases, load_golden_cases

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--require-release-ready", action="store_true")
    args = parser.parse_args()

    summary = evaluate_golden_cases(load_golden_cases(args.path))
    payload = asdict(summary)
    payload["agreement"] = str(summary.agreement)
    for result in payload["results"]:
        result["expected_confidence"] = result["expected_confidence"].value
        result["actual_confidence"] = result["actual_confidence"].value
    print(json.dumps(payload, indent=2, sort_keys=True))

    if summary.passed != summary.total:
        return 1
    if args.require_release_ready and not summary.release_ready:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
