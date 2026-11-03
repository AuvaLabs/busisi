import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import responses

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.districts import (
    OfficeDistrictAttribution,
    acquire_district_snapshot,
    parse_district_pages,
)
from engine.budget_watchdog.sources import default_source_registry


def _district(
    district_id: str,
    label: str,
    office: str,
    *,
    tier: str,
    representative: str,
) -> dict[str, object]:
    return {
        "id": district_id,
        "label": label,
        "jurisdiction": label.split(",", maxsplit=1)[0],
        "district_label": label.split(",", maxsplit=1)[1].strip(),
        "region": "Region I",
        "representative": {
            "name": representative,
            "seat": label,
            "status": "resolved",
            "status_note": None,
            "profile_url": f"https://www.congress.gov.ph/house-members/view/{district_id[-1]}",
        },
        "offices": [{"name": office, "tier": tier}],
    }


def _page(districts: list[dict[str, object]], *, offset: int, total: int) -> bytes:
    return json.dumps(
        {
            "meta": {
                "source_commit": "a" * 40,
                "built_at": "2026-10-26T08:46:14.383Z",
                "offset": offset,
                "returned": len(districts),
                "total": total,
            },
            "data": {"districts": districts},
        }
    ).encode()


def test_district_snapshot_classifies_single_shared_and_unassigned_offices() -> None:
    pages = (
        _page(
            [
                _district(
                    "leg:alpha:1st",
                    "Alpha, 1st District",
                    "Alpha 1st DEO",
                    tier="A",
                    representative="Rep One",
                ),
                _district(
                    "leg:beta:1st",
                    "Beta, 1st District",
                    "Shared DEO",
                    tier="B",
                    representative="Rep Two",
                ),
            ],
            offset=0,
            total=3,
        ),
        _page(
            [
                _district(
                    "leg:beta:2nd",
                    "Beta, 2nd District",
                    "Shared DEO",
                    tier="B",
                    representative="Rep Three",
                )
            ],
            offset=2,
            total=3,
        ),
    )

    snapshot = parse_district_pages(
        pages,
        source_sha256=("b" * 64, "c" * 64),
        retrieved_on=date(2026, 11, 3),
    )

    single = snapshot.lookup("Alpha 1st DEO")
    shared = snapshot.lookup("Shared DEO")
    missing = snapshot.lookup("Regional Office")
    assert snapshot.district_count == 3
    assert snapshot.office_count == 2
    assert single.classification == "single_district"
    assert single.seats[0].representative_name == "Rep One"
    assert shared.classification == "shared_office"
    assert [seat.label for seat in shared.seats] == [
        "Beta, 1st District",
        "Beta, 2nd District",
    ]
    assert missing.classification == "unassigned"
    assert missing.seats == ()


def test_district_snapshot_rejects_incomplete_or_duplicate_pages() -> None:
    district = _district(
        "leg:alpha:1st",
        "Alpha, 1st District",
        "Alpha 1st DEO",
        tier="A",
        representative="Rep One",
    )
    with pytest.raises(ValueError, match="complete district set"):
        parse_district_pages(
            (_page([district], offset=0, total=2),),
            source_sha256=("b" * 64,),
            retrieved_on=date(2026, 11, 3),
        )
    with pytest.raises(ValueError, match="unique"):
        parse_district_pages(
            (
                _page([district], offset=0, total=2),
                _page([district], offset=1, total=2),
            ),
            source_sha256=("b" * 64, "c" * 64),
            retrieved_on=date(2026, 11, 3),
        )


@responses.activate
def test_district_acquisition_archives_both_source_pages(tmp_path: Path) -> None:
    first = _district(
        "leg:alpha:1st",
        "Alpha, 1st District",
        "Alpha 1st DEO",
        tier="A",
        representative="Rep One",
    )
    second = _district(
        "leg:beta:1st",
        "Beta, 1st District",
        "Beta 1st DEO",
        tier="A",
        representative="Rep Two",
    )
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/api/v1/hgab/2027/districts?limit=200&offset=0",
        body=_page([first], offset=0, total=2),
        content_type="application/json",
    )
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/api/v1/hgab/2027/districts?limit=200&offset=200",
        body=_page([second], offset=1, total=2),
        content_type="application/json",
    )

    artifacts, snapshot = acquire_district_snapshot(
        SourceFetcher(default_source_registry()),
        ArtifactArchive(tmp_path),
        retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
    )

    assert len(artifacts) == 2
    assert all(artifact.blob_path.is_file() for artifact in artifacts)
    assert snapshot.district_count == 2
    assert snapshot.retrieved_on == date(2026, 11, 3)


def test_district_boundaries_reject_invalid_classification_and_hashes() -> None:
    with pytest.raises(ValueError, match="classification"):
        OfficeDistrictAttribution("Office", "guessed", ())
    with pytest.raises(ValueError, match="non-empty and aligned"):
        parse_district_pages((), source_sha256=(), retrieved_on=date(2026, 11, 3))
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        parse_district_pages(
            (_page([], offset=0, total=0),),
            source_sha256=("A" * 64,),
            retrieved_on=date(2026, 11, 3),
        )
