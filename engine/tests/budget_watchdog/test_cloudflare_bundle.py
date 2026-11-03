import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.cloudflare_bundle import build_cloudflare_bundle

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
MIGRATION_PATH = ROOT / "cloudflare" / "busisi" / "migrations" / "0001_publication.sql"
REVIEWED_RECORDS = 6
STATIC_PAGES = 9
SHA256_HEX_LENGTH = 64
CATMON_RECORDS = 5


def test_cloudflare_bundle_contains_static_site_seed_and_manifest(tmp_path) -> None:
    result = build_cloudflare_bundle(GOLDEN_PATH, MIGRATION_PATH, tmp_path)

    assert result.reviewed_records == REVIEWED_RECORDS
    assert result.static_pages == STATIC_PAGES
    assert (tmp_path / "public" / "watchlist" / "index.html").is_file()
    assert (tmp_path / "reviewed-seed.sql").is_file()
    manifest = json.loads((tmp_path / "publication-manifest.json").read_text())
    assert manifest["reviewed_cases"] == REVIEWED_RECORDS
    assert manifest["release_ready"] is False
    assert len(manifest["golden_sha256"]) == SHA256_HEX_LENGTH


def test_cloudflare_seed_applies_to_schema_and_populates_fts(tmp_path) -> None:
    build_cloudflare_bundle(GOLDEN_PATH, MIGRATION_PATH, tmp_path)
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text())
        connection.executescript((tmp_path / "reviewed-seed.sql").read_text())
        records = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        matches = connection.execute(
            "SELECT COUNT(*) FROM project_search WHERE project_search MATCH ?",
            ('"catmon"*',),
        ).fetchone()[0]
    finally:
        connection.close()

    assert records == REVIEWED_RECORDS
    assert matches == CATMON_RECORDS


def test_cloudflare_seed_is_deterministic(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_cloudflare_bundle(GOLDEN_PATH, MIGRATION_PATH, first)
    build_cloudflare_bundle(GOLDEN_PATH, MIGRATION_PATH, second)

    assert (first / "reviewed-seed.sql").read_bytes() == (second / "reviewed-seed.sql").read_bytes()
    assert (first / "publication-manifest.json").read_bytes() == (
        second / "publication-manifest.json"
    ).read_bytes()
