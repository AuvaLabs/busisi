from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.source_status_bundle import build_source_status_sql

MIGRATION = Path("cloudflare/busisi/migrations/0023_source_monitor_status.sql")


def _report() -> dict[str, object]:
    return {
        "checked_at": "2026-11-04T01:00:00+00:00",
        "status": "drift_detected",
        "differences": ["pcab: records changed"],
        "known_discovery_limits": [
            {
                "source": "Commission on Audit report catalogues",
                "effect": "Official source blocks unattended acquisition.",
            }
        ],
        "observed": {"pcab": {"records": 18853}},
    }


def test_builds_self_contained_source_status_upsert() -> None:
    sql, digest = build_source_status_sql(_report())
    database = sqlite3.connect(":memory:")
    database.executescript(MIGRATION.read_text())
    database.executescript(sql)
    row = database.execute(
        "SELECT status, differences_json, observations_sha256 FROM source_monitor_status"
    ).fetchone()

    assert row[0] == "drift_detected"
    assert json.loads(row[1]) == ["pcab: records changed"]
    assert row[2] == digest
    assert len(digest) == 64


def test_rejects_untrusted_source_status_shapes() -> None:
    for update in (
        {"status": "passed"},
        {"checked_at": "today"},
        {"differences": [1]},
        {"known_discovery_limits": [{"source": "COA"}]},
        {"observed": []},
    ):
        report = {**_report(), **update}
        with pytest.raises(ValueError, match="source monitor"):
            build_source_status_sql(report)
