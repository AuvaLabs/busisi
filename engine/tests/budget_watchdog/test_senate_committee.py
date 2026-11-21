import json

import pytest

from engine.budget_watchdog.senate_committee import (
    SenateCommitteeError,
    load_senate_committee_release,
    reconcile_senate_committee_release,
)


def _release(*, state: str = "verified_changes") -> dict[str, object]:
    official = state == "verified_changes"
    return {
        "schema_version": 1,
        "release_id": "fy2027-cr131",
        "fiscal_year": 2027,
        "report_number": "131",
        "related_bill": "HB 10858",
        "state": state,
        "checked_at": "2026-11-21T12:00:00+00:00",
        "official_document": {
            "source_url": "https://legacy.senate.gov.ph/lis/bill_res.aspx?congress=20&q=HBN-10858",
            "publication_date": "2026-11-20",
            "artifact_sha256": "a" * 64,
            "byte_size": 12345,
        }
        if official
        else None,
        "controls": [
            {
                "group_code": "house_added_noncompliant",
                "label": "House-added projects that did not meet stated requirements",
                "project_count": 1,
                "previous_centavos": 10_000,
                "senate_centavos": 0,
                "change_centavos": -10_000,
            },
            {
                "group_code": "nep_projects",
                "label": "Projects from the Executive proposal",
                "project_count": 1,
                "previous_centavos": 20_000,
                "senate_centavos": 5_000,
                "change_centavos": -15_000,
            },
        ]
        if official
        else [],
        "items": [
            {
                "change_id": "cr131:house:1",
                "group_code": "house_added_noncompliant",
                "origin_stage": "house_gab",
                "source_project_id": "H-1",
                "title": "Sample road project",
                "project_type": "road",
                "region": "Region III",
                "province": "Bulacan",
                "city_or_municipality": None,
                "district": None,
                "previous_centavos": 10_000,
                "senate_centavos": 0,
                "change_centavos": -10_000,
                "reason": "Required project details were not shown in the schedule.",
                "source_page": 12,
                "match_state": "unmatched",
                "linked_project_slug": None,
                "public_note": "This records a committee-stage change, not a final deletion.",
            },
            {
                "change_id": "cr131:nep:1",
                "group_code": "nep_projects",
                "origin_stage": "nep",
                "source_project_id": "N-1",
                "title": "Sample flood-control project",
                "project_type": "flood_control",
                "region": "NCR",
                "province": None,
                "city_or_municipality": "Manila",
                "district": "1st District",
                "previous_centavos": 20_000,
                "senate_centavos": 5_000,
                "change_centavos": -15_000,
                "reason": "The committee schedule records a lower amount.",
                "source_page": 13,
                "match_state": "exact",
                "linked_project_slug": "sample-flood-project",
                "public_note": "The exact project identifier matched a Busisi record.",
            },
        ]
        if official
        else [],
        "public_note": (
            "The official report and complete project schedules were checked."
            if official
            else "The official report and project schedules are not in Busisi yet."
        ),
    }


def test_accepts_watch_only_release_without_money_claims() -> None:
    release = load_senate_committee_release(
        json.dumps(_release(state="awaiting_official_document")).encode()
    )
    summary = reconcile_senate_committee_release(release)

    assert release.state == "awaiting_official_document"
    assert release.official_document is None
    assert summary.item_count == 0
    assert summary.total_change_centavos is None


def test_reconciles_verified_items_to_group_and_overall_controls() -> None:
    release = load_senate_committee_release(json.dumps(_release()).encode())
    summary = reconcile_senate_committee_release(release)

    assert summary.item_count == 2
    assert summary.total_previous_centavos == 30_000
    assert summary.total_senate_centavos == 5_000
    assert summary.total_change_centavos == -25_000


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda root: root.update(
                official_document={
                    "source_url": "https://legacy.senate.gov.ph/test.pdf",
                    "publication_date": "2026-11-20",
                    "artifact_sha256": "a" * 64,
                    "byte_size": 12,
                }
            ),
            "watch-only",
        ),
        (lambda root: root["items"][0].update(previous_centavos=100.0), "integer centavos"),
        (lambda root: root["items"][0].update(change_centavos=-9_999), "does not equal"),
        (lambda root: root["controls"][0].update(project_count=2), "does not reconcile"),
        (lambda root: root["items"][0].update(match_state="quarantine"), "held-back match"),
        (
            lambda root: root["official_document"].update(
                source_url="https://example.com/file.pdf"
            ),
            "official Senate",
        ),
    ],
)
def test_rejects_unsupported_or_unreconciled_claims(mutator, message: str) -> None:
    payload = _release()
    if message == "watch-only":
        payload = _release(state="awaiting_official_document")
    mutator(payload)

    with pytest.raises(SenateCommitteeError, match=message):
        load_senate_committee_release(json.dumps(payload).encode())
