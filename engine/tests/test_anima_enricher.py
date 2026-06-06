"""Tests for engine.core.anima_enricher — §3 contract derivation + calendar."""

from __future__ import annotations

from datetime import datetime, timezone

from engine.core import anima_enricher as ae


def _utc(y: int, m: int, d: int, h: int = 0) -> datetime:
    return datetime(y, m, d, h, tzinfo=timezone.utc)


# ---- display_source / host_of ----


def test_host_of_strips_www():
    assert ae.host_of("https://www.bls.gov/cpi/") == "bls.gov"


def test_display_source_maps_primary_agencies():
    assert ae.display_source("https://www.federalreserve.gov/x") == "Fed"
    assert ae.display_source("https://fred.stlouisfed.org/series/x") == "FRED"
    assert ae.display_source("https://www.bls.gov/news.release") == "BLS"


def test_display_source_falls_back_to_host():
    assert ae.display_source("https://unknown.example.com/x") == "unknown.example.com"


# ---- lane ----


def test_derive_lane_first_mapped_label_wins():
    assert ae.derive_lane(["retirement-planning", "taxes"]) == "The Cost of Waiting"
    assert ae.derive_lane(["taxes", "retirement-planning"]) == "What It Really Costs"
    assert ae.derive_lane(["banking"]) == "Where Your Money Goes"


def test_derive_lane_unmapped_labels_default():
    assert ae.derive_lane(["something-odd"]) == "Money, Explained"


def test_derive_lane_no_labels_is_none():
    assert ae.derive_lane([]) is None


# ---- evergreen ----


def test_derive_evergreen_true_for_explainer_topic():
    assert ae.derive_evergreen(["taxes"]) is True


def test_derive_evergreen_false_for_newsy_only():
    assert ae.derive_evergreen(["layoff-strategy"]) is False
    assert ae.derive_evergreen([]) is False


# ---- key_stat ----


def test_key_stat_prefers_headline_match():
    numerics = [{"value": "$1.66T", "context": "deficit"}, {"value": "23%"}]
    assert ae.derive_key_stat(numerics, "Deficit hits $1.66T this year") == "$1.66T"


def test_key_stat_parses_headline_when_no_numerics():
    assert ae.derive_key_stat([], "Social Security runs dry in 2033") == "2033"


def test_key_stat_falls_back_to_first_numeric():
    numerics = [{"value": "$300 billion"}]
    assert ae.derive_key_stat(numerics, "A headline with no number") == "$300 billion"


def test_key_stat_scans_narrative_last():
    got = ae.derive_key_stat([], "No number here", narrative="It costs 4.5% annually.")
    assert got == "4.5%"


def test_key_stat_none_when_nothing():
    assert ae.derive_key_stat([], "No number here", narrative="Still nothing.") is None


# ---- primary_source_url ----


def test_primary_source_prefers_primary_host():
    sources = [
        {"host": "bloomberg.com", "agency_class": "A", "source_url": "https://bloomberg.com/x"},
        {"host": "bls.gov", "agency_class": "D", "source_url": "https://bls.gov/cpi"},
    ]
    assert ae.pick_primary_source_url(sources) == "https://bls.gov/cpi"


def test_primary_source_subdomain_matches():
    sources = [
        {"host": "data.bls.gov", "agency_class": "A", "source_url": "https://data.bls.gov/x"},
    ]
    assert ae.pick_primary_source_url(sources) == "https://data.bls.gov/x"


def test_primary_source_falls_back_to_class_d():
    sources = [
        {"host": "fidelity.com", "agency_class": "D", "source_url": "https://fidelity.com/x"},
    ]
    assert ae.pick_primary_source_url(sources) == "https://fidelity.com/x"


def test_primary_source_none_when_no_primary():
    sources = [
        {"host": "bloomberg.com", "agency_class": "A", "source_url": "https://bloomberg.com/x"},
    ]
    assert ae.pick_primary_source_url(sources) is None


# ---- momentum ----


def test_momentum_fresh_multi_source_is_high():
    now = _utc(2026, 6, 6, 12)
    m = ae.compute_momentum(5, _utc(2026, 6, 6, 10), now=now)
    assert m > 0.9


