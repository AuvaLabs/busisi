"""Tests for the Anima channel-feeder endpoints (/api/v1/anima/*)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from engine.core.db import (
    Article,
    ArticleEntity,
    Entity,
    Story,
    StoryArticle,
    StorySource,
)


def _utc(y: int, m: int, d: int, h: int = 0) -> datetime:
    return datetime(y, m, d, h, tzinfo=timezone.utc)


@pytest.fixture
def seeded_anima(test_engine, seeded_vertical):
    """One published Story with a primary BLS source + numerics + entity."""
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        a1 = Article(
            vertical_id=seeded_vertical,
            hash="anima-h1",
            slug="cpi-primary",
            title="Inflation cooled to 2.3% in May",
            link="https://vested.news/story/cpi-may",
            source="https://bls.gov/feed",
            feed_region="US",
            summary="Prices rose 2.3% year over year.",
            summary_source="llm",
            published_at=_utc(2026, 6, 6, 9),
            labels=[{"label": "taxes", "confidence": 80}],
            structured_extract={"numerics": [{"value": "2.3%", "context": "CPI YoY"}]},
        )
        a2 = Article(
            vertical_id=seeded_vertical,
            hash="anima-h2",
            slug="cpi-secondary",
            title="CPI report: inflation eases",
            link="https://bloomberg.com/cpi",
            source="https://bloomberg.com/feed",
            feed_region="US",
            summary="Coverage of the CPI print.",
            summary_source="feed",
            published_at=_utc(2026, 6, 6, 10),
            labels=[{"label": "banking", "confidence": 40}],
        )
        s.add_all([a1, a2])
        s.commit()

        ent = Entity(
            vertical_id=seeded_vertical,
            type="employer",
            slug="bls",
            name="Bureau of Labor Statistics",
        )
        s.add(ent)
        s.commit()

        published = Story(
            vertical_id=seeded_vertical,
            canonical_headline="Inflation cooled to 2.3% in May",
            primary_published_at=_utc(2026, 6, 6, 9),
            importance=0.8,
            state="published",
            narrative="CPI rose 2.3%[1] in May.",
            why_this_matters="Slower inflation eases rate-cut pressure.",
            narrative_version=1,
        )
        draft = Story(
            vertical_id=seeded_vertical,
            canonical_headline="Unpublished cluster",
            primary_published_at=_utc(2026, 6, 5, 9),
            importance=0.2,
            state="draft",
        )
        s.add_all([published, draft])
        s.commit()

        s.add_all(
            [
                StoryArticle(story_id=published.id, article_id=a1.id, is_primary=True),
                StoryArticle(story_id=published.id, article_id=a2.id, is_primary=False),
                StorySource(
                    story_id=published.id,
                    source_url="https://www.bls.gov/cpi/",
                    host="bls.gov",
                    agency_class="D",
                    cited_as_n=1,
                    article_id=a1.id,
                ),
                StorySource(
                    story_id=published.id,
                    source_url="https://bloomberg.com/cpi",
                    host="bloomberg.com",
                    agency_class="A",
                    cited_as_n=2,
                    article_id=a2.id,
                ),
                ArticleEntity(article_id=a1.id, entity_id=ent.id),
            ]
        )
        s.commit()


def test_anima_feed_emits_contract(client, seeded_anima) -> None:
    r = client.get("/api/v1/anima/feed?vertical=modelwatch")
    assert r.status_code == 200
    body = r.json()
    assert body["vertical"] == "modelwatch"
    assert "generated_at" in body
    assert body["count"] == 1  # only published
    story = body["stories"][0]

    # §3 contract keys exactly.
    assert set(story.keys()) == {
        "id", "headline", "summary", "url", "source",
        "primary_source_url", "key_stat", "entities",
        "lane", "evergreen", "published_at", "momentum",
    }
    assert story["headline"] == "Inflation cooled to 2.3% in May"
    assert story["url"] == "https://vested.news/story/cpi-may"
    assert story["key_stat"] == "2.3%"
    assert story["primary_source_url"] == "https://www.bls.gov/cpi/"
    assert story["lane"] == "What It Really Costs"  # taxes (conf 80) beats banking
    assert story["evergreen"] is True
    assert story["entities"] == ["Bureau of Labor Statistics"]
    assert story["summary"] == "Slower inflation eases rate-cut pressure."
    assert 0.0 <= story["momentum"] <= 1.0


def test_anima_feed_unknown_vertical_404(client) -> None:
    r = client.get("/api/v1/anima/feed?vertical=ghost")
    assert r.status_code == 404


def test_anima_feed_limit_validation(client) -> None:
    r = client.get("/api/v1/anima/feed?vertical=modelwatch&limit=99999")
    assert r.status_code == 422


def test_anima_feed_since_filter(client, seeded_anima) -> None:
    r = client.get(
        "/api/v1/anima/feed?vertical=modelwatch&since=2026-07-01T00:00:00Z"
    )
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_anima_feed_invalid_since_400(client, seeded_anima) -> None:
    r = client.get("/api/v1/anima/feed?vertical=modelwatch&since=nope")
    assert r.status_code == 400


# ---- calendar ----


def test_anima_calendar_reads_vested(client, repo_verticals_dir) -> None:
    # repo_verticals_dir points VERTICALS_DIR at the in-repo verticals/ which
    # ships verticals/vested/calendar.yaml.
    r = client.get("/api/v1/anima/calendar?vertical=vested")
    assert r.status_code == 200
    body = r.json()
    assert body["vertical"] == "vested"
    assert body["count"] >= 1
    ids = {row["id"] for row in body["releases"]}
    assert "ss-trustees-2026" in ids
    for row in body["releases"]:
        assert row["primary_source_url"].startswith("http")
        assert "is_upcoming" in row


def test_anima_calendar_upcoming_only_filters(client, repo_verticals_dir) -> None:
    r = client.get("/api/v1/anima/calendar?vertical=vested&upcoming_only=true")
    assert r.status_code == 200
    body = r.json()
    assert body["upcoming_only"] is True
    assert all(row["is_upcoming"] for row in body["releases"])


def test_anima_calendar_unknown_vertical_traversal_404(client) -> None:
    r = client.get("/api/v1/anima/calendar?vertical=../etc")
    assert r.status_code == 404


# ---- topics ----


@pytest.fixture
def seeded_topics(test_engine, seeded_vertical):
    """Two recent published stories sharing the 'Federal Reserve' entity, each
    with a Fed primary source + key stat — should cluster into one topic."""
    now = datetime.now(timezone.utc)
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        ent = Entity(
            vertical_id=seeded_vertical, type="employer",
            slug="federal-reserve", name="Federal Reserve",
        )
        s.add(ent)
        s.commit()
        for i, hrs in enumerate([2, 5]):
            a = Article(
                vertical_id=seeded_vertical,
                hash=f"tp-h{i}",
                slug=f"fed-{i}",
                title=f"Fed holds rates as inflation cools to {2 + i}.1%",
                link=f"https://vested.news/story/fed-{i}",
                source="https://federalreserve.gov/feed",
                feed_region="US",
                summary="The Fed kept rates steady.",
                summary_source="llm",
                published_at=now - timedelta(hours=hrs),
                labels=[{"label": "brokerage-investing", "confidence": 80}],
                structured_extract={"numerics": [{"value": f"{2 + i}.1%"}]},
            )
            s.add(a)
            s.commit()
            story = Story(
                vertical_id=seeded_vertical,
                canonical_headline=a.title,
                primary_published_at=now - timedelta(hours=hrs),
                importance=0.8 - 0.1 * i,
                state="published",
                narrative=f"The Fed held rates[1] as inflation cooled to {2 + i}.1%.",
                why_this_matters="Rate path shapes savings and mortgage costs.",
                narrative_version=1,
            )
            s.add(story)
            s.commit()
            s.add_all([
                StoryArticle(story_id=story.id, article_id=a.id, is_primary=True),
                StorySource(
                    story_id=story.id,
                    source_url="https://www.federalreserve.gov/monetarypolicy.htm",
                    host="federalreserve.gov",
                    agency_class="D",
                    cited_as_n=1,
                    article_id=a.id,
                ),
                ArticleEntity(article_id=a.id, entity_id=ent.id),
            ])
            s.commit()


def test_anima_topics_clusters_sourced_stories(client, seeded_topics) -> None:
    r = client.get("/api/v1/anima/topics?vertical=modelwatch&min_cluster=2")
    assert r.status_code == 200
    body = r.json()
    assert body["vertical"] == "modelwatch"
    assert "generated_at" in body and body["story_pool"] >= 2
    assert body["count"] >= 1
    topic = next(t for t in body["topics"] if t["theme_entity"] == "Federal Reserve")
    assert topic["n_stories"] == 2
    assert topic["lane"] == "Where Your Money Goes"  # brokerage-investing -> lane
    assert len(topic["facts"]) == 2
    # every fact is sourced to the Fed primary source
    assert all(f["source_url"].startswith("https://www.federalreserve.gov") for f in topic["facts"])
    assert "https://www.federalreserve.gov/monetarypolicy.htm" in topic["sources"]
    assert topic["story_ids"]  # ids present for Anima to dereference


def test_anima_topics_unknown_vertical_404(client) -> None:
    r = client.get("/api/v1/anima/topics?vertical=ghost")
    assert r.status_code == 404


def test_anima_topics_limit_validation(client) -> None:
    r = client.get("/api/v1/anima/topics?vertical=modelwatch&limit=9999")
    assert r.status_code == 422
