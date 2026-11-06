"""Reconcile project-link review cases against the saved source records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "api.dpwh.bettergov.ph",
        "budget.bettergov.ph",
        "budget.example.test",
        "projects.example.test",
    }
)


@dataclass(frozen=True, slots=True)
class ReviewPrecheckResult:
    checked_cases: int
    passed_cases: int
    failed_cases: int


def _read_cases(path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM review_cases ORDER BY case_id").fetchall()
    finally:
        connection.close()


def _source_records(
    path: Path,
) -> tuple[dict[tuple[str, int], sqlite3.Row], dict[str, sqlite3.Row]]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        budgets = {
            (row["budget_line_id"], row["fiscal_year"]): row
            for row in connection.execute("SELECT * FROM budget_projects")
        }
        deliveries = {
            row["contract_id"]: row for row in connection.execute("SELECT * FROM delivery_projects")
        }
    finally:
        connection.close()
    return budgets, deliveries


def _safe_source_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_SOURCE_HOSTS


def _check_case(
    case: sqlite3.Row,
    budgets: dict[tuple[str, int], sqlite3.Row],
    deliveries: dict[str, sqlite3.Row],
) -> tuple[list[str], list[str]]:
    checks: list[str] = []
    failures: list[str] = []
    budget = budgets.get((case["budget_line_id"], case["fiscal_year"]))
    delivery = deliveries.get(case["contract_id"])
    for label, available in (("budget record exists", budget), ("project record exists", delivery)):
        (checks if available else failures).append(label)
    for label, value in (
        ("budget source link allowed", case["budget_source_url"]),
        ("project source link allowed", case["delivery_source_url"]),
    ):
        (checks if _safe_source_url(value) else failures).append(label)
    if budget:
        for label, left, right in (
            ("budget title agrees", case["budget_description"], budget["description"]),
            ("budget amount agrees", case["budget_amount_centavos"], budget["amount_centavos"]),
            ("budget place agrees", case["budget_location"], budget["location"]),
            (
                "budget saved-file check agrees",
                case["budget_source_sha256"],
                budget["artifact_sha256"],
            ),
        ):
            (checks if left == right else failures).append(label)
    if delivery:
        for label, left, right in (
            ("project year agrees", case["fiscal_year"], delivery["fiscal_year"]),
            ("project title agrees", case["delivery_description"], delivery["description"]),
            (
                "project amount agrees",
                case["delivery_budget_centavos"],
                delivery["budget_centavos"],
            ),
            ("project office agrees", case["delivery_location"], delivery["location"]),
            ("fund source agrees", case["source_of_funds"], delivery["source_of_funds"]),
            (
                "project saved-file check agrees",
                case["delivery_source_sha256"],
                delivery["artifact_sha256"],
            ),
        ):
            (checks if left == right else failures).append(label)
    return checks, failures


def run_review_prechecks(
    review_database: Path,
    canonical_database: Path,
    checked_at: str,
) -> ReviewPrecheckResult:
    if not checked_at.strip():
        raise ValueError("checked_at must be provided")
    cases = _read_cases(review_database)
    budgets, deliveries = _source_records(canonical_database)
    rows = []
    failed = 0
    for case in cases:
        checks, failures = _check_case(case, budgets, deliveries)
        failed += int(bool(failures))
        rows.append(
            (
                case["case_id"],
                checked_at,
                int(not failures),
                json.dumps(checks),
                json.dumps(failures),
            )
        )
    connection = sqlite3.connect(review_database)
    try:
        with connection:
            connection.execute("DELETE FROM review_prechecks")
            connection.executemany("INSERT INTO review_prechecks VALUES (?, ?, ?, ?, ?)", rows)
            connection.execute(
                "UPDATE review_metadata SET value = ? WHERE key = 'critical_failures'",
                (str(failed),),
            )
    finally:
        connection.close()
    return ReviewPrecheckResult(len(cases), len(cases) - failed, failed)
