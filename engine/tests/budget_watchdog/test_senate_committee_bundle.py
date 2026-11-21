import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.senate_committee_bundle import build_senate_committee_bundle


def _watch_fixture(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "release_id": "fy2027-cr131",
        "fiscal_year": 2027,
        "report_number": "131",
        "related_bill": "HB 10858",
        "state": "awaiting_official_document",
        "checked_at": "2026-11-21T12:00:00+00:00",
        "official_document": None,
        "controls": [],
        "items": [],
        "public_note": "The official report and project schedules are not in Busisi yet.",
    }
    fixture = path / "release.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    return fixture


def test_builds_watch_status_without_publishing_zero_amounts(tmp_path) -> None:
    output = tmp_path / "bundle"
    result = build_senate_committee_bundle(_watch_fixture(tmp_path), output)

    assert result.state == "awaiting_official_document"
    assert result.item_count == 0
    migration = (
        Path(__file__).resolve().parents[3]
        / "cloudflare"
        / "busisi"
        / "migrations"
        / "0034_senate_committee_changes.sql"
    )
    database = sqlite3.connect(":memory:")
    try:
        database.executescript(migration.read_text(encoding="utf-8"))
        database.executescript((output / "senate-committee.sql").read_text(encoding="utf-8"))
        row = database.execute(
            "SELECT state, item_count, total_change_centavos FROM senate_committee_releases"
        ).fetchone()
        assert row == ("awaiting_official_document", 0, None)
        assert database.execute("SELECT COUNT(*) FROM senate_committee_changes").fetchone() == (0,)
    finally:
        database.close()
