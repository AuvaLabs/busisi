"""Run the bounded FY2027 Senate catalogue drift monitor."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.senate_monitor import (
    ACCESS_BLOCK_FAILURE_KINDS,
    SenateMonitorError,
    run_senate_monitor,
)
from engine.budget_watchdog.source_resilience import source_check_due

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "ops" / "harness" / "fixtures" / "senate_2027_catalog.json"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "senate-monitor"
RETRYABLE_FAILURE_KINDS = ACCESS_BLOCK_FAILURE_KINDS | {
    "publisher_maintenance",
    "rate_limited",
    "server_error",
    "transport_error",
}


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
            "monitor_state": (
                "waiting_for_retry" if previous.get("failure_kind") else "waiting_for_next_check"
            ),
            "alert_reason": None,
            "prior_response_artifact_count": (
                len(prior_artifacts) if isinstance(prior_artifacts, list) else 0
            ),
            "response_artifacts": [],
        }
        _write_state(args.output / "report.json", waiting)
        print(json.dumps(waiting, indent=2))
        return 0
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
                "failure_kind": exc.failure_kind,
                "error": str(exc),
            }
        failure.setdefault("failure_kind", exc.failure_kind)
        failure["monitor_state"] = (
            "access_blocked"
            if failure["failure_kind"] in ACCESS_BLOCK_FAILURE_KINDS
            else "check_failed"
        )
        alert = _failure_alert(failure, strict=args.strict)
        _record_attempt(args.output, {**failure, "alert_reason": alert})
        return 3 if alert else 0
    report = json.loads((args.output / "report.json").read_text(encoding="utf-8"))
    _record_attempt(
        args.output,
        {
            **report,
            "monitor_state": result.status,
            "alert_reason": "catalogue_changed" if result.changed else None,
        },
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


def _record_attempt(output: Path, report: dict[str, object]) -> None:
    _write_state(output / "report.json", report)
    _write_state(output / "state.json", report)
    print(json.dumps(report, indent=2))


def _failure_alert(report: dict[str, object], *, strict: bool) -> str | None:
    kind = report.get("failure_kind")
    if not isinstance(kind, str) or kind not in RETRYABLE_FAILURE_KINDS:
        return kind if isinstance(kind, str) else "check_failed"
    if strict and report.get("freshness_state") in {"stale", "unknown"}:
        return "stale_source" if report.get("freshness_state") == "stale" else "source_unverified"
    return None


def format_summary(report: dict[str, object]) -> str:
    state = str(report.get("monitor_state", "unknown"))
    blocked = report.get("failure_kind") in ACCESS_BLOCK_FAILURE_KINDS
    labels = {
        "access_blocked": "Access blocked",
        "check_failed": "Check failed",
        "drift_detected": "Catalogue changes detected",
        "unchanged": "Catalogue checked and unchanged",
        "waiting_for_next_check": "Waiting for the next scheduled check",
        "waiting_for_retry": (
            "Waiting to retry after access was blocked" if blocked else "Waiting to retry"
        ),
    }
    retrying = bool(report.get("failure_kind"))
    next_label = "Next retry eligible" if retrying else "Next check eligible"
    lines = [
        "## FY2027 Senate catalogue check",
        "",
        f"- Status: **{labels.get(state, 'Unknown')}**",
        f"- Official portal: `{report.get('direct_status', 'unknown')}`",
        f"- Check method: `{report.get('discovery_mode', 'unknown')}`",
        f"- Failure type: `{report.get('failure_kind') or 'none'}`",
        f"- Evidence freshness: `{report.get('freshness_state', 'unknown')}`",
        f"- Last attempt (UTC): `{report.get('checked_at') or 'unknown'}`",
        f"- Last successful check (UTC): `{report.get('last_success_at') or 'none'}`",
        f"- Consecutive failed checks: `{report.get('consecutive_failures', 0)}`",
        f"- {next_label} (UTC): `{report.get('next_check_at') or 'unknown'}`",
    ]
    if report.get("alert_reason"):
        lines.append(f"- Alert: `{report['alert_reason']}`")
    if state == "waiting_for_next_check" and report.get("status") == "drift_detected":
        lines.append("- The previous check found catalogue changes that need review.")
    if report.get("error"):
        lines.append(f"- Reason: {report['error']}")
    if report.get("next_check_at"):
        lines.extend(
            [
                "",
                "The next automatic attempt runs on the first scheduled run at or after that time.",
            ]
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
