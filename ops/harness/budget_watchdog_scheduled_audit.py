"""Run and retain weekly coverage or monthly full-reconciliation evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.scheduled_audit import audit_command_results

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "cloudflare" / "busisi"
OUTPUT = ROOT / "data" / "budget_watchdog" / "scheduled-audits"
COMMANDS = {
    "operations": (
        ["python3", "ops/harness/budget_watchdog_operational_audit.py"],
        ROOT,
        10_800,
    ),
    "python": (
        ["python3", "-m", "pytest", "engine/tests/budget_watchdog", "-q", "-p", "no:cacheprovider"],
        ROOT,
        3_600,
    ),
    "retrieval": (
        ["python3", "ops/harness/budget_watchdog_evidence_retrieval.py", "audit"],
        ROOT,
        3_600,
    ),
    "worker": (["npm", "run", "check"], WORKER, 3_600),
}


def _run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": (exc.stdout or "")[-8_000:],
            "stderr": (exc.stderr or "")[-8_000:],
            "timed_out": True,
        }
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8_000:],
        "stderr": completed.stderr[-8_000:],
        "timed_out": False,
    }


def _write_report(cadence: str, now: datetime, report: dict[str, Any]) -> Path:
    directory = OUTPUT / cadence
    run_directory = directory / "runs" / now.strftime("%Y%m%dT%H%M%SZ")
    run_directory.mkdir(parents=True, exist_ok=False)
    path = run_directory / "report.json"
    report["report_path"] = str(path)
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(document, encoding="utf-8")
    temporary = directory / ".latest.json.building"
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(directory / "latest.json")
    return path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cadence", choices=("weekly", "monthly"), required=True)
    return parser.parse_args()


def main() -> int:
    options = arguments()
    now = datetime.now(UTC)
    names = ("operations", "retrieval") if options.cadence == "weekly" else tuple(COMMANDS)
    results = {
        name: _run(*COMMANDS[name])
        for name in names
    }
    issues = audit_command_results({
        name: result["returncode"] for name, result in results.items()
    })
    report = {
        "passed": not issues,
        "cadence": options.cadence,
        "checked_at": now.isoformat(),
        "issues": list(issues),
        "checks": results,
    }
    report["report_path"] = str(_write_report(options.cadence, now, report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
