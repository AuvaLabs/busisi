"""Monitor the official PSA poverty workbook without publishing blocked data."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import AcquisitionError, SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.poverty_bundle import build_poverty_release_sql
from engine.budget_watchdog.poverty_estimates import (
    EXPECTED_POVERTY_RECORDS,
    PSA_POVERTY_SOURCE_URL,
    parse_poverty_workbook,
)
from engine.budget_watchdog.poverty_status_bundle import build_poverty_status_sql
from engine.budget_watchdog.source_resilience import (
    classify_source_failure,
    source_health_after_failure,
    source_health_after_success,
)
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "poverty-source-monitor"
POVERTY_RETRY_DELAYS = (timedelta(hours=6),)


def _base_report(now: datetime) -> dict[str, Any]:
    return {
        "checked_at": now.isoformat(),
        "source_url": PSA_POVERTY_SOURCE_URL,
        "http_status": None,
        "source_sha256": None,
        "expected_records": EXPECTED_POVERTY_RECORDS,
        "validated_records": 0,
    }


def poverty_failure_report(
    error: AcquisitionError,
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """Describe an inaccessible workbook without treating its response as data."""

    failure_kind = classify_source_failure(error.http_status, error.response_body)
    report = {
        **_base_report(now),
        **source_health_after_failure(
            previous,
            checked_at=now,
            failure_kind=failure_kind,
            response_body=error.response_body,
            retry_delays=POVERTY_RETRY_DELAYS,
        ),
        "http_status": error.http_status,
        "source_state": "blocked"
        if error.http_status in {401, 403, 429}
        else "acquisition_failure",
        "publication_state": "not_published",
        "status_note": (
            "PSA blocked the automatic download. No poverty estimates were published."
            if error.http_status in {401, 403, 429}
            else "The official PSA workbook could not be downloaded. No poverty estimates were published."
        ),
    }
    return report, 0 if error.http_status in {401, 403, 429} else 2


def _validation_failure_report(
    error: Exception,
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_base_report(now),
        **source_health_after_failure(
            previous,
            checked_at=now,
            failure_kind="validation_error",
            retry_delays=POVERTY_RETRY_DELAYS,
        ),
        "source_state": "validation_failure",
        "publication_state": "not_published",
        "status_note": (
            "The downloaded PSA workbook did not pass the required checks. "
            "No poverty estimates were published."
        ),
        "internal_error": type(error).__name__,
    }


def _load_previous(output: Path) -> dict[str, Any] | None:
    path = output / "latest.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_report(output: Path, now: datetime, report: dict[str, Any]) -> None:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    sql, digest = build_poverty_status_sql(report)
    report["status_sha256"] = digest
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (run_dir / "report.json").write_text(document, encoding="utf-8")
    (output / "latest.json").write_text(document, encoding="utf-8")
    (output / "public-status.sql").write_text(sql, encoding="utf-8")


def run_poverty_monitor(
    output: Path = DEFAULT_OUTPUT, *, reset_output: bool = False
) -> tuple[dict[str, Any], int]:
    """Download, archive and validate the registered official workbook."""

    previous = _load_previous(output)
    if reset_output:
        shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    path = urlparse(PSA_POVERTY_SOURCE_URL).path
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=2 * 1024 * 1024)
    try:
        acquisition = fetcher.fetch("psa-statistics", path, retrieved_at=now)
        archived = ArtifactArchive(output / "archive").store(acquisition)
        records = parse_poverty_workbook(
            acquisition.payload, acquisition.source_url, archived.sha256
        )
        report = {
            **_base_report(now),
            **source_health_after_success(now, response_body=acquisition.payload),
            "source_state": "validated",
            "publication_state": "ready_for_review",
            "source_sha256": archived.sha256,
            "validated_records": len(records),
            "status_note": (
                "The official PSA workbook passed the source, identity, uncertainty, "
                "and published-total checks. Publication still requires a reviewed release."
            ),
        }
        release_sql, release_sha256 = build_poverty_release_sql(records, report)
        (output / "review-release.sql").write_text(release_sql, encoding="utf-8")
        report["review_release_sha256"] = release_sha256
        code = 0
    except AcquisitionError as exc:
        report, code = poverty_failure_report(exc, now, previous)
    except Exception as exc:
        report = _validation_failure_report(exc, now, previous)
        code = 3
    _write_report(output, now, report)
    return report, code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reset-output", action="store_true")
    options = parser.parse_args()
    report, code = run_poverty_monitor(options.output, reset_output=options.reset_output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
