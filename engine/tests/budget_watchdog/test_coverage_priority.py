from engine.budget_watchdog.coverage_priority import (
    CoveragePriorityFacts,
    classify_coverage_priority,
)


def test_prioritizes_reviewed_and_evidence_rich_contracts_deterministically() -> None:
    reviewed = classify_coverage_priority(
        CoveragePriorityFacts(reviewed=True)
    )
    evidence_rich = classify_coverage_priority(
        CoveragePriorityFacts(
            source_image_hint=True,
            high_value=True,
            joint_venture=True,
            repeated_contractor=True,
            integrity_question=True,
            coa_evidence=True,
        )
    )

    assert reviewed.score == 0
    assert reviewed.reasons == ("reviewed_dossier",)
    assert evidence_rich.score == 5
    assert evidence_rich.reasons == (
        "source_image_hint",
        "high_value",
        "joint_venture",
        "repeated_contractor",
        "integrity_question",
        "coa_evidence",
    )


def test_plain_contracts_remain_eligible_without_claiming_evidence() -> None:
    result = classify_coverage_priority(CoveragePriorityFacts())

    assert result.score == 100
    assert result.reasons == ()
