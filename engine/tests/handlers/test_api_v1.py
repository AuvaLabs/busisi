"""Tests for engine.handlers.api_v1 — public read API at /api/v1/*."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from engine.core.db import Article, Entity


def _utc(y: int, m: int, d: int, h: int = 0, mn: int = 0) -> datetime:
    return datetime(y, m, d, h, mn, tzinfo=timezone.utc)


@pytest.fixture
def seeded_articles(test_engine, seeded_vertical):
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        s.add_all(
            [
                Article(
                    vertical_id=seeded_vertical,
                    hash="h1",
                    slug="anthropic-1m-context",
                    title="Anthropic doubles context window",
                    link="https://anthropic.com/news/1m",
                    source="https://anthropic.com/feed",
                    feed_region="US",
                    summary="Claude Sonnet 4.6 ships 1M context.",
                    summary_source="llm",
                    published_at=_utc(2026, 5, 4, 14, 22),
                    curator_tier="standard",
                ),
                Article(
                    vertical_id=seeded_vertical,
                    hash="h2",
                    slug="forum-thread",
                    title="Forum: anyone using GPT-5?",
                    link="https://example.com/thread",
                    source="https://example.com/feed",
                    feed_region="US",
                    summary="A discussion thread.",
                    summary_source="feed",
                    published_at=_utc(2026, 5, 3, 10, 0),
                    curator_tier="skip",
                ),
                Article(
                    vertical_id=seeded_vertical,
                    hash="h3",
                    slug="researcher-piece",
                    title="Deep dive on transformer scaling",
                    link="https://research.example.com/scaling",
                    source="https://research.example.com/feed",
                    feed_region="EU",
                    summary="A long-form piece.",
                    summary_source="llm",
                    published_at=_utc(2026, 5, 1, 9, 0),
                    curator_tier="researcher",
                ),
            ]
        )
        s.commit()


@pytest.fixture
def seeded_entities(test_engine, seeded_vertical):
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        s.add_all(
            [
                Entity(
                    vertical_id=seeded_vertical,
                    type="lab",
                    slug="anthropic",
                    name="Anthropic",
                    first_seen_at=_utc(2026, 1, 1),
                    last_seen_at=_utc(2026, 5, 4),
                ),
                Entity(
                    vertical_id=seeded_vertical,
                    type="model",
                    slug="claude-sonnet-4-6",
                    name="Claude Sonnet 4.6",
                    first_seen_at=_utc(2026, 4, 1),
                    last_seen_at=_utc(2026, 5, 4),
                ),
            ]
        )
        s.commit()


def test_api_v1_health(client) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "version": "v1"}


def test_articles_returns_non_skip_rows_only(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=modelwatch&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["vertical"] == "modelwatch"
    assert body["count"] == 2  # skip-tier excluded
    slugs = [d["slug"] for d in body["data"]]
    assert "anthropic-1m-context" in slugs
    assert "researcher-piece" in slugs
    assert "forum-thread" not in slugs


def test_articles_orders_by_published_desc(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=modelwatch")
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["slug"] == "anthropic-1m-context"


def test_articles_since_filter(client, seeded_articles) -> None:
    r = client.get(
        "/api/v1/articles?vertical=modelwatch&since=2026-05-04T00:00:00Z"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["data"][0]["slug"] == "anthropic-1m-context"


def test_articles_invalid_since_400(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=modelwatch&since=not-a-date")
    assert r.status_code == 400


def test_articles_unknown_vertical_404(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=ghost")
    assert r.status_code == 404


def test_articles_iso_format_dates(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=modelwatch")
    assert r.status_code == 200
    pub = r.json()["data"][0]["published_at"]
    assert pub.endswith("+00:00")
    datetime.fromisoformat(pub)


def test_entities_happy_path(client, seeded_entities) -> None:
    r = client.get("/api/v1/entities?vertical=modelwatch")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    types = {d["type"] for d in body["data"]}
    assert types == {"lab", "model"}


def test_entities_type_filter(client, seeded_entities) -> None:
    r = client.get("/api/v1/entities?vertical=modelwatch&type=lab")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["data"][0]["slug"] == "anthropic"


def test_entities_unknown_vertical_404(client, seeded_entities) -> None:
    r = client.get("/api/v1/entities?vertical=ghost")
    assert r.status_code == 404


def test_articles_limit_validation(client, seeded_articles) -> None:
    r = client.get("/api/v1/articles?vertical=modelwatch&limit=10000")
    assert r.status_code == 422
