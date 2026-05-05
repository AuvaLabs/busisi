"""Tests for engine.core.indexnow."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import indexnow as inx
from engine.core.db import Article, Base, Vertical


@pytest.fixture
def test_engine(monkeypatch: pytest.MonkeyPatch):
    eng = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "_engine", eng)
    yield eng


@pytest.fixture
def vroot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point VERTICALS_DIR at a tmp tree so .indexnow_key writes don't
    pollute the repo."""
    import engine.core.config as cfg

    root = tmp_path / "verticals" / "embedding"
    root.mkdir(parents=True)
    monkeypatch.setattr(cfg, "VERTICALS_DIR", tmp_path / "verticals")
    return root


@pytest.fixture
def seeded(test_engine):
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    now = datetime.now(timezone.utc)
    with SM() as s:
        v = Vertical(name="embedding", display_name="The Embedding Report")
        s.add(v)
        s.commit()
        s.refresh(v)
        s.add_all(
            [
                Article(
                    vertical_id=v.id, hash="h1", slug="recent-story",
                    title="Recent", link="https://example.com/r",
                    source="https://example.com/feed", feed_region="US",
                    summary="x", summary_source="llm",
                    published_at=now - timedelta(hours=2),
                    curator_tier="standard",
                ),
                Article(
                    vertical_id=v.id, hash="h2", slug="skip-tier",
                    title="Forum", link="https://example.com/f",
                    source="https://example.com/feed", feed_region="US",
                    summary="x", summary_source="feed",
                    published_at=now - timedelta(hours=3),
                    curator_tier="skip",
                ),
                Article(
                    vertical_id=v.id, hash="h3", slug="too-old",
                    title="Old", link="https://example.com/o",
                    source="https://example.com/feed", feed_region="US",
                    summary="x", summary_source="llm",
                    published_at=now - timedelta(hours=72),
                    curator_tier="standard",
                ),
            ]
        )
        s.commit()


class TestKey:
    def test_get_or_create_idempotent(self, vroot) -> None:
        k1 = inx.get_or_create_key("embedding")
        k2 = inx.get_or_create_key("embedding")
        assert k1 == k2
        assert len(k1) == 32
        assert all(c in "0123456789abcdef" for c in k1)

    def test_key_persisted_to_disk(self, vroot) -> None:
        k = inx.get_or_create_key("embedding")
        path = vroot / ".indexnow_key"
        assert path.exists()
        assert path.read_text() == k


class TestCollectRecentUrls:
    def test_excludes_skip_tier(self, test_engine, seeded) -> None:
        urls = inx.collect_recent_urls("embedding", since_hours=24)
        assert any("recent-story" in u for u in urls)
        assert not any("skip-tier" in u for u in urls)

    def test_includes_front_page(self, test_engine, seeded) -> None:
        urls = inx.collect_recent_urls("embedding", since_hours=24)
        assert urls[0].endswith("/")
        assert "story" not in urls[0].rstrip("/").rsplit("/", 1)[-1]

    def test_since_hours_filter(self, test_engine, seeded) -> None:
        urls = inx.collect_recent_urls("embedding", since_hours=24)
        assert not any("too-old" in u for u in urls)

    def test_unknown_vertical_raises(self, test_engine) -> None:
        with pytest.raises(ValueError):
            inx.collect_recent_urls("ghost", since_hours=24)


class TestSubmitUrls:
    def test_dry_run_returns_payload(self) -> None:
        status, body = inx.submit_urls(
            "embedding.report",
            "abcdef" * 4 + "0123" * 2,
            ["https://embedding.report/", "https://embedding.report/story/x/"],
            dry_run=True,
        )
        assert status == 0
        d = json.loads(body)
        assert d["host"] == "embedding.report"
        assert d["keyLocation"].endswith(".txt")
        assert len(d["urlList"]) == 2

    def test_empty_url_list_no_op(self) -> None:
        status, body = inx.submit_urls(
            "embedding.report", "k" * 32, [], dry_run=True
        )
        assert status == 0


class TestPing:
    def test_ping_dry_run_uses_canonical_base(
        self, test_engine, seeded, vroot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "EMBEDDING_CANONICAL_BASE", "https://embedding.report"
        )
        n, status = inx.ping_recent_urls("embedding", dry_run=True)
        assert n >= 1
        assert status == 0
