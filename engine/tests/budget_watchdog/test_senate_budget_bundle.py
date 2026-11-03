import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.senate_budget_bundle import build_senate_budget_bundle


def _catalog(tmp_path, *, coverage_count: int = 1):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fiscal_year": 2027,
                "source": {
                    "source_id": "senate-budget-portal",
                    "url": "https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027",
                    "retrieved_at": "2026-11-03T12:00:00+00:00",
                    "acquisition_status": "direct_blocked_secondary_discovery",
                    "discovery_source_id": "jina-reader",
                },
                "documents": [
                    {
                        "document_id": "senate-portal:385",
                        "source_record_id": "385",
                        "title": "HB 10858 FOR 3RD READING VOL I-B",
                        "stage": "house_gab",
                        "stage_label": "House bill, third reading",
                        "publisher": "Senate Budget Transparency Portal",
                        "volume": "I-B",
                        "publication_date": "2026-10-13",
                        "source_url": "https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027",
                        "viewer_url": "https://budget-transparency-portal.senate.gov.ph/file_viewer?id=385&type=Documents",
                        "acquisition_status": "verified_archived",
                        "artifact_sha256": "4" * 64,
                        "byte_size": 15663076,
                        "mirror_url": "https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf",
                        "evidence_note": "Archived mirror fingerprint matches the source analysis.",
                    }
                ],
                "stage_coverage": [
                    {"stage": "nep", "status": "available_elsewhere", "document_count": 0},
                    {"stage": "house_gab", "status": "partial", "document_count": coverage_count},
                    {"stage": "senate_committee", "status": "unavailable", "document_count": 0},
                    {"stage": "senate_amendment", "status": "unavailable", "document_count": 0},
                    {"stage": "bicam", "status": "unavailable", "document_count": 0},
                    {"stage": "gaa", "status": "unavailable", "document_count": 0},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_builds_verified_budget_cycle_bundle(tmp_path) -> None:
    output = tmp_path / "bundle"

    result = build_senate_budget_bundle(_catalog(tmp_path), output)

    assert result.document_count == 1
    assert result.verified_document_count == 1
    assert len(result.catalog_sha256) == 64
    database = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare"
            / "busisi"
            / "migrations"
            / "0010_budget_cycle.sql"
        )
        database.executescript(migration.read_text(encoding="utf-8"))
        database.executescript((output / "budget-cycle.sql").read_text(encoding="utf-8"))
        row = database.execute(
            "SELECT stage, acquisition_status, artifact_sha256 FROM budget_cycle_documents"
        ).fetchone()
        assert row == ("house_gab", "verified_archived", "4" * 64)
        assert database.execute(
            "SELECT status FROM budget_cycle_stages WHERE stage = 'gaa'"
        ).fetchone() == ("unavailable",)
    finally:
        database.close()


def test_bundle_rejects_unreconciled_catalog_without_replacing_output(tmp_path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("stable", encoding="utf-8")

    with pytest.raises(ValueError, match="does not reconcile"):
        build_senate_budget_bundle(_catalog(tmp_path, coverage_count=2), output)

    assert marker.read_text(encoding="utf-8") == "stable"
