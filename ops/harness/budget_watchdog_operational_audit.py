"""Run and publish the recurring Busisi source and operations audit."""

from __future__ import annotations

import fcntl
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.operations_audit import (
    OperationalFacts,
    audit_operational_facts,
)
from engine.budget_watchdog.source_status_bundle import build_source_status_sql
from ops.harness.budget_watchdog_facility_monitor import (
    DEFAULT_OUTPUT as FACILITY_OUTPUT,
)
from ops.harness.budget_watchdog_facility_monitor import run_facility_monitor
from ops.harness.budget_watchdog_source_monitor import (
    DEFAULT_BASELINE,
    run_monitor,
)
from ops.harness.budget_watchdog_source_monitor import (
    DEFAULT_OUTPUT as SOURCE_OUTPUT,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "cloudflare" / "busisi"
QUEUE = ROOT / "data" / "budget_watchdog" / "project-image-automation" / "coverage-queue.sqlite3"
PUBLICATIONS = ROOT / "data" / "budget_watchdog" / "project-image-publications"
RELEASES = ROOT / "data" / "budget_watchdog" / "project-image-releases"
OUTPUT = ROOT / "data" / "budget_watchdog" / "operational-audit"
PIPELINE_LOCK = ROOT / "data" / "budget_watchdog" / "project-image-automation" / "cycle.lock"
TIMERS = (
    "busisi-project-image-coverage.timer",
    "busisi-acquisition-retry.timer",
    "busisi-weekly-coverage-audit.timer",
    "busisi-monthly-reconciliation.timer",
)


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-8_000:],
        "stderr": completed.stderr[-8_000:],
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _queue_facts(now: datetime) -> tuple[dict[str, Any], bool]:
    with sqlite3.connect(QUEUE) as database:
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        statuses = dict(
            database.execute("SELECT status, COUNT(*) FROM image_tasks GROUP BY status").fetchall()
        )
        total = database.execute("SELECT COUNT(*) FROM image_tasks").fetchone()[0]
        latest = database.execute("SELECT MAX(updated_at) FROM image_tasks").fetchone()[0]
        expired = database.execute(
            """
            SELECT COUNT(*) FROM image_tasks
            WHERE status = 'in_progress' AND lease_until IS NOT NULL AND lease_until < ?
            """,
            (now.isoformat(),),
        ).fetchone()[0]
    return {
        "integrity": integrity,
        "total": total,
        "statuses": statuses,
        "expired_leases": expired,
        "latest_update": latest,
    }, integrity == "ok"


def _release_facts() -> dict[str, Any]:
    published: list[tuple[datetime, dict[str, Any], Path, Path]] = []
    for marker in sorted(PUBLICATIONS.glob("*.json")):
        marker_document = json.loads(marker.read_text(encoding="utf-8"))
        release_id = marker_document.get("release_id")
        if release_id != marker.stem:
            raise ValueError(f"published release marker identity mismatch: {marker.name}")
        manifest_path = RELEASES / release_id / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"published release missing archived manifest: {release_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        release = manifest.get("coverage_release")
        if not isinstance(release, dict) or release.get("release_id") != release_id:
            raise ValueError(f"archived release identity mismatch: {release_id}")
        completed = release.get("completed_contracts")
        released_at = _parse_time(release.get("released_at"))
        if not isinstance(completed, int) or completed < 0 or released_at is None:
            raise ValueError(f"archived release metadata is invalid: {release_id}")
        published.append((released_at, release, marker, manifest_path))
    if not published:
        raise ValueError("no published project-image release evidence")
    _, release, marker, manifest_path = max(published, key=lambda item: item[0])
    return {
        "release_id": release["release_id"],
        "completed_contracts": release["completed_contracts"],
        "released_at": release["released_at"],
        "release_manifest": str(manifest_path),
        "publication_marker": str(marker),
        "publication_marker_exists": marker.is_file(),
    }


