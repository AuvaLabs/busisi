import json
import sqlite3
from pathlib import Path

from engine.budget_watchdog.coa_bundle import build_coa_bundle


def _catalog(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checked_at": "2026-11-03T12:00:00+00:00",
                "catalogs": [
                    {
                        "catalog_id": "coa-aar-nga",
                        "title": "COA NGA Annual Audit Reports",
                        "source_url": "https://www.coa.gov.ph/reports/annual-audit-reports/aar-national-government-agencies/",
                        "checked_status": "reachable_by_index",
                        "evidence_note": "Official catalogue checked.",
                    }
                ],
                "reports": [
                    {
                        "report_id": "coa-report-1",
                        "title": "Reviewed audit report",
                        "report_type": "annual_audit_report",
                        "audited_entity": "Department of Public Works and Highways",
                        "fiscal_year": 2024,
                        "publication_date": "2025-06-01",
                        "source_url": "https://www.coa.gov.ph/wpfd_file/reviewed-audit-report/",
                        "landing_url": "https://www.coa.gov.ph/reports/",
                        "acquisition_status": "verified_archived",
                        "artifact_sha256": "a" * 64,
                        "byte_size": 1234,
                        "page_count": 50,
                        "scope_note": "Agency accounts and operations.",
                        "evidence_note": "Archived official report.",
                    }
                ],
                "project_coverage": [
                    {
                        "case_id": "case-1",
                        "contract_id": "24TEST",
                        "fiscal_year": 2024,
                        "status": "reviewed_observation_match",
                        "report_id": "coa-report-1",
                        "match_confidence": "exact",
                        "match_basis": ["contract_id"],
                        "page_start": 12,
                        "page_end": 13,
                        "observation_summary": "The report discusses this contract.",
                        "recommendation_summary": "The agency was directed to verify delivery.",
                        "management_response": "Management agreed to review the record.",
                        "implementation_status": "in_progress",
                        "review_note": "Contract identifier appears on the cited pages.",
                        "reviewed_at": "2026-11-03",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_builds_reconciled_coa_d1_bundle(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    result = build_coa_bundle(_catalog(tmp_path / "catalog.json"), output)

    assert result.report_count == 1
    assert result.checked_projects == 1
    assert result.project_matches == 1
    connection = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare"
            / "busisi"
            / "migrations"
            / "0012_coa_audit_evidence.sql"
        )
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.executescript((output / "coa-audit-evidence.sql").read_text(encoding="utf-8"))
        row = connection.execute(
            "SELECT status, match_confidence, report_id FROM coa_project_coverage"
        ).fetchone()
        assert row == ("reviewed_observation_match", "exact", "coa-report-1")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()
