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


def _district_snapshots(first: Path, second: Path) -> None:
    def district(district_id: str, label: str, office: str, tier: str, rep: str) -> dict:
        jurisdiction, district_label = label.split(",", maxsplit=1)
        return {
            "id": district_id,
            "label": label,
            "jurisdiction": jurisdiction,
            "district_label": district_label.strip(),
            "region": "NCR",
            "representative": {
                "name": rep,
                "seat": label,
                "status": "resolved",
                "status_note": None,
                "profile_url": "https://www.congress.gov.ph/house-members/view/A001",
            },
            "offices": [{"name": office, "tier": tier}],
        }

    pages = (
        {
            "meta": {
                "source_commit": "c" * 40,
                "built_at": "2026-10-26T08:46:14.383Z",
                "offset": 0,
                "returned": 2,
                "total": 3,
            },
            "data": {
                "districts": [
                    district(
                        "leg:manila:1st",
                        "Manila, 1st District",
                        "Manila 1st DEO",
                        "A",
                        "Rep One",
                    ),
                    district(
                        "leg:quezon:1st",
                        "Quezon, 1st District",
                        "Quezon 1st DEO",
                        "B",
                        "Rep Two",
                    ),
                ]
            },
        },
        {
            "meta": {
                "source_commit": "c" * 40,
                "built_at": "2026-10-26T08:46:14.383Z",
                "offset": 2,
                "returned": 1,
                "total": 3,
            },
            "data": {
                "districts": [
                    district(
                        "leg:quezon:2nd",
                        "Quezon, 2nd District",
                        "Quezon 1st DEO",
                        "B",
                        "Rep Three",
                    )
                ]
            },
        },
    )
    first.write_text(json.dumps(pages[0]))
    second.write_text(json.dumps(pages[1]))


def _assert_contractor_associations(connection: sqlite3.Connection) -> None:
    associations = connection.execute(
        "SELECT contractor_key, contract_id, party_position, party_count, relationship "
        "FROM contractor_project_associations ORDER BY contract_id"
    ).fetchall()
    assert associations == [
        ("pcab:12345", "24B", 1, 1, "sole"),
        ("pcab:12345", "25A", 1, 1, "sole"),
    ]


def _apply_integrity_migrations(connection: sqlite3.Connection, migration: Path) -> None:
    for name in (
        "0005_integrity.sql",
        "0006_contractor_verification.sql",
        "0007_district_attribution.sql",
        "0011_delivery_details.sql",
        "0024_contractor_project_associations.sql",
    ):
        connection.executescript(migration.with_name(name).read_text())


def test_integrity_bundle_is_deterministic_and_verifies_generated_sql(tmp_path) -> None:
    snapshot = tmp_path / "dpwh.parquet"
    output = tmp_path / "bundle"
    pcab = tmp_path / "pcab.json"
    districts_one = tmp_path / "districts-0.json"
    districts_two = tmp_path / "districts-2.json"
    _snapshot(snapshot)
    _pcab_snapshot(pcab)
    _district_snapshots(districts_one, districts_two)

    options = {
        "fiscal_years": (2024, 2025),
        "chunk_rows": 2,
        "pcab_snapshot_path": pcab,
        "pcab_retrieved_on": date(2026, 11, 3),
        "minimum_concentration_projects": 1,
        "district_snapshot_paths": (districts_one, districts_two),
        "district_retrieved_on": date(2026, 11, 3),
    }
    first = build_integrity_bundle(snapshot, output, **options)
    first_manifest = (output / "manifest.json").read_bytes()
    second = build_integrity_bundle(snapshot, output, **options)

    assert first.source_records == 2
    assert first.integrity_signals == 4
    assert first.contractors == 1
    assert first.contractor_associations == 2
    assert first.concentrations == 11
    assert first.district_offices == 2
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
        _apply_integrity_migrations(connection, migration)
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text())
        assert connection.execute("SELECT COUNT(*) FROM integrity_signal_items").fetchone()[0] == 4
        details = connection.execute(
            "SELECT contract_id, category, status, progress, contractor_name, start_date, "
            "completion_date, latitude, longitude, has_satellite_image "
            "FROM delivery_project_details ORDER BY contract_id"
        ).fetchall()
        assert details == [
            (
                "24B",
                "Buildings and Facilities",
                "Completed",
                "0.0",
                "ACME BUILDERS (12345)",
                "2024-01-01",
                "2024-12-01",
                "",
                "",
                0,
            ),
            (
                "25A",
                "Buildings and Facilities",
                "On-Going",
                "100.0",
                "ACME BUILDERS (12345)",
                "2025-01-01",
                "2025-12-01",
                "14.5995",
                "120.9842",
                1,
            ),
        ]
        parties = connection.execute(
            "SELECT contractor_parties_json FROM delivery_project_details WHERE contract_id = '25A'"
        ).fetchone()[0]
        assert json.loads(parties) == [
            {"contractor_key": "pcab:12345", "contractor_name": "ACME BUILDERS", "pcab_id": "12345"}
        ]
        contractor = connection.execute(
            "SELECT project_count, total_budget_centavos FROM contractor_rankings"
        ).fetchone()
        assert contractor == (2, 30_000_075)
        _assert_contractor_associations(connection)
        verification = connection.execute(
            "SELECT pcab_status, pcab_name, pcab_gov_infra FROM contractor_rankings"
        ).fetchone()
        assert verification == ("current_regular", "ACME BUILDERS", 1)
        assert (
            connection.execute("SELECT COUNT(*) FROM contractor_concentrations").fetchone()[0] == 11
        )
        district_rows = connection.execute(
            "SELECT office_name, classification, district_count "
            "FROM district_office_attributions ORDER BY office_name"
        ).fetchall()
        assert district_rows == [
            ("Manila 1st DEO", "single_district", 1),
            ("Quezon 1st DEO", "shared_office", 2),
        ]
    finally:
        connection.close()
