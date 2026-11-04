from __future__ import annotations

import json

import pytest

from engine.budget_watchdog.source_monitor import (
    SourceMonitorError,
    compare_observations,
    parse_dbm_release_catalog,
    parse_hgab_overview,
    parse_huggingface_metadata,
    review_pcab_transition,
)


def test_parses_hgab_overview_identity() -> None:
    payload = json.dumps({
        "meta": {
            "dataset": "hgab",
            "fiscal_year": 2027,
            "source_commit": "a" * 40,
            "built_at": "2026-10-26T08:46:14.383Z",
        },
        "data": {"datasets": [{"key": "dpwh"}, {"key": "fmr"}]},
    }).encode()

    assert parse_hgab_overview(payload) == {
        "source_commit": "a" * 40,
        "built_at": "2026-10-26T08:46:14.383Z",
        "datasets": ["dpwh", "fmr"],
    }


def test_rejects_hgab_overview_with_wrong_year_or_invalid_commit() -> None:
    for year, commit in ((2026, "a" * 40), (2027, "bad")):
        payload = json.dumps({
            "meta": {
                "dataset": "hgab",
                "fiscal_year": year,
                "source_commit": commit,
                "built_at": "2026-10-26T08:46:14.383Z",
            },
            "data": {"datasets": [{"key": "dpwh"}]},
        }).encode()
        with pytest.raises(SourceMonitorError):
            parse_hgab_overview(payload)


@pytest.mark.parametrize(
    "value",
    [
        {"meta": [], "data": {}},
        {
            "meta": {
                "dataset": "hgab",
                "fiscal_year": 2027,
                "source_commit": "a" * 40,
                "built_at": "today",
            },
            "data": {"datasets": [{"key": "dpwh"}]},
        },
        {
            "meta": {
                "dataset": "hgab",
                "fiscal_year": 2027,
                "source_commit": "a" * 40,
                "built_at": "2026-10-26T00:00:00Z",
            },
            "data": {"datasets": []},
        },
        {
            "meta": {
                "dataset": "hgab",
                "fiscal_year": 2027,
                "source_commit": "a" * 40,
                "built_at": "2026-10-26T00:00:00Z",
            },
            "data": {"datasets": [{"key": "dpwh"}, {"key": "dpwh"}]},
        },
    ],
)
def test_rejects_malformed_hgab_overview_boundaries(value: dict) -> None:
    with pytest.raises(SourceMonitorError):
        parse_hgab_overview(json.dumps(value).encode())


def _pcab_document(rows: list[list[str]]) -> bytes:
    return json.dumps({
        "page": 1,
        "total": 1,
        "records": len(rows),
        "rows": [{"id": row[0], "cell": row} for row in rows],
    }).encode()


def test_reviews_pcab_expiry_churn_without_hiding_changed_active_rows() -> None:
    reviewed = _pcab_document([
        ["1", "EXPIRED BUILDER", "100", "AMO", "D", "2026-11-04", "1"],
        ["2", "ACTIVE BUILDER", "200", "AMO", "A", "2027-01-01", "1"],
    ])
    observed = _pcab_document([
        ["2", "ACTIVE BUILDER", "200", "AMO", "A", "2027-01-01", "1"],
        ["3", "NEW BUILDER", "300", "AMO", "B", "2028-01-01", "1"],
    ])

    result = review_pcab_transition(
        reviewed,
        observed,
        reviewed_sha256="a" * 64,
        observed_sha256="b" * 64,
        observed_on="2026-11-04",
    )

    assert result["passed"] is True
    assert result["reviewed_records"] == 2
    assert result["observed_records"] == 2
    assert result["removed_expired_records"] == 1
    assert result["removed_active_records"] == 0
    assert result["added_records"] == 1
    assert result["changed_retained_records"] == 0
    assert result["recommended_floor"] == 1


def test_rejects_pcab_transition_with_active_removal_or_changed_row() -> None:
    reviewed = _pcab_document([
        ["1", "ACTIVE BUILDER", "100", "AMO", "D", "2027-01-01", "1"],
        ["2", "STABLE BUILDER", "200", "AMO", "A", "2027-01-01", "1"],
    ])
    observed = _pcab_document([
        ["2", "RENAMED BUILDER", "200", "AMO", "A", "2027-01-01", "1"],
    ])

    result = review_pcab_transition(
        reviewed,
        observed,
        reviewed_sha256="a" * 64,
        observed_sha256="b" * 64,
        observed_on="2026-11-04",
    )

    assert result["passed"] is False
    assert result["removed_active_records"] == 1
    assert result["changed_retained_records"] == 1
    assert result["recommended_floor"] is None


def test_parses_huggingface_revision_metadata() -> None:
    payload = json.dumps(
        {
            "id": "bettergovph/gaa",
            "sha": "a" * 40,
            "lastModified": "2026-01-29T09:21:01.000Z",
            "private": False,
            "disabled": False,
        }
    ).encode()

    result = parse_huggingface_metadata(payload, "bettergovph/gaa")

    assert result == {
        "dataset_id": "bettergovph/gaa",
        "revision": "a" * 40,
        "last_modified": "2026-01-29T09:21:01.000Z",
    }


