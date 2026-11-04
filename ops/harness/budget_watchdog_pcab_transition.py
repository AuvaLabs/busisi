"""Review an official PCAB snapshot transition before changing its record floor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from engine.budget_watchdog.source_monitor import review_pcab_transition


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    options = arguments()
    if not options.reviewed.is_file() or not options.observed.is_file():
        raise ValueError("both archived PCAB snapshots must exist")
    report = review_pcab_transition(
        options.reviewed.read_bytes(),
        options.observed.read_bytes(),
        reviewed_sha256=_digest(options.reviewed),
        observed_sha256=_digest(options.observed),
        observed_on=options.observed_on,
    )
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    options.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = options.output.with_suffix(".building")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(options.output)
    print(document, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
