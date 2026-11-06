import json
import sqlite3
from dataclasses import replace

import pytest

from engine.budget_watchdog.candidate_queue import ReviewCandidate
from engine.budget_watchdog.identity import LinkConfidence
from engine.budget_watchdog.review_council import (
    COUNCIL_SEATS,
    CouncilVerdict,
    adjudicate_case,
    build_evidence_packet,
    council_status,
    record_verdict,
    validate_verdict,
    validate_verdict_against_packet,
    verdict_from_payload,
)
from engine.budget_watchdog.review_expansion import DeliveryContext, build_review_workspace


def _workspace(tmp_path):
    candidate = ReviewCandidate(
        fiscal_year=2025,
        budget_line_id="18-001|sample-health-center",
        contract_id="25AA0001",
        confidence=LinkConfidence.HIGH,
        score=90,
        signals=("year_match", "strong_title_match", "amount_compatible"),
        budget_description="Construction of Sample Health Center, Sample City",
        delivery_description="CONSTRUCTION OF SAMPLE HEALTH CENTER, SAMPLE CITY",
        budget_amount_centavos=5_000_000_000,
        delivery_budget_centavos=4_950_000_000,
        budget_evidence_url="https://budget.bettergov.ph/sample",
        delivery_evidence_url="https://api.dpwh.bettergov.ph/projects/25AA0001",
        budget_artifact_sha256="b" * 64,
        delivery_artifact_sha256="a" * 64,
        budget_location="Sample City",
        delivery_location="Sample DEO, Region I",
        source_of_funds="Regular Infra - GAA 2025",
    )
    context = DeliveryContext(
        contract_id=candidate.contract_id,
        category="Buildings and Facilities",
        status="Completed",
        progress="100.0",
        contractor_name="SAMPLE BUILDERS",
        contractor_parties=("pcab:1",),
        province="Sample DEO",
        region="Region I",
        latitude="14.5",
        longitude="121.0",
        has_source_image=True,
        evidence_questions=(),
        source_sha256="a" * 64,
    )
    result = build_review_workspace(
        (candidate,), {candidate.contract_id: context}, tmp_path / "review", target=1
    )
    connection = sqlite3.connect(result.database_path)
    try:
        case_id = connection.execute("SELECT case_id FROM review_cases").fetchone()[0]
        connection.execute(
            "INSERT INTO review_prechecks VALUES (?, ?, 1, ?, ?)",
            (case_id, "2026-11-06T10:00:00+04:00", json.dumps(["all checks"]), "[]"),
        )
        connection.commit()
    finally:
        connection.close()
    return result.database_path, case_id


def _verdict(case_id, seat, decision="confirm", *, blocking=False):
    findings = (
        (
            {
                "code": "identity_conflict",
                "severity": "blocking",
                "claim": "The phases may describe different physical work.",
                "evidence": "The budget title says Phase 1 while the project title says Phase 2.",
                "what_to_check": "Check the signed scope of work.",
                "evidence_paths": (
                    "/budget_record/description",
                    "/project_record/description",
                ),
            },
        )
        if blocking
        else ()
    )
    return CouncilVerdict(
        schema_version=2,
        case_id=case_id,
        seat=seat,
        decision=decision,
        confidence="high",
        summary="The recorded year, place, amount, and work description agree.",
        identity_basis=(
            {
                "claim": "The records have the same year and work description.",
                "evidence_paths": (
                    "/budget_record/fiscal_year",
                    "/budget_record/description",
                    "/project_record/description",
                ),
            },
        ),
        findings=findings,
        gaps=(),
        does_not_prove=("This does not prove physical completion or payment.",),
        recommendation="Keep the link only with the stated evidence limits.",
    )


def _record(database, verdict, round_number=1):
    record_verdict(
        database,
        verdict,
        round_number=round_number,
        model=f"model-{verdict.seat}",
        packet_sha256="c" * 64,
        prompt_sha256="d" * 64,
        output_sha256="e" * 64,
        started_at="2026-11-06T10:01:00+04:00",
        duration_seconds=1.5,
        token_usage={"input_tokens": 1000, "output_tokens": 200},
    )


def _payload(case_id="case", seat="source_auditor"):
    return {
        "schema_version": 2,
        "case_id": case_id,
        "seat": seat,
        "decision": "confirm",
        "confidence": "high",
        "summary": "The supplied records agree.",
        "identity_basis": [
            {
                "claim": "The records have the same year and work.",
                "evidence_paths": [
                    "/budget_record/fiscal_year",
                    "/budget_record/description",
                ],
            }
        ],
        "findings": [],
        "gaps": [],
        "does_not_prove": ["This does not prove payment."],
        "recommendation": "Keep the evidence limits visible.",
    }


def test_evidence_packet_is_source_checked_and_contains_no_other_votes(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)

    packet = build_evidence_packet(database, case_id)

    assert packet["case_id"] == case_id
    assert packet["source_precheck"]["passed"] is True
    assert packet["budget_record"]["amount_centavos"] == 5_000_000_000
    assert packet["budget_record"]["source_classification"].startswith("civic data mirror")
    assert packet["project_record"]["contract_id"] == "25AA0001"
    assert "council_verdicts" not in packet


def test_verdict_validation_requires_grounded_findings() -> None:
    verdict = _verdict("case", "identity_skeptic", blocking=True)
    validate_verdict(verdict)

    invalid = replace(
        verdict,
        findings=({**verdict.findings[0], "evidence": ""},),
    )
    with pytest.raises(ValueError, match="evidence"):
        validate_verdict(invalid)

    generalized = replace(verdict, summary="This amount difference is normal.")
    with pytest.raises(ValueError, match="unsupported generalization"):
        validate_verdict(generalized)