def test_rejects_private_disabled_or_malformed_dataset_metadata() -> None:
    for value in (
        {"id": "bettergovph/gaa", "sha": "bad", "lastModified": "today"},
        {
            "id": "bettergovph/gaa",
            "sha": "a" * 40,
            "lastModified": "2026-01-01T00:00:00Z",
            "private": True,
        },
        {"id": "wrong/name", "sha": "a" * 40, "lastModified": "2026-01-01T00:00:00Z"},
    ):
        with pytest.raises(SourceMonitorError):
            parse_huggingface_metadata(json.dumps(value).encode(), "bettergovph/gaa")

    for payload in (b"not json", b"[]"):
        with pytest.raises(SourceMonitorError):
            parse_huggingface_metadata(payload, "bettergovph/gaa")

    for modified in (None, "today"):
        value = {
            "id": "bettergovph/gaa",
            "sha": "a" * 40,
            "lastModified": modified,
        }
        with pytest.raises(SourceMonitorError, match="modification time"):
            parse_huggingface_metadata(json.dumps(value).encode(), "bettergovph/gaa")


def test_rejects_invalid_pcab_transition_date() -> None:
    with pytest.raises(SourceMonitorError, match="ISO format"):
        review_pcab_transition(
            b"{}",
            b"{}",
            reviewed_sha256="a" * 64,
            observed_sha256="b" * 64,
            observed_on="today",
        )


def test_extracts_only_normalized_2026_dbm_release_entries() -> None:
    payload = b"""
    <div id="rlta-panel-2026"><div>
      <a href="/index.php?view=article&amp;id=1&amp;catid=307">January</a>
      <a href="https://www.dbm.gov.ph/index.php?view=article&amp;id=9&amp;catid=307"> September </a>
    </div></div>
    <div id="rlta-panel-2025"><a href="/old">January</a></div>
    """

    records = parse_dbm_release_catalog(payload, 2026)

    assert records == (
        {
            "label": "January",
            "url": "https://www.dbm.gov.ph/index.php?catid=307&id=1&view=article",
        },
        {
            "label": "September",
            "url": "https://www.dbm.gov.ph/index.php?catid=307&id=9&view=article",
        },
    )


def test_rejects_missing_or_duplicate_dbm_catalog_entries() -> None:
    with pytest.raises(SourceMonitorError, match="2026"):
        parse_dbm_release_catalog(b"<div id='rlta-panel-2025'></div>", 2026)
    duplicate = b"""
    <div id="rlta-panel-2026">
      <a href="/one">January</a><a href="/two">January</a>
    </div>
    """
    with pytest.raises(SourceMonitorError, match="duplicate"):
        parse_dbm_release_catalog(duplicate, 2026)
    assert parse_dbm_release_catalog(b"<main></main>", 2027, allow_empty=True) == ()
    escaped = b'<div id="rlta-panel-2026"><a href="https://example.com/file">Bad</a></div>'
    with pytest.raises(SourceMonitorError, match="official origin"):
        parse_dbm_release_catalog(escaped, 2026)


def test_compares_observations_without_hiding_added_or_changed_records() -> None:
    baseline = {
        "datasets": {"gaa": {"revision": "a" * 40}},
        "dbm_releases": [{"label": "January", "url": "https://example/1"}],
        "dbm_next_releases": [],
        "districts": {"revision": "b" * 40, "total": 254},
        "pcab": {"minimum_records": 10},
        "hgab_2027": {"source_commit": "d" * 40},
    }
    unchanged = {
        "datasets": {"gaa": {"revision": "a" * 40, "last_modified": "now"}},
        "dbm_releases": [{"label": "January", "url": "https://example/1"}],
        "dbm_next_releases": [],
        "districts": {"revision": "b" * 40, "total": 254, "built_at": "now"},
        "pcab": {"sha256": "c" * 64, "records": 11},
        "hgab_2027": {"source_commit": "d" * 40, "built_at": "now"},
    }
    assert compare_observations(baseline, unchanged) == ()

    changed = {
        **unchanged,
        "dbm_releases": [
            *unchanged["dbm_releases"],
            {"label": "February", "url": "https://example/2"},
        ],
    }
    differences = compare_observations(baseline, changed)
    assert differences == ("dbm_releases: catalogue changed",)

    regressed = {
        **unchanged,
        "pcab": {"sha256": "d" * 64, "records": 9},
    }
    assert compare_observations(baseline, regressed) == (
        "pcab: records fell below the reviewed floor",
    )

    hgab_changed = {
        **unchanged,
        "hgab_2027": {"source_commit": "e" * 40, "built_at": "later"},
    }
    assert compare_observations(baseline, hgab_changed) == (
        "hgab_2027: source commit changed",
    )
