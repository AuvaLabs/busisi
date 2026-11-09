"""Run the bounded FY2027 Senate catalogue drift monitor."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.senate_monitor import SenateMonitorError, run_senate_monitor
from engine.budget_watchdog.source_resilience import source_check_due

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "ops" / "harness" / "fixtures" / "senate_2027_catalog.json"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "senate-monitor"
IMMEDIATE_FAILURE_KINDS = frozenset({"validation_error", "unexpected_response", "not_found"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--respect-backoff", action="store_true")
    args = parser.parse_args()
    previous = _load_state(args.output / "state.json")
    if args.respect_backoff and not source_check_due(previous, at=datetime.now(UTC)):
        assert previous is not None
        prior_artifacts = previous.get("response_artifacts")
        waiting = {
            **previous,
            "monitor_state": "waiting_for_retry",
            "prior_response_artifact_count": (
                len(prior_artifacts) if isinstance(prior_artifacts, list) else 0
            ),
            "response_artifacts": [],
        }
        _write_state(args.output / "report.json", waiting)
        print(json.dumps(waiting, indent=2))
        return _failure_exit(waiting, strict=args.strict)
    shutil.rmtree(args.output / "responses", ignore_errors=True)
    (args.output / "report.json").unlink(missing_ok=True)
    try:
        result = run_senate_monitor(args.baseline, args.output, previous_report=previous)
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
        _write_state(args.output / "state.json", failure)
        return _failure_exit(failure, strict=args.strict)
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
    _write_state(
        args.output / "state.json",
        json.loads((args.output / "report.json").read_text(encoding="utf-8")),
    )
    return 2 if result.changed else 0


def _load_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _failure_exit(report: dict[str, object], *, strict: bool) -> int:
    if report.get("failure_kind") in IMMEDIATE_FAILURE_KINDS:
        return 3
    if strict and report.get("freshness_state") in {"stale", "unknown"}:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
