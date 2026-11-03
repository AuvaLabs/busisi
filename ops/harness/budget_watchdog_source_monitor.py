"""Monitor public source revisions and catalogues without auto-publishing drift."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.districts import acquire_district_snapshot
from engine.budget_watchdog.pcab import acquire_pcab_regular_licenses
from engine.budget_watchdog.source_monitor import (
    SourceMonitorError,
    compare_observations,
    parse_dbm_release_catalog,
    parse_huggingface_metadata,
)
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "ops" / "harness" / "fixtures" / "source_monitor_baseline.json"
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "source-monitor"
DATASETS = {
    "gaa": ("bettergov-gaa-snapshot", "bettergovph/gaa"),
    "delivery": (
        "bettergov-dpwh-snapshot",
        "bettergovph/dpwh-transparency-data",
    ),
    "philgeps": ("bettergov-philgeps-snapshot", "bettergovph/philgeps-data"),
}
DBM_CATALOG_PATH = "/index.php/status-of-allotment-releases"
MONITORED_YEAR = 2026
NEXT_MONITORED_YEAR = 2027
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_CATALOG_BYTES = 2 * 1024 * 1024
BASELINE_SCHEMA_VERSION = 2
KNOWN_DISCOVERY_LIMITS = [
    {
        "source": "Commission on Audit report catalogues",
        "status": "official_source_blocks_unattended_acquisition",
        "effect": (
            "New COA reports require separate discovery and cannot be "
            "auto-published from this monitor."
        ),
    }
]


def _stable_observation(observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "datasets": {
            key: {"revision": value["revision"]} for key, value in observed["datasets"].items()
        },
        "dbm_releases": observed["dbm_releases"],
        "dbm_next_releases": observed["dbm_next_releases"],
        "districts": {
            "revision": observed["districts"]["revision"],
            "total": observed["districts"]["total"],
        },
        "pcab": {
            "sha256": observed["pcab"]["sha256"],
            "records": observed["pcab"]["records"],
        },
        "known_discovery_limits": KNOWN_DISCOVERY_LIMITS,
    }


def _observe(
    *, now: datetime, archive: ArtifactArchive
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    registry = default_source_registry()
    metadata_fetcher = SourceFetcher(registry, max_response_bytes=MAX_METADATA_BYTES)
    artifacts: list[dict[str, Any]] = []
    datasets: dict[str, Any] = {}
    for key, (source_id, dataset_id) in DATASETS.items():
        acquisition = metadata_fetcher.fetch(
            source_id, f"/api/datasets/{dataset_id}", retrieved_at=now
        )
        artifact = archive.store(acquisition)
        datasets[key] = parse_huggingface_metadata(acquisition.payload, dataset_id)
        artifacts.append(
            {
                "source": key,
                "sha256": artifact.sha256,
                "byte_size": artifact.byte_size,
            }
        )

    catalogue = SourceFetcher(registry, max_response_bytes=MAX_CATALOG_BYTES).fetch(
        "dbm-saaodb", DBM_CATALOG_PATH, retrieved_at=now
    )
    catalogue_artifact = archive.store(catalogue)
    releases = parse_dbm_release_catalog(catalogue.payload, MONITORED_YEAR)
    next_releases = parse_dbm_release_catalog(
        catalogue.payload, NEXT_MONITORED_YEAR, allow_empty=True
    )
    artifacts.append(
        {
            "source": "dbm_release_catalogue",
            "sha256": catalogue_artifact.sha256,
            "byte_size": catalogue_artifact.byte_size,
        }
    )

    district_artifacts, districts = acquire_district_snapshot(
        metadata_fetcher, archive, retrieved_at=now
    )
    artifacts.extend(
        {
            "source": f"districts:{index}",
            "sha256": artifact.sha256,
            "byte_size": artifact.byte_size,
        }
        for index, artifact in enumerate(district_artifacts)
    )

    pcab_artifact, pcab = acquire_pcab_regular_licenses(
        SourceFetcher(registry), archive, retrieved_at=now
    )
    artifacts.append(
        {
            "source": "pcab",
            "sha256": pcab_artifact.sha256,
            "byte_size": pcab_artifact.byte_size,
        }
    )
    observed = {
        "datasets": datasets,
        "dbm_releases": list(releases),
        "dbm_next_releases": list(next_releases),
        "districts": {
            "revision": districts.source_commit,
            "built_at": districts.source_built_at,
            "total": districts.district_count,
            "offices": districts.office_count,
        },
        "pcab": {
            "sha256": pcab.source_sha256,
            "records": pcab.record_count,
            "retrieved_on": pcab.retrieved_on.isoformat(),
        },
    }
    return observed, artifacts


def _write_report(output: Path, now: datetime, report: dict[str, Any]) -> Path:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = output / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path.write_text(document, encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(document, encoding="utf-8")
    return report_path


def run_monitor(
    baseline_path: Path,
    output: Path,
    *,
    write_baseline: bool = False,
) -> tuple[dict[str, Any], int]:
    now = datetime.now(UTC)
    try:
        observed, artifacts = _observe(now=now, archive=ArtifactArchive(output / "archive"))
        stable = _stable_observation(observed)
        if write_baseline:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(stable, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if not baseline_path.is_file():
            raise SourceMonitorError("source monitor baseline does not exist")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        differences = compare_observations(baseline, observed)
        report = {
            "passed": not differences,
            "status": "drift_detected" if differences else "unchanged",
            "checked_at": now.isoformat(),
            "differences": list(differences),
            "observed": observed,
            "artifacts": artifacts,
            "known_discovery_limits": stable["known_discovery_limits"],
        }
        code = 2 if differences else 0
    except Exception as exc:
        report = {
            "passed": False,
            "status": "acquisition_or_validation_failure",
            "checked_at": now.isoformat(),
            "error": str(exc),
            "differences": ["A monitored source could not be acquired or validated."],
            "observed": {},
            "known_discovery_limits": KNOWN_DISCOVERY_LIMITS,
        }
        code = 3
    report["report_path"] = str(_write_report(output, now, report))
    return report, code


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--reset-output", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = arguments()
    if options.reset_output:
        shutil.rmtree(options.output, ignore_errors=True)
    report, code = run_monitor(
        options.baseline, options.output, write_baseline=options.write_baseline
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