def test_payload_parser_enforces_exact_structure_and_allowed_values() -> None:
    assert verdict_from_payload(_payload()).decision == "confirm"

    invalid_payloads = []
    for field, value in (
        ("schema_version", 1),
        ("seat", "other"),
        ("decision", "approve"),
        ("confidence", "certain"),
        ("identity_basis", []),
        ("does_not_prove", "none"),
        ("findings", {}),
        ("gaps", ["missing"]),
    ):
        invalid_payloads.append({**_payload(), field: value})
    invalid_payloads.append({**_payload(), "extra": True})
    invalid_payloads.append(
        {
            **_payload(),
            "findings": [
                {
                    "code": "conflict",
                    "severity": "critical",
                    "claim": "The records differ.",
                    "evidence": "The years differ.",
                    "what_to_check": "Read the scope.",
                    "evidence_paths": [
                        "/budget_record/fiscal_year",
                        "/project_record/source_of_funds",
                    ],
                }
            ],
        }
    )
    for payload in invalid_payloads:
        with pytest.raises(ValueError, match="."):
            verdict_from_payload(payload)


def test_verdict_evidence_paths_must_resolve_in_the_packet(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    packet = build_evidence_packet(database, case_id)
    verdict = _verdict(case_id, "source_auditor")
    validate_verdict_against_packet(verdict, packet)

    invalid = replace(
        verdict,
        identity_basis=(
            {
                "claim": "Unsupported location claim.",
                "evidence_paths": ("/budget_record/missing",),
            },
        ),
    )
    with pytest.raises(ValueError, match="does not exist"):
        validate_verdict_against_packet(invalid, packet)


def test_evidence_packet_requires_an_existing_prechecked_case(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    with pytest.raises(ValueError, match="does not exist"):
        build_evidence_packet(database, "missing")

    connection = sqlite3.connect(database)
    with connection:
        connection.execute("DELETE FROM review_prechecks WHERE case_id = ?", (case_id,))
    connection.close()
    with pytest.raises(ValueError, match="has not passed"):
        build_evidence_packet(database, case_id)


def test_unanimous_council_confirms_and_records_token_totals(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    for seat in COUNCIL_SEATS:
        _record(database, _verdict(case_id, seat))

    outcome = adjudicate_case(database, case_id, "2026-11-06T10:05:00+04:00")
    status = council_status(database)

    assert outcome.outcome == "confirmed"
    assert outcome.votes == dict.fromkeys(COUNCIL_SEATS, "confirm")
    assert status.completed_cases == 1
    assert status.confirmed_cases == 1
    assert status.input_tokens == 3_000
    assert status.output_tokens == 600


def test_disagreement_or_blocking_finding_cannot_confirm(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    _record(database, _verdict(case_id, "source_auditor"))
    _record(database, _verdict(case_id, "identity_skeptic", "reject", blocking=True))
    _record(database, _verdict(case_id, "quality_reviewer"))

    outcome = adjudicate_case(database, case_id, "2026-11-06T10:05:00+04:00")

    assert outcome.outcome == "unclear"
    assert "blocking identity or evidence finding" in outcome.reason


def test_two_rejections_reject_and_missing_seat_is_incomplete(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    _record(database, _verdict(case_id, "source_auditor", "reject"))
    _record(database, _verdict(case_id, "identity_skeptic", "reject"))

    incomplete = adjudicate_case(database, case_id, "2026-11-06T10:05:00+04:00")
    assert incomplete.outcome == "incomplete"

    _record(database, _verdict(case_id, "quality_reviewer", "unclear"))
    rejected = adjudicate_case(database, case_id, "2026-11-06T10:06:00+04:00")
    assert rejected.outcome == "rejected"


def test_mixed_votes_and_packet_mismatch_stay_unconfirmed(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    _record(database, _verdict(case_id, "source_auditor"))
    _record(database, _verdict(case_id, "identity_skeptic", "unclear"))
    record_verdict(
        database,
        _verdict(case_id, "quality_reviewer"),
        round_number=1,
        model="model-quality",
        packet_sha256="f" * 64,
        prompt_sha256="d" * 64,
        output_sha256="e" * 64,
        started_at="2026-11-06T10:01:00+04:00",
        duration_seconds=1.5,
        token_usage={},
    )
    outcome = adjudicate_case(database, case_id, "2026-11-06T10:05:00+04:00")
    assert outcome.outcome == "incomplete"


def test_latest_round_is_used_and_empty_status_is_zero(tmp_path) -> None:
    database, case_id = _workspace(tmp_path)
    assert council_status(database).agreement_bps == 0
    for seat in COUNCIL_SEATS:
        _record(database, _verdict(case_id, seat), round_number=1)
    adjudicate_case(database, case_id, "2026-11-06T10:04:00+04:00", round_number=1)
    for seat in COUNCIL_SEATS:
        _record(database, _verdict(case_id, seat, "unclear"), round_number=2)

    outcome = adjudicate_case(database, case_id, "2026-11-06T10:05:00+04:00")
    connection = sqlite3.connect(database)
    outcome_count = connection.execute("SELECT COUNT(*) FROM council_outcomes").fetchone()[0]
    connection.close()
    status = council_status(database)

    assert outcome.round_number == 2
    assert outcome.outcome == "unclear"
    assert outcome_count == 2
    assert status.completed_cases == 1
    assert status.unclear_cases == 1
