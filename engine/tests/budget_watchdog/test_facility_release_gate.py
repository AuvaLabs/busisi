import pytest

from engine.budget_watchdog.facility_identity import (
    FacilityLink,
    FacilityRegistryRecord,
    FacilityTitleRecord,
)
from engine.budget_watchdog.facility_release_gate import (
    build_facility_review_packet,
    candidate_set_sha256,
    evaluate_facility_release,
)


def _links(count: int = 100) -> tuple[FacilityLink, ...]:
    return tuple(
        FacilityLink(
            source_type="delivery" if index % 2 else "budget",
            record_id=f"record-{index:03d}",
            match_state="official_exact",
            facility_id=f"deped:{100000 + index}",
            record_group_key=None,
            record_group_label=f"School {index}",
            match_method="exact_registry_name_and_place",
            confidence=95,
            signals=("exact_registry_name_in_title", "place_in_record"),
            limitation="The link identifies a school, not a completed building.",
        )
        for index in range(count)
    )


def _manifest(links: tuple[FacilityLink, ...]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_artifact_sha256": "a" * 64,
        "candidate_set_sha256": candidate_set_sha256(links),
        "matcher_version": "facility-identity-v1",
        "critical_reconciliation_failures": [],
        "cases": [
            {
                "source_type": link.source_type,
                "record_id": link.record_id,
                "facility_id": link.facility_id,
                "reviewer_one_id": "reviewer-one",
                "reviewer_one_decision": "accept",
                "reviewer_two_id": "reviewer-two",
                "reviewer_two_decision": "accept",
                "adjudication": "correct",
            }
            for link in links
        ],
    }


def test_release_gate_passes_only_a_bound_reviewed_candidate_set() -> None:
    links = _links()

    result = evaluate_facility_release(_manifest(links), links, "a" * 64)

    assert result.passed is True
    assert result.reviewed_cases == 100
    assert result.precision_bps == 10_000
    assert result.agreement_bps == 10_000
    assert result.critical_failures == 0
    assert result.reasons == ()
    assert len(result.manifest_sha256) == 64


def test_release_gate_fails_closed_for_quality_or_reconciliation_gaps() -> None:
    links = _links()
    too_few = evaluate_facility_release(_manifest(links[:99]), links[:99], "a" * 64)
    assert too_few.passed is False
    assert "reviewed cases" in " ".join(too_few.reasons)

    low_quality_manifest = _manifest(links)
    cases = list(low_quality_manifest["cases"])
    for index in range(6):
        cases[index] = {**cases[index], "adjudication": "incorrect"}
    low_quality_manifest["cases"] = cases
    low_quality = evaluate_facility_release(low_quality_manifest, links, "a" * 64)
    assert low_quality.precision_bps == 9_400
    assert low_quality.passed is False

    critical_manifest = _manifest(links)
    critical_manifest["critical_reconciliation_failures"] = ["registry total mismatch"]
    critical = evaluate_facility_release(critical_manifest, links, "a" * 64)
    assert critical.critical_failures == 1
    assert critical.passed is False


def test_release_gate_rejects_unbound_or_malformed_review_evidence() -> None:
    links = _links()
    with pytest.raises(ValueError, match="candidate set"):
        evaluate_facility_release(
            {**_manifest(links), "candidate_set_sha256": "b" * 64},
            links,
            "a" * 64,
        )
    with pytest.raises(ValueError, match="source artifact"):
        evaluate_facility_release(_manifest(links), links, "b" * 64)
    duplicate_reviewer = _manifest(links)
    duplicate_reviewer["cases"][0]["reviewer_two_id"] = "reviewer-one"
    with pytest.raises(ValueError, match="independent"):
        evaluate_facility_release(duplicate_reviewer, links, "a" * 64)


def test_review_packet_keeps_candidate_and_source_evidence_together() -> None:
    link = _links(1)[0]
    source_record = FacilityTitleRecord(
        source_type=link.source_type,
        record_id=link.record_id,
        title="Construction at School 0, Sample City",
        location="Sample City, Region I",
    )
    registry = FacilityRegistryRecord(
        facility_id=link.facility_id or "",
        facility_type="school",
        official_id="100000",
        official_name="School 0",
        municipality="Sample City",
        province="Sample Province",
        region="Region I",
        source_id="deped-ppp-2025",
    )

    packet = build_facility_review_packet(
        (source_record,),
        (registry,),
        (link,),
        "a" * 64,
    )

    assert packet["candidate_set_sha256"] == candidate_set_sha256((link,))
    assert packet["candidate_count"] == 1
    assert packet["cases"][0]["record_title"] == source_record.title
    assert packet["cases"][0]["official_school_id"] == "100000"
    assert packet["cases"][0]["reviewer_one_decision"] is None
    assert "adjudication" in packet["cases"][0]
