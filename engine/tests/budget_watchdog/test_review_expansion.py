import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.candidate_queue import ReviewCandidate
from engine.budget_watchdog.identity import BudgetProject, DeliveryProject, LinkConfidence
from engine.budget_watchdog.review_expansion import (
    DeliveryContext,
    build_review_workspace,
    evaluate_review_workspace,
    select_balanced_cases,
)
from engine.budget_watchdog.review_precheck import run_review_prechecks
from engine.budget_watchdog.review_release import (
    export_confirmed_golden_set,
    write_review_status,
)
from engine.budget_watchdog.storage import CanonicalStore

ROOT = Path(__file__).resolve().parents[3]


def _candidate(index: int, year: int, amount: int) -> ReviewCandidate:
    return ReviewCandidate(
        fiscal_year=year,
        budget_line_id=f"18-001|sample-{index}",
        contract_id=f"{year % 100:02d}AA{index:04d}",
        confidence=LinkConfidence.HIGH,
        score=90,
        signals=("year_match", "strong_title_match", "amount_compatible"),
        budget_description=f"Construction of sample project {index}",
        delivery_description=f"CONSTRUCTION OF SAMPLE PROJECT {index}",
        budget_amount_centavos=amount,
        delivery_budget_centavos=amount - 100_000,
        budget_evidence_url=f"https://budget.example.test/{index}",
        delivery_evidence_url=f"https://projects.example.test/{index}",
        budget_artifact_sha256="b" * 64,
        delivery_artifact_sha256="a" * 64,
        budget_location=f"Province {index % 5}",
        delivery_location=f"Province {index % 5}, Region {index % 3}",
        source_of_funds=f"Regular Infra - GAA {year}",
    )


def _context(index: int, candidate: ReviewCandidate) -> DeliveryContext:
    categories = ("Roads", "Buildings and Facilities", "Flood Control and Drainage")
    regions = ("Region I", "Region VII", "Region XIII")
    return DeliveryContext(
        contract_id=candidate.contract_id,
        category=categories[index % len(categories)],
        status="Completed" if index % 2 else "On-Going",
        progress="100.0" if index % 2 else "55.0",
        contractor_name=f"Contractor {index}",
        contractor_parties=(f"contractor:{index}", f"contractor:{index}:joint")
        if index in {2, 13}
        else (f"contractor:{index}",),
        province=f"Province {index % 5}",
        region=regions[index % len(regions)],
        latitude="14.5",
        longitude="121.0",
        has_source_image=index % 3 == 0,
        evidence_questions=("coordinate_location_conflict",) if index in {3, 14, 18} else (),
        source_sha256="a" * 64,
    )


def _sample(size: int = 24):
    amounts = (500_000_000, 2_000_000_000, 7_500_000_000, 15_000_000_000)
    candidates = tuple(
        _candidate(index, 2024 + (index % 2), amounts[index % len(amounts)])
        for index in range(size)
    )
    contexts = {item.contract_id: _context(index, item) for index, item in enumerate(candidates)}
    return candidates, contexts


def _canonical_database(path, candidates) -> None:
    with CanonicalStore(path) as store:
        store.store_budget_projects(
            tuple(
                BudgetProject(
                    item.budget_line_id,
                    item.fiscal_year,
                    item.budget_description,
                    item.budget_amount_centavos,
                    item.budget_location,
                )
                for item in candidates
            ),
            "b" * 64,
        )
        store.store_delivery_projects(
            tuple(
                DeliveryProject(
                    item.contract_id,
                    item.fiscal_year,
                    item.delivery_description,
                    item.delivery_budget_centavos,
                    item.delivery_location,
                    item.source_of_funds,
                )
                for item in candidates
            ),
            "a" * 64,
        )


def test_balanced_selection_covers_years_places_types_values_and_special_cases() -> None:
    candidates, contexts = _sample()

    selected = select_balanced_cases(candidates, contexts, target=12)

    assert len(selected) == 12
    assert {case.candidate.fiscal_year for case in selected} == {2024, 2025}
    assert len({case.context.region for case in selected}) == 3
    assert len({case.category_group for case in selected}) == 3
    assert len({case.amount_band for case in selected}) == 4
    assert any(case.is_joint_venture for case in selected)
    assert any(case.context.evidence_questions for case in selected)


