import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.procurement_bundle import build_procurement_bundle


def _catalog(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "checked_at": "2026-11-03T15:00:00+04:00",
        "sources": [
            {
                "source_id": "pmr-2024",
                "title": "DPWH PMR",
                "publisher": "DPWH Cebu 5th DEO",
                "document_type": "procurement_monitoring_report",
                "fiscal_year": 2024,
                "reporting_cutoff": "2024-12-31",
                "source_url": "https://www.dpwh.gov.ph/pmr.pdf",
                "acquisition_status": "discovered",
                "artifact_sha256": None,
                "byte_size": None,
                "page_count": None,
                "evidence_note": "Official PDF row discovered.",
            }
        ],
        "records": [
            {
                "evidence_id": "pmr-24test",
                "case_id": "case-1",
                "contract_id": "24TEST",
                "fiscal_year": 2024,
                "source_id": "pmr-2024",
                "evidence_type": "monitoring_report",
                "match_basis": "exact_contract_id",
                "project_title": "Test public project",
                "procuring_entity": "DPWH Test DEO",
                "procurement_mode": "Competitive Bidding",
                "procurement_status": "Completed",
                "page_number": 5,
                "reference_number": None,
                "abc_centavos": 495000000,
                "contract_cost_centavos": 493416373,
                "savings_centavos": 1583627,
                "observers": ["COA", "PICE"],
                "events": [
                    {"stage": "advertisement", "event_date": "2024-05-16", "date_kind": "actual"},
                    {"stage": "notice_of_award", "event_date": "2024-06-18", "date_kind": "actual"},
                ],
                "reviewed_at": "2026-11-03",
                "boundary_note": "Agency-reported PMR row.",
            }
        ],
        "coverage": [
            {
                "case_id": "case-1",
                "contract_id": "24TEST",
                "fiscal_year": 2024,
                "status": "exact_evidence",
                "record_count": 1,
                "review_note": "Exact contract ID located.",
                "reviewed_at": "2026-11-03",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_builds_verified_procurement_d1_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    result = build_procurement_bundle(_catalog(tmp_path / "catalog.json"), output)

    assert result.source_count == 1
    assert result.record_count == 1
    assert result.checked_projects == 1
    connection = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare"
            / "busisi"
            / "migrations"
            / "0013_procurement_evidence.sql"
        )
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.executescript((output / "procurement-evidence.sql").read_text(encoding="utf-8"))
        row = connection.execute(
            "SELECT contract_id, abc_centavos, savings_centavos FROM procurement_records"
        ).fetchone()
        assert row == ("24TEST", 495000000, 1583627)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()
