"""Tests for engine.core.anima_topics — deterministic topic clustering."""

from __future__ import annotations

from engine.core import anima_topics as t


def S(
    sid,
    momentum,
    entities,
    *,
    key_stat="X",
    source="https://www.bls.gov/x",
    lane="Money, Explained",
    headline=None,
    evergreen=False,
    published="2026-06-06T00:00:00+00:00",
):
    return {
        "id": sid,
        "headline": headline or f"Story {sid}",
        "summary": f"summary {sid}",
        "url": f"https://vested.news/story/{sid}",
        "key_stat": key_stat,
        "primary_source_url": source,
        "lane": lane,
        "entities": entities,
        "momentum": momentum,
        "evergreen": evergreen,
        "published_at": published,
    }


def test_clusters_by_shared_entity_with_lead():
    topics = t.build_topics(
        [S(1, 0.5, ["Fed"]), S(2, 0.8, ["Fed"]), S(3, 0.4, ["IRS"])],
        min_cluster=2,
    )
    fed = next(x for x in topics if x["theme_entity"] == "Fed")
    assert fed["n_stories"] == 2
    assert fed["title"] == "Story 2"  # lead = highest momentum
    assert {f["claim"] for f in fed["facts"]} == {"Story 1", "Story 2"}
    assert fed["momentum"] == 0.85  # max 0.8 + 0.05 corroboration bonus


def test_single_story_with_stat_becomes_topic():
    topics = t.build_topics([S(1, 0.6, [], key_stat="2033")], min_cluster=2)
    assert len(topics) == 1
    assert topics[0]["theme_entity"] is None
    assert topics[0]["n_stories"] == 1
    assert topics[0]["id"] == "topic-story-1"


def test_single_without_stat_or_source_dropped():
    assert t.build_topics([S(1, 0.6, [], key_stat=None, source=None)], min_cluster=2) == []


def test_ranked_by_momentum_desc():
    topics = t.build_topics([S(1, 0.2, []), S(2, 0.9, [])], min_cluster=2)
    moms = [x["momentum"] for x in topics]
    assert moms == sorted(moms, reverse=True)


def test_fact_pack_carries_stat_and_source():
    topics = t.build_topics(
        [S(1, 0.5, ["Fed"], key_stat="5%", source="https://www.federalreserve.gov/a")],
        min_cluster=1,  # entity cluster of 1 allowed
    )
    top = topics[0]
    assert top["facts"][0]["key_stat"] == "5%"
    assert top["facts"][0]["source_url"] == "https://www.federalreserve.gov/a"
    assert "https://www.federalreserve.gov/a" in top["sources"]
    assert top["theme_entity"] == "Fed"


def test_story_claimed_by_one_cluster_only():
    stories = [S(1, 0.5, ["Fed", "Rates"]), S(2, 0.5, ["Fed"]), S(3, 0.5, ["Rates"])]
    topics = t.build_topics(stories, min_cluster=2)
    fed = next(x for x in topics if x["theme_entity"] == "Fed")
    assert set(fed["story_ids"]) == {"1", "2"}  # Fed (alpha-first, size 2) claims 1,2
    # 3 left alone (Rates now has <2) → single topic
    singles = [x for x in topics if x["theme_entity"] is None]
    assert any(x["story_ids"] == ["3"] for x in singles)


def test_evergreen_and_lane_aggregate():
    topics = t.build_topics(
        [
            S(1, 0.5, ["Fed"], lane="Where Your Money Goes", evergreen=False),
            S(2, 0.6, ["Fed"], lane="Where Your Money Goes", evergreen=True),
        ],
        min_cluster=2,
    )
    fed = topics[0]
    assert fed["lane"] == "Where Your Money Goes"
    assert fed["evergreen"] is True  # any member evergreen


def test_limit_caps_results():
    stories = [S(i, 0.1 * (i % 9), [], key_stat=f"{i}") for i in range(30)]
    assert len(t.build_topics(stories, min_cluster=2, limit=5)) == 5
