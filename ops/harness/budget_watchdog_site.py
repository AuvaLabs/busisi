"""Build and validate the local budget-watchdog static preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.budget_watchdog.site_builder import build_site, validate_site

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "site-preview"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    build = build_site(args.golden, args.output)
    validation = validate_site(args.output)
    passed = not (
        validation.missing_routes
        or validation.pages_missing_viewport
        or validation.pages_missing_main_landmark
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "output": str(build.output_dir),
                "pages_written": build.pages_written,
                "project_pages": build.project_pages,
                "missing_routes": validation.missing_routes,
                "pages_missing_viewport": validation.pages_missing_viewport,
                "pages_missing_main_landmark": validation.pages_missing_main_landmark,
            },
            indent=2,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
