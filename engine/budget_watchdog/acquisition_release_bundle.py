"""Build the reconciled acquisition-universe D1 summary bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.acquisition_release import (
    MATCH_STATES,
    load_acquisition_release,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0016_acquisition_universe.sql"
)


@dataclass(frozen=True, slots=True)
class AcquisitionReleaseBundleResult:
    output_dir: Path
    contract_count: int
    lifecycle_task_count: int
    catalog_sha256: str
    bundle_sha256: str


def _text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _metadata(catalog: dict[str, Any]) -> dict[str, str]:
    source = catalog["source"]
    summary = catalog["summary"]
    return {
        "schema_version": str(catalog["schema_version"]),
        "checked_on": catalog["checked_on"],
        **{
            f"source:{key}": str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in source.items()
        },
        **{key: str(value) for key, value in summary.items() if key != "match_state_counts"},
        **{f"state:{key}": str(value) for key, value in summary["match_state_counts"].items()},
        **{f"queue:{key}": str(value) for key, value in catalog["queue_status_counts"].items()},
    }


def _breakdown_statement(dimension: str, item: dict[str, Any]) -> str:
    counts = item["state_counts"]
    values = [
        _text(dimension),
        _text(str(item["value"])),
        str(item["total_contracts"]),
        *(str(counts[state]) for state in MATCH_STATES),
    ]
    return f"INSERT INTO acquisition_universe_breakdowns VALUES ({', '.join(values)});"  # noqa: S608


def _render(catalog: dict[str, Any]) -> str:
    lines = [
        "DELETE FROM acquisition_universe_breakdowns;",
        "DELETE FROM acquisition_universe_metadata;",
        *(
            f"INSERT INTO acquisition_universe_metadata VALUES ({_text(key)}, {_text(value)});"  # noqa: S608
            for key, value in sorted(_metadata(catalog).items())
        ),
    ]
    state_counts = catalog["summary"]["match_state_counts"]
    for state in MATCH_STATES:
        item = {
            "value": state,
            "total_contracts": state_counts.get(state, 0),
            "state_counts": {
                key: state_counts.get(state, 0) if key == state else 0 for key in MATCH_STATES
            },
        }
        lines.append(_breakdown_statement("match_state", item))
    for dimension, key in (("fiscal_year", "year_breakdowns"), ("category", "category_breakdowns")):
        lines.extend(_breakdown_statement(dimension, item) for item in catalog[key])
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(sql)
        total = connection.execute(
            "SELECT SUM(total_contracts) FROM acquisition_universe_breakdowns "
            "WHERE dimension = 'match_state'"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if total != expected or integrity != "ok":
        raise ValueError("acquisition universe bundle verification failed")


def build_acquisition_release_bundle(
    catalog_path: Path, output_dir: Path
) -> AcquisitionReleaseBundleResult:
    payload = catalog_path.read_bytes()
    catalog = load_acquisition_release(payload)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render(catalog)
    expected = catalog["summary"]["contract_count"]
    _verify(sql, expected)
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle = building / "acquisition-universe.sql"
    bundle.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_sha256": bundle_sha256,
                "catalog_sha256": catalog_sha256,
                "contract_count": expected,
                "lifecycle_task_count": catalog["summary"]["lifecycle_task_count"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return AcquisitionReleaseBundleResult(
        output_dir,
        expected,
        catalog["summary"]["lifecycle_task_count"],
        catalog_sha256,
        bundle_sha256,
    )
