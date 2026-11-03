import json
import sqlite3
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from engine.budget_watchdog.integrity_bundle import build_integrity_bundle


def _snapshot(path: Path) -> None:
    table = pa.Table.from_pylist(
        [
            {
                "contractId": "25A",
                "description": "Construction of public market",
                "category": "Buildings and Facilities",
                "status": "On-Going",
                "budget": 100_000.25,
                "progress": 100.0,
                "location": {"province": "Manila 1st DEO", "region": "NCR"},
                "contractor": "ACME BUILDERS (12345)",
                "startDate": date(2025, 1, 1),
                "completionDate": date(2025, 12, 1),
                "infraYear": "2025",
                "latitude": 14.5995,
                "longitude": 120.9842,
                "hasSatelliteImage": True,
            },
            {
                "contractId": "24B",
                "description": "Repair of provincial hospital",
                "category": "Buildings and Facilities",
                "status": "Completed",
                "budget": 200_000.50,
                "progress": 0.0,
                "location": {"province": "Quezon 1st DEO", "region": "Region IV-A"},
                "contractor": "ACME BUILDERS (12345)",
                "startDate": date(2024, 1, 1),
                "completionDate": date(2024, 12, 1),
                "infraYear": "2024",
                "latitude": None,
                "longitude": None,
                "hasSatelliteImage": False,
            },
            {
                "contractId": "23C",
                "description": "Excluded old record",
                "category": "Roads",
                "status": "Completed",
                "budget": 300_000.75,
                "progress": 100.0,
                "location": {"province": "Cebu 1st DEO", "region": "Region VII"},
                "contractor": "OLD BUILDERS (99999)",
                "startDate": date(2023, 1, 1),
                "completionDate": date(2023, 12, 1),
                "infraYear": "2023",
                "latitude": 10.3157,
                "longitude": 123.8854,
                "hasSatelliteImage": True,
            },
        ]
    )
    pq.write_table(table, path)


def _pcab_snapshot(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "page": "1",
                "total": 1,
                "records": 1,
                "rows": [
                    {
                        "id": "1",
                        "cell": [
                            "1",
                            "ACME BUILDERS",
                            "12345",
                            "A Person",
                            "AAA",
                            "2027-12-31",
                            "1",
                        ],
                    }
                ],
            }
        )
    )


def test_integrity_bundle_is_deterministic_and_verifies_generated_sql(tmp_path) -> None:
    snapshot = tmp_path / "dpwh.parquet"
    output = tmp_path / "bundle"
    pcab = tmp_path / "pcab.json"
    _snapshot(snapshot)
    _pcab_snapshot(pcab)

    options = {
        "fiscal_years": (2024, 2025),
        "chunk_rows": 2,
        "pcab_snapshot_path": pcab,
        "pcab_retrieved_on": date(2026, 11, 3),
        "minimum_concentration_projects": 1,
    }
    first = build_integrity_bundle(snapshot, output, **options)
    first_manifest = (output / "manifest.json").read_bytes()
    second = build_integrity_bundle(snapshot, output, **options)

    assert first.source_records == 2
    assert first.integrity_signals == 4
    assert first.contractors == 1
    assert first.concentrations == 11
    assert first.manifest_sha256 == second.manifest_sha256
    assert first_manifest == (output / "manifest.json").read_bytes()

    manifest = json.loads(first_manifest)
    assert manifest["fiscal_years"] == [2024, 2025]
    assert len(manifest["source_artifact_sha256"]) == 64

    connection = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare"
            / "busisi"
            / "migrations"
            / "0005_integrity.sql"
        )
        connection.executescript(migration.read_text())
        migration_0006 = migration.with_name("0006_contractor_verification.sql")
        connection.executescript(migration_0006.read_text())
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text())
        assert connection.execute("SELECT COUNT(*) FROM integrity_signal_items").fetchone()[0] == 4
        contractor = connection.execute(
            "SELECT project_count, total_budget_centavos FROM contractor_rankings"
        ).fetchone()
        assert contractor == (2, 30_000_075)
        verification = connection.execute(
            "SELECT pcab_status, pcab_name, pcab_gov_infra FROM contractor_rankings"
        ).fetchone()
        assert verification == ("current_regular", "ACME BUILDERS", 1)
        assert (
            connection.execute("SELECT COUNT(*) FROM contractor_concentrations").fetchone()[0] == 11
        )
    finally:
        connection.close()
