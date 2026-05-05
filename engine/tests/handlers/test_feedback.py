"""Tests for engine.handlers.feedback — POST /api/feedback."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from engine.core.db import Article, ArticleFeedback


@pytest.fixture
def seeded_article(test_engine, seeded_vertical) -> str:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        a = Article(
            vertical_id=seeded_vertical,
            hash="h1",
            slug="test-story",
            title="Test story",
            link="https://example.com/x",
            source="https://example.com/feed",
            feed_region="US",
            summary="x",
            summary_source="llm",
            published_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        )
        s.add(a)
        s.commit()
    return "test-story"


def test_happy_path_inserts_row(client, seeded_article, test_engine) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": seeded_article,
            "issue_kind": "factual_error",
            "note": "Citation count appears off by 10x.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "status": "received"}

    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        rows = s.execute(select(ArticleFeedback)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.issue_kind == "factual_error"
        assert row.note.startswith("Citation count")
        assert len(row.reporter_ip_hash) == 64


def test_honeypot_trip_returns_200_silently_no_row(
    client, seeded_article, test_engine
) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": seeded_article,
            "issue_kind": "factual_error",
            "note": "spammy spam",
            "hp": "i-am-a-bot",
        },
    )
    assert r.status_code == 200
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        rows = s.execute(select(ArticleFeedback)).scalars().all()
        assert rows == []


def test_invalid_issue_kind_returns_422(client, seeded_article) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": seeded_article,
            "issue_kind": "made-up-category",
        },
    )
    assert r.status_code == 422
    assert "issue_kind must be one of" in r.json().get("detail", "")


def test_unknown_vertical_returns_404(client, seeded_article) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "ghost",
            "slug": seeded_article,
            "issue_kind": "spam",
        },
    )
    assert r.status_code == 404


def test_unknown_slug_returns_404(client, seeded_article) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": "no-such-story",
            "issue_kind": "spam",
        },
    )
    assert r.status_code == 404
    assert "article not found" in r.json().get("detail", "")


def test_missing_required_field_returns_422(client, seeded_article) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": seeded_article,
            # missing issue_kind
        },
    )
    assert r.status_code == 422


def test_oversized_note_returns_422(
    client, seeded_article, test_engine
) -> None:
    r = client.post(
        "/api/feedback",
        data={
            "vertical": "modelwatch",
            "slug": seeded_article,
            "issue_kind": "other",
            "note": "a" * 1500,
        },
    )
    assert r.status_code == 422
