import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.identity import BudgetProject, DeliveryProject
from engine.budget_watchdog.public_data_bundle import build_public_data_bundle
from engine.budget_watchdog.storage import CanonicalStore

BUDGET_SHA = "a" * 64
DELIVERY_SHA = "b" * 64
EXPECTED_SOURCE_RECORDS = 2
EXPECTED_CHUNKS = 6


def _canonical_database(path) -> None:
    with CanonicalStore(path) as store:
        store.store_budget_projects(
            (
                BudgetProject("18-001|pump", 2025, "Pumping station", 400_000, "Manila"),
                BudgetProject("18-001|road", 2024, "Provincial road", 100_000, "Cebu"),
            ),
            BUDGET_SHA,
        )
        store.store_delivery_projects(
            (
                DeliveryProject("25A", 2025, "Pumping station", 380_000, "Manila", "GAA"),
                DeliveryProject("26B", 2026, "Health center", 0, "Cebu", "GAA"),
            ),
            DELIVERY_SHA,
        )


def _candidate_file(path) -> None:
    candidate = {
        "fiscal_year": 2025,
        "budget_line_id": "18-001|pump",
        "contract_id": "25A",
        "confidence": "high",
        "score": 90,
        "signals": ["year_match", "strong_title_match"],
        "budget_description": "Pumping station",
        "delivery_description": "Pumping station",
        "budget_amount_centavos": 400_000,
        "delivery_budget_centavos": 380_000,
        "budget_evidence_url": "https://budget.example/pump",
        "delivery_evidence_url": "https://dpwh.example/25A",
    }
    path.write_text(json.dumps({"count": 1, "candidates": [candidate]}))


def test_public_data_bundle_writes_verified_deterministic_chunks(tmp_path) -> None:
    database = tmp_path / "canonical.sqlite3"
    candidates = tmp_path / "candidates.json"
    output = tmp_path / "bundle"
    _canonical_database(database)
    _candidate_file(candidates)

    result = build_public_data_bundle(database, candidates, output, chunk_rows=1)

    assert result.budget_records == EXPECTED_SOURCE_RECORDS
    assert result.delivery_records == EXPECTED_SOURCE_RECORDS
    assert result.candidate_links == 1
    assert result.sql_chunks == EXPECTED_CHUNKS
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["budget_artifact_sha256"] == BUDGET_SHA
    assert manifest["delivery_artifact_sha256"] == DELIVERY_SHA

    connection = sqlite3.connect(":memory:")
    try:
        project_root = Path(__file__).resolve().parents[3]
        migration_root = project_root / "cloudflare" / "busisi" / "migrations"
        connection.executescript((migration_root / "0002_public_explorer.sql").read_text())
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text())
        assert (
            connection.execute("SELECT COUNT(*) FROM budget_items").fetchone()[0]
            == EXPECTED_SOURCE_RECORDS
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM delivery_items").fetchone()[0]
            == EXPECTED_SOURCE_RECORDS
        )
        assert connection.execute("SELECT COUNT(*) FROM candidate_links").fetchone()[0] == 1
    finally:
        connection.close()
