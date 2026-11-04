"""Monitor the official DepEd facility source and emit a public status update."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.acquisition import AcquisitionError
from engine.budget_watchdog.facility_registry import (
    DEPED_PPP_SOURCE_URL,
    EXPECTED_DEPED_PPP_SCHOOLS,
)
from engine.budget_watchdog.facility_status_bundle import build_facility_status_sql
from ops.harness.budget_watchdog_facilities import (
    CANONICAL_DATABASE,
    HGAB_BUNDLE_DIR,
    acquire_facility_registry,
    build_facility_release,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "facility-source-monitor"
DEFAULT_REVIEW_MANIFEST = ROOT / "ops" / "harness" / "fixtures" / "facility_review_manifest.json"
HTTP_FORBIDDEN = 403


def _base_report(now: datetime) -> dict[str, Any]:
    return {
        "checked_at": now.isoformat(),
        "source_url": DEPED_PPP_SOURCE_URL,
        "http_status": None,
        "source_artifact_sha256": None,
        "expected_facilities": EXPECTED_DEPED_PPP_SCHOOLS,
        "validated_facilities": 0,
        "candidate_links": 0,
        "reviewed_cases": 0,
        "precision_bps": None,
        "agreement_bps": None,
        "critical_failures": 0,
    }


def facility_failure_report(
    error: AcquisitionError,
    now: datetime,
) -> tuple[dict[str, Any], int]:
    """Classify source failures without treating the known 403 as data."""

    report = _base_report(now)
    report["http_status"] = error.http_status
    if error.http_status == HTTP_FORBIDDEN:
        report.update(
            source_state="blocked",
            release_state="source_blocked",
            status_note=(
                "The official DepEd source blocked unattended acquisition. "
                "No registry bytes or inferred links were published."
            ),
        )
        return report, 0
    if error.http_status in {404, 410}:
        report.update(
            source_state="unavailable",
            release_state="source_unavailable",
            status_note="The registered official DepEd workbook is unavailable and needs review.",
        )
        return report, 2
    report.update(
        source_state="acquisition_failure",
        release_state="acquisition_failed",
        status_note="The official DepEd workbook could not be acquired and needs review.",
    )
    return report, 3


def _validation_failure_report(error: Exception, now: datetime) -> dict[str, Any]:
    report = _base_report(now)
    report.update(
        source_state="validation_failure",
        release_state="validation_failed",
        status_note="The acquired DepEd workbook failed a release validation and needs review.",
        internal_error=type(error).__name__,
    )
    return report


def _write_report(output: Path, now: datetime, report: dict[str, Any]) -> Path:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    status_sql, status_sha256 = build_facility_status_sql(report)
    report["status_sha256"] = status_sha256
    report["report_path"] = str(report_path)
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(document, encoding="utf-8")
    (output / "latest.json").write_text(document, encoding="utf-8")
    (output / "public-status.sql").write_text(status_sql, encoding="utf-8")
    return report_path


def run_facility_monitor(
    output: Path = DEFAULT_OUTPUT,
    *,
    review_manifest: Path | None = DEFAULT_REVIEW_MANIFEST,
    reset_output: bool = False,
) -> tuple[dict[str, Any], int]:
    """Check source availability and build a held or review-gated candidate release."""

    if reset_output:
        shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    try:
        acquisition, digest, records = acquire_facility_registry(now, output / "archive")
        release = build_facility_release(
            acquisition,
            digest,
            records,
            now,
            snapshot_dir=output / "snapshot",
            output_dir=output / "d1-bundle",
            canonical_database=CANONICAL_DATABASE,
            hgab_bundle_dir=HGAB_BUNDLE_DIR,
            review_manifest_path=(
                review_manifest
                if review_manifest is not None and review_manifest.is_file()
                else None
            ),
        )
        report = {
            **_base_report(now),
            "source_state": "validated",
            "release_state": release["release_state"],
            "source_artifact_sha256": digest,
            "validated_facilities": release["facility_count"],
            "candidate_links": release["candidate_links"],
            "reviewed_cases": release["reviewed_cases"],
            "precision_bps": release["precision_bps"],
            "agreement_bps": release["agreement_bps"],
            "critical_failures": release["critical_failures"],
            "status_note": (
                "The official workbook passed source validation. "
                + (
                    "The measured review gate passed and the bundle is ready for publication."
                    if release["release_state"] == "ready_for_publication"
                    else "Candidate links remain unpublished until measured review passes."
                )
            ),
        }
        code = 0 if release["release_state"] != "gate_failed" else 2
    except AcquisitionError as exc:
        report, code = facility_failure_report(exc, now)
    except Exception as exc:
        report = _validation_failure_report(exc, now)
        code = 3
    _write_report(output, now, report)
    return report, code


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-manifest", type=Path, default=DEFAULT_REVIEW_MANIFEST)
    parser.add_argument("--reset-output", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = arguments()
    report, code = run_facility_monitor(
        options.output,
        review_manifest=options.review_manifest,
        reset_output=options.reset_output,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
