import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from engine.budget_watchdog.acquisition_detail_bundle import build_acquisition_detail_bundle
from engine.budget_watchdog.acquisition_universe import build_acquisition_universe
from engine.tests.budget_watchdog.test_acquisition_universe import _awards, _delivery


def _snapshot(tmp_path: Path):
    delivery = tmp_path / "delivery.parquet"
    awards = tmp_path / "awards.parquet"
    _delivery(delivery)
    _awards(awards)
    return build_acquisition_universe(
        delivery,
        awards,
        fiscal_years=(2024, 2025),
        delivery_sha256="d" * 64,
        award_sha256="a" * 64,
        award_revision="b" * 40,
        checked_on=date(2026, 11, 3),
    )


def test_builds_reconciled_contract_detail_chunks(tmp_path) -> None:
    output = tmp_path / "bundle"
    result = build_acquisition_detail_bundle(_snapshot(tmp_path), output, chunk_rows=2)

    assert result.contract_count == 3
    assert result.match_count == 3
    assert result.quarantine_count == 1
    assert result.quarantine_candidate_count == 2
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["contract_count"] == 3
    assert len(manifest["chunk_sha256"]) == result.sql_chunks

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            Path("cloudflare/busisi/migrations/0018_contract_acquisition_detail.sql").read_text()
        )
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text())
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "contract_acquisition_details",
                "contract_award_matches",
                "contract_quarantine_rows",
                "contract_quarantine_candidates",
            )
        )
        conflict = connection.execute(
            "SELECT reference_id, contract_no, award_title FROM contract_quarantine_rows"
        ).fetchone()
    finally:
        connection.close()
    assert counts == (3, 3, 1, 2)
    assert conflict == ("24AA0001", "24AA0001", "25CC0003")


def test_detail_bundle_validates_chunk_size(tmp_path) -> None:
    with pytest.raises(ValueError, match="chunk_rows"):
        build_acquisition_detail_bundle(_snapshot(tmp_path), tmp_path / "bundle", chunk_rows=0)