def test_momentum_old_single_source_is_low():
    now = _utc(2026, 6, 6, 12)
    m = ae.compute_momentum(1, _utc(2026, 5, 1), now=now)
    assert m < 0.2


def test_momentum_in_unit_range():
    now = _utc(2026, 6, 6, 12)
    for sc in (0, 1, 3, 5, 20):
        m = ae.compute_momentum(sc, _utc(2026, 6, 6), now=now)
        assert 0.0 <= m <= 1.0


def test_momentum_handles_missing_date():
    assert 0.0 <= ae.compute_momentum(3, None) <= 1.0


# ---- story_to_contract ----


def test_story_to_contract_shape_and_values():
    rec = ae.story_to_contract(
        story_id=42,
        headline="Social Security trust fund empties in 2033",
        summary="The runway just got shorter.",
        url="https://vested.news/story/ss-2033",
        labels=["retirement-planning"],
        numerics=[{"value": "2033", "context": "depletion"}],
        sources=[
            {"host": "ssa.gov", "agency_class": "D", "source_url": "https://ssa.gov/oact/TR/"},
            {"host": "bloomberg.com", "agency_class": "A", "source_url": "https://bloomberg.com/y"},
        ],
        entities=["Social Security"],
        narrative="The trust fund is projected to deplete by 2033[1].",
        published_at=_utc(2026, 6, 6, 10),
        now=_utc(2026, 6, 6, 12),
    )
    assert rec["id"] == "42"
    assert rec["key_stat"] == "2033"
    assert rec["primary_source_url"] == "https://ssa.gov/oact/TR/"
    assert rec["lane"] == "The Cost of Waiting"
    assert rec["evergreen"] is True
    assert rec["entities"] == ["Social Security"]
    assert rec["source"] == "vested.news"
    assert 0.0 <= rec["momentum"] <= 1.0
    assert rec["published_at"].endswith("+00:00")
    # Contract keys exactly match §3.
    assert set(rec.keys()) == {
        "id", "headline", "summary", "url", "source",
        "primary_source_url", "key_stat", "entities",
        "lane", "evergreen", "published_at", "momentum",
    }


# ---- calendar ----


def test_load_calendar_reads_vested(monkeypatch, tmp_path):
    import engine.core.config as cfg

    vdir = tmp_path / "vested"
    vdir.mkdir()
    (vdir / "calendar.yaml").write_text(
        "releases:\n"
        "  - id: cpi-x\n"
        "    name: CPI\n"
        "    agency: BLS\n"
        "    date: 2026-12-01\n"
        "    primary_source_url: https://www.bls.gov/cpi/\n"
        "  - id: past-x\n"
        "    name: Old\n"
        "    agency: BLS\n"
        "    date: 2026-01-01\n"
        "    primary_source_url: https://www.bls.gov/x\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "VERTICALS_DIR", tmp_path)

    rows = ae.load_calendar("vested", today=_utc(2026, 6, 6))
    assert [r["id"] for r in rows] == ["past-x", "cpi-x"]  # date-sorted
    upcoming = {r["id"]: r["is_upcoming"] for r in rows}
    assert upcoming == {"past-x": False, "cpi-x": True}


def test_load_calendar_missing_file_is_empty(monkeypatch, tmp_path):
    import engine.core.config as cfg

    (tmp_path / "vested").mkdir()
    monkeypatch.setattr(cfg, "VERTICALS_DIR", tmp_path)
    assert ae.load_calendar("vested") == []


def test_load_calendar_skips_malformed_rows(monkeypatch, tmp_path):
    import engine.core.config as cfg

    vdir = tmp_path / "vested"
    vdir.mkdir()
    (vdir / "calendar.yaml").write_text(
        "releases:\n"
        "  - name: no id or date\n"
        "  - id: bad-date\n"
        "    date: not-a-date\n"
        "  - id: good\n"
        "    date: 2026-07-01\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "VERTICALS_DIR", tmp_path)
    rows = ae.load_calendar("vested", today=_utc(2026, 6, 6))
    assert [r["id"] for r in rows] == ["good"]
