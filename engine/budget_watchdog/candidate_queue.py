"""Generate evidence-linked candidates for manual golden-set review."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from engine.budget_watchdog.identity import (
    BudgetProject,
    DeliveryProject,
    LinkConfidence,
    match_candidates,
)
from engine.budget_watchdog.models import validate_fiscal_year


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    fiscal_year: int
    budget_line_id: str
    contract_id: str
    confidence: LinkConfidence
    score: int
    signals: tuple[str, ...]
    budget_description: str
    delivery_description: str
    budget_amount_centavos: int
    delivery_budget_centavos: int
    budget_evidence_url: str
    delivery_evidence_url: str


def _query(database_path: Path, fiscal_years: tuple[int, ...], limit: int) -> list[sqlite3.Row]:
    sql = """
        WITH budget_candidates AS (
            SELECT *, COUNT(*) OVER (
                PARTITION BY project_family_id, fiscal_year
            ) AS family_count
            FROM budget_projects
            WHERE fiscal_year IN (SELECT value FROM json_each(?))
              AND amount_centavos > 0
        ),
        delivery_candidates AS (
            SELECT *, COUNT(*) OVER (
                PARTITION BY project_family_id, fiscal_year
            ) AS family_count
            FROM delivery_projects
            WHERE fiscal_year IN (SELECT value FROM json_each(?))
        )
        SELECT
            b.budget_line_id,
            b.fiscal_year,
            b.description AS budget_description,
            b.amount_centavos,
            b.location AS budget_location,
            d.contract_id,
            d.description AS delivery_description,
            d.budget_centavos,
            d.location AS delivery_location,
            d.source_of_funds
        FROM budget_candidates b
        JOIN delivery_candidates d
          ON d.project_family_id = b.project_family_id
         AND d.fiscal_year = b.fiscal_year
        WHERE b.family_count = 1 AND d.family_count = 1
        ORDER BY b.fiscal_year DESC, b.amount_centavos DESC, b.budget_line_id
        LIMIT ?
    """
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        encoded_years = json.dumps(fiscal_years)
        return connection.execute(sql, (encoded_years, encoded_years, limit)).fetchall()
    finally:
        connection.close()


def generate_review_candidates(
    database_path: Path,
    *,
    fiscal_years: tuple[int, ...],
    limit: int,
) -> tuple[ReviewCandidate, ...]:
    if not database_path.is_file():
        raise ValueError("database_path must be an existing file")
    if not fiscal_years or len(fiscal_years) != len(set(fiscal_years)):
        raise ValueError("fiscal_years must be non-empty and unique")
    for fiscal_year in fiscal_years:
        validate_fiscal_year(fiscal_year)
    if limit <= 0:
        raise ValueError("limit must be positive")

    output: list[ReviewCandidate] = []
    for row in _query(database_path, fiscal_years, limit):
        budget = BudgetProject(
            budget_line_id=row["budget_line_id"],
            fiscal_year=row["fiscal_year"],
            description=row["budget_description"],
            amount_centavos=row["amount_centavos"],
            location=row["budget_location"],
        )
        delivery = DeliveryProject(
            contract_id=row["contract_id"],
            fiscal_year=row["fiscal_year"],
            description=row["delivery_description"],
            budget_centavos=row["budget_centavos"],
            location=row["delivery_location"],
            source_of_funds=row["source_of_funds"],
        )
        decision = match_candidates(budget, (delivery,))
        if decision.confidence not in {LinkConfidence.EXACT, LinkConfidence.HIGH}:
            continue
        score = decision.candidates[0]
        department_id = budget.budget_line_id.split("-", maxsplit=1)[0]
        budget_url = (
            "https://budget.bettergov.ph/api/v1/gaa/search"
            f"?q={quote_plus(budget.description)}"
            f"&department_id={quote_plus(department_id)}"
            f"&year={budget.fiscal_year}"
        )
        output.append(
            ReviewCandidate(
                fiscal_year=budget.fiscal_year,
                budget_line_id=budget.budget_line_id,
                contract_id=delivery.contract_id,
                confidence=decision.confidence,
                score=score.score,
                signals=score.signals,
                budget_description=budget.description,
                delivery_description=delivery.description,
                budget_amount_centavos=budget.amount_centavos,
                delivery_budget_centavos=delivery.budget_centavos,
                budget_evidence_url=budget_url,
                delivery_evidence_url=(
                    f"https://api.dpwh.bettergov.ph/projects/{delivery.contract_id}"
                ),
            )
        )
    return tuple(output)
