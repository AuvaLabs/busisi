"""Write review status receipts and export confirmed project links."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from engine.budget_watchdog.golden import load_golden_cases
from engine.budget_watchdog.review_expansion import evaluate_review_workspace


def write_review_status(database_path: Path, output_path: Path) -> Path:
    status = evaluate_review_workspace(database_path)
    document = asdict(status)
    document["reasons"] = list(status.reasons)
    building = output_path.with_name(f".{output_path.name}.building")
    building.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    building.replace(output_path)
    return output_path


def _confirmed_rows(database_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """
            SELECT c.*, MAX(d.reviewed_at) AS last_reviewed_at
            FROM review_cases c
            JOIN review_decisions d ON d.case_id = c.case_id
            GROUP BY c.case_id
            HAVING COUNT(*) = 2
               AND MIN(d.decision) = 'confirm'
               AND MAX(d.decision) = 'confirm'
            ORDER BY c.case_id
            """
        ).fetchall()
    finally:
        connection.close()


def _golden_case(row: sqlite3.Row) -> dict[str, object]:
    return {
        "case_id": row["case_id"],
        "evidence_urls": [row["budget_source_url"], row["delivery_source_url"]],
        "budget": {
            "budget_line_id": row["budget_line_id"],
            "fiscal_year": row["fiscal_year"],
            "description": row["budget_description"],
            "amount_centavos": row["budget_amount_centavos"],
            "location": row["budget_location"],
        },
        "candidates": [
            {
                "contract_id": row["contract_id"],
                "fiscal_year": row["fiscal_year"],
                "description": row["delivery_description"],
                "budget_centavos": row["delivery_budget_centavos"],
                "location": row["delivery_location"],
                "source_of_funds": row["source_of_funds"],
            }
        ],
        "expected_confidence": row["match_confidence"],
        "expected_selected_contract_id": row["contract_id"],
        "expected_top_contract_id": row["contract_id"],
    }


def export_confirmed_golden_set(
    database_path: Path,
    existing_golden_path: Path,
    output_path: Path,
) -> Path:
    status = evaluate_review_workspace(database_path)
    if not status.release_ready:
        raise ValueError("project links cannot be exported until every release check passes")
    existing = json.loads(existing_golden_path.read_text(encoding="utf-8"))
    if existing.get("schema_version") != 1 or not isinstance(existing.get("cases"), list):
        raise ValueError("existing reviewed-project file is invalid")
    cases = list(existing["cases"])
    known_ids = {case["case_id"] for case in cases}
    reviewed_dates = [existing.get("reviewed_at", "")]
    for row in _confirmed_rows(database_path):
        if row["case_id"] not in known_ids:
            cases.append(_golden_case(row))
            known_ids.add(row["case_id"])
        reviewed_dates.append(row["last_reviewed_at"])
    document = {
        "schema_version": 1,
        "reviewed_at": max(value for value in reviewed_dates if value),
        "cases": cases,
    }
    building = output_path.with_name(f".{output_path.name}.building")
    building.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_golden_cases(building)
    building.replace(output_path)
    return output_path
