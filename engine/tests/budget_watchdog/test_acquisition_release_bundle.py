import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.acquisition_release_bundle import build_acquisition_release_bundle
from engine.tests.budget_watchdog.test_acquisition_release import _release


def test_builds_verified_acquisition_release_bundle(tmp_path: Path) -> None:
    release, _ = _release(tmp_path)
    catalog = tmp_path / "release.json"
    catalog.write_text(json.dumps(release) + "\n")

    result = build_acquisition_release_bundle(catalog, tmp_path / "bundle")

    assert result.contract_count == 3
    assert result.lifecycle_task_count == 27
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            Path("cloudflare/busisi/migrations/0016_acquisition_universe.sql").read_text()
        )
        connection.executescript((result.output_dir / "acquisition-universe.sql").read_text())
        states = dict(connection.execute(
            "SELECT value, total_contracts FROM acquisition_universe_breakdowns "
            "WHERE dimension = 'match_state' AND total_contracts > 0"
        ))
    finally:
        connection.close()

    assert states == {"conflict_review": 2, "multiple_exact_rows": 1}
