import csv
import sqlite3

import pytest

from engine.budget_watchdog.quarantine_review import build_quarantine_review
from engine.tests.budget_watchdog.test_acquisition_detail_bundle import _snapshot


def test_builds_internal_quarantine_review_workspace(tmp_path) -> None:
    output = tmp_path / "review"
    result = build_quarantine_review(_snapshot(tmp_path), output)

    assert result.case_count == 1
    assert result.candidate_count == 2
    connection = sqlite3.connect(output / "quarantine-review.sqlite3")
    try:
        case = connection.execute(
            "SELECT source_row_id, review_status, reason FROM review_cases"
        ).fetchone()
        candidates = connection.execute(
            "SELECT contract_id FROM review_candidates ORDER BY contract_id"
        ).fetchall()
        decisions = connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
    finally:
        connection.close()
    assert case[1:] == ("unresolved", "conflicting_exact_identifiers")
    assert candidates == [("24AA0001",), ("25CC0003",)]
    assert decisions == 0

    with (output / "quarantine-review.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["candidate_contract_ids"] == "24AA0001|25CC0003"

    document = (output / "index.html").read_text()
    assert "Internal quarantine review" in document
    assert "24AA0001" in document
    assert "25CC0003" in document
    assert "Unresolved" in document
    assert "not a finding of wrongdoing" in document


def test_review_ledger_rejects_unsupported_resolution(tmp_path) -> None:
    output = tmp_path / "review"
    build_quarantine_review(_snapshot(tmp_path), output)
    connection = sqlite3.connect(output / "quarantine-review.sqlite3")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO review_decisions (
                    source_row_id, resolution, resolved_contract_id, evidence_url,
                    evidence_sha256, reviewer_note, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "award-conflict",
                    "confirmed_reference_id",
                    "24ZZ9999",
                    "https://example.gov.ph/evidence",
                    "a" * 64,
                    "Unsupported candidate must fail.",
                    "2026-11-03T12:00:00+04:00",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO review_decisions (
                    source_row_id, resolution, resolved_contract_id, evidence_url,
                    evidence_sha256, reviewer_note, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "award-conflict",
                    "retain_quarantine",
                    None,
                    "http://example.test/evidence",
                    "a" * 64,
                    "Non-HTTPS evidence must fail.",
                    "2026-11-03T12:00:00+04:00",
                ),
            )
    finally:
        connection.close()