def _timer_facts() -> tuple[dict[str, tuple[str, datetime | None]], list[dict[str, Any]]]:
    listing = _run(
        [
            "systemctl",
            "--user",
            "list-timers",
            *TIMERS,
            "--all",
            "--output=json",
            "--no-pager",
        ],
        cwd=ROOT,
    )
    rows = json.loads(listing["stdout"]) if listing["returncode"] == 0 else []
    by_name = {row["unit"]: row for row in rows}
    facts: dict[str, tuple[str, datetime | None]] = {}
    commands = [listing]
    for timer in TIMERS:
        state_result = _run(
            ["systemctl", "--user", "show", timer, "-p", "ActiveState", "--value"],
            cwd=ROOT,
        )
        commands.append(state_result)
        row = by_name.get(timer, {})
        epoch_microseconds = row.get("next")
        next_run = (
            datetime.fromtimestamp(epoch_microseconds / 1_000_000, tz=UTC)
            if isinstance(epoch_microseconds, int) and epoch_microseconds > 0
            else None
        )
        state = state_result["stdout"].strip() if state_result["returncode"] == 0 else "unavailable"
        facts[timer] = (state, next_run)
    return facts, commands


def _write_report(now: datetime, report: dict[str, Any]) -> Path:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUTPUT / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "report.json"
    report["report_path"] = str(path)
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(document, encoding="utf-8")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "latest.json").write_text(document, encoding="utf-8")
    return path


def _run_audit() -> int:
    now = datetime.now(UTC)
    source_report, source_code = run_monitor(DEFAULT_BASELINE, SOURCE_OUTPUT)
    source_sql, source_digest = build_source_status_sql(source_report)
    sql_path = Path(source_report["report_path"]).with_name("public-status.sql")
    sql_path.write_text(source_sql, encoding="utf-8")

    publish = _run(
        [
            "npx",
            "wrangler",
            "d1",
            "execute",
            "busisi-publication",
            "--remote",
            f"--file={sql_path}",
        ],
        cwd=WORKER,
    )
    facility_report, facility_code = run_facility_monitor(FACILITY_OUTPUT)
    facility_publish = _run(
        [
            "npx",
            "wrangler",
            "d1",
            "execute",
            "busisi-publication",
            "--remote",
            f"--file={FACILITY_OUTPUT / 'public-status.sql'}",
        ],
        cwd=WORKER,
    )
    live = _run(["npm", "run", "verify:live"], cwd=WORKER)

    queue, queue_ok = _queue_facts(now)
    release = _release_facts()
    timers, timer_commands = _timer_facts()
    facts = OperationalFacts(
        queue_total=queue["total"],
        queue_statuses=queue["statuses"],
        expired_leases=queue["expired_leases"],
        latest_queue_update=_parse_time(queue["latest_update"]),
        release_completed=release["completed_contracts"],
        publication_marker_exists=release["publication_marker_exists"],
        source_monitor_checked_at=_parse_time(source_report["checked_at"]),
        source_monitor_passed=source_report["passed"],
        timer_states=timers,
    )
    issues = list(audit_operational_facts(facts, now=now))
    if not queue_ok:
        issues.append("private coverage queue failed SQLite integrity check")
    if publish["returncode"] != 0:
        issues.append("source status publication failed")
    if facility_code != 0:
        issues.append("facility source monitor requires review")
    if facility_publish["returncode"] != 0:
        issues.append("facility source status publication failed")
    if live["returncode"] != 0:
        issues.append("live production verification failed")

    report = {
        "passed": not issues and source_code == 0,
        "checked_at": now.isoformat(),
        "issues": issues,
        "source_monitor": {
            "code": source_code,
            "status": source_report["status"],
            "report_path": source_report["report_path"],
            "observations_sha256": source_digest,
        },
        "facility_monitor": {
            "code": facility_code,
            "source_state": facility_report["source_state"],
            "release_state": facility_report["release_state"],
            "report_path": facility_report["report_path"],
            "status_sha256": facility_report["status_sha256"],
        },
        "queue": queue,
        "release": release,
        "timers": {
            name: {
                "state": state,
                "next_run": next_run.isoformat() if next_run else None,
            }
            for name, (state, next_run) in timers.items()
        },
        "commands": {
            "source_status_publication": publish,
            "facility_status_publication": facility_publish,
            "live_verification": live,
            "timers": timer_commands,
        },
    }
    report["report_path"] = str(_write_report(now, report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def main() -> int:
    PIPELINE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _run_audit()


if __name__ == "__main__":
    raise SystemExit(main())