def test_workspace_starts_closed_and_uses_plain_language(tmp_path) -> None:
    candidates, contexts = _sample()
    output = tmp_path / "review-expansion"

    result = build_review_workspace(candidates, contexts, output, target=12)
    status = evaluate_review_workspace(result.database_path)

    assert result.case_count == 12
    assert status.reviewed_cases == 0
    assert status.release_ready is False
    assert "100 checked cases are required" in status.reasons
    document = (output / "index.html").read_text()
    assert "Project link review" in document
    assert "What reviewers need to decide" in document
    assert "not proof of wrongdoing" in document
    assert "provenance" not in document.lower()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["case_count"] == 12
    assert manifest["release_ready"] is False
    assert manifest["distribution"]["year"] == {"2024": 6, "2025": 6}
    packet = json.loads((output / "cases.json").read_text())
    assert packet["count"] == 12
    with pytest.raises(ValueError, match="every release check passes"):
        export_confirmed_golden_set(
            result.database_path,
            ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json",
            tmp_path / "must-not-publish.json",
        )


def test_precheck_reconciles_every_case_and_stops_on_changed_source_fact(tmp_path) -> None:
    candidates, contexts = _sample()
    output = tmp_path / "review-expansion"
    result = build_review_workspace(candidates, contexts, output, target=12)
    canonical = tmp_path / "canonical.sqlite3"
    _canonical_database(canonical, candidates)

    passed = run_review_prechecks(result.database_path, canonical, "2026-11-06T09:00:00+04:00")

    assert passed.checked_cases == 12
    assert passed.passed_cases == 12
    assert passed.failed_cases == 0
    connection = sqlite3.connect(result.database_path)
    try:
        connection.execute(
            "UPDATE review_cases SET budget_amount_centavos = budget_amount_centavos + 1 "
            "WHERE case_id = (SELECT case_id FROM review_cases ORDER BY case_id LIMIT 1)"
        )
        connection.commit()
    finally:
        connection.close()

    failed = run_review_prechecks(result.database_path, canonical, "2026-11-06T09:01:00+04:00")

    assert failed.failed_cases == 1
    assert evaluate_review_workspace(result.database_path).critical_failures == 1


def test_two_independent_decisions_control_the_release_gate(tmp_path) -> None:
    candidates, contexts = _sample(120)
    output = tmp_path / "review-expansion"
    result = build_review_workspace(candidates, contexts, output, target=100)
    connection = sqlite3.connect(result.database_path)
    try:
        case_ids = [row[0] for row in connection.execute("SELECT case_id FROM review_cases")]
        rows = []
        for index, case_id in enumerate(case_ids):
            decision = "reject" if index < 4 else "confirm"
            for reviewer in ("reviewer-one", "reviewer-two"):
                rows.append(
                    (
                        case_id,
                        reviewer,
                        decision,
                        "https://example.gov.ph/source",
                        "b" * 64,
                        "The source titles, year, amount, and place were checked.",
                        "2026-11-05T12:00:00+04:00",
                    )
                )
        connection.executemany(
            """
            INSERT INTO review_decisions (
                case_id, reviewer_id, decision, evidence_url,
                evidence_sha256, reviewer_note, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()

    same_result = build_review_workspace(candidates, contexts, output, target=100)
    status = evaluate_review_workspace(same_result.database_path)

    assert status.reviewed_cases == 100
    assert status.confirmed_cases == 96
    assert status.precision_bps == 9_600
    assert status.agreement_bps == 10_000
    assert status.release_ready is True
    status_path = write_review_status(result.database_path, output / "review-status.json")
    assert json.loads(status_path.read_text())["release_ready"] is True

    expanded = tmp_path / "expanded-golden.json"
    export_confirmed_golden_set(
        result.database_path,
        ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json",
        expanded,
    )
    expanded_document = json.loads(expanded.read_text())
    assert len(expanded_document["cases"]) == 102
