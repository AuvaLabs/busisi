from __future__ import annotations

import json

import pytest

from engine.budget_watchdog.source_monitor import (
    SourceMonitorError,
    compare_observations,
    parse_dbm_release_catalog,
    parse_huggingface_metadata,
)


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


def test_compares_observations_without_hiding_added_or_changed_records() -> None:
    baseline = {
        "datasets": {"gaa": {"revision": "a" * 40}},
        "dbm_releases": [{"label": "January", "url": "https://example/1"}],
        "dbm_next_releases": [],
        "districts": {"revision": "b" * 40, "total": 254},
        "pcab": {"sha256": "c" * 64, "records": 10},
    }
    unchanged = {
        "datasets": {"gaa": {"revision": "a" * 40, "last_modified": "now"}},
        "dbm_releases": [{"label": "January", "url": "https://example/1"}],
        "dbm_next_releases": [],
        "districts": {"revision": "b" * 40, "total": 254, "built_at": "now"},
        "pcab": {"sha256": "c" * 64, "records": 10},
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
