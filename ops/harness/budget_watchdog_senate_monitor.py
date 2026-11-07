"""Run the bounded FY2027 Senate catalogue drift monitor."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from engine.budget_watchdog.senate_monitor import SenateMonitorError, run_senate_monitor

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "ops" / "harness" / "fixtures" / "senate_2027_catalog.json"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "senate-monitor"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    shutil.rmtree(args.output, ignore_errors=True)
    try:
        result = run_senate_monitor(args.baseline, args.output)
    except SenateMonitorError as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        report_path = args.output / "report.json"
        if report_path.is_file():
            failure = json.loads(report_path.read_text(encoding="utf-8"))
        else:
            failure = {
                "passed": False,
                "status": "acquisition_failure",
                "error": str(exc),
            }
            report_path.write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(failure, indent=2))
        return 3
    payload = {
        "passed": not result.changed,
        "status": "drift_detected" if result.changed else "unchanged",
        "direct_status": result.direct_status,
        "discovery_mode": result.discovery_mode,
        "expected_document_count": result.expected_document_count,
        "observed_document_count": result.observed_document_count,
        "differences": list(result.differences),
        "response_artifacts": len(result.response_artifacts),
    }
    print(json.dumps(payload, indent=2))
    return 2 if result.changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
