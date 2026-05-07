"""Tests for engine.core.story_lifecycle (R7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.config as _cfg_module
import engine.core.db as db_module
from engine.core import story_lifecycle as sl
from engine.core.db import (
    Article,
    Base,
    BotHit,
    CitationEvent,
    Story,
    StoryArticle,
    Vertical,
)


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


def _write_sources(tmp_path, monkeypatch: pytest.MonkeyPatch, lines: str) -> None:
    v_dir = tmp_path / "verticals" / "embedding"
    v_dir.mkdir(parents=True)
    (v_dir / "sources.yaml").write_text(lines, encoding="utf-8")
    monkeypatch.setattr(_cfg_module, "VERTICALS_DIR", tmp_path / "verticals")


def _seed(eng, *, sources_classes: list[str], age_minutes: int = 60) -> int:
    """Create a Vertical, Articles (one per class), Story (state='draft')."""
    SM = sessionmaker(eng, expire_on_commit=False, future=True)
    now = datetime.now(timezone.utc)
    with SM() as s:
        v = Vertical(name="embedding", display_name="X")
        s.add(v)
        s.commit()
        article_ids = []
        for i, cls in enumerate(sources_classes):
            host = f"src-{cls.lower()}-{i}.example.com"
            a = Article(
                vertical_id=v.id,
                hash=f"h-{i}",
                slug=f"slug-{i}",
                title=f"Title {i}",
                link=f"https://{host}/p/{i}",
                source=f"https://{host}/feed",
                body="A" * 500,
                summary="",
                published_at=now,
                structured_extract={"lead_claim": "x"},
                extract_version=1,
            )
            s.add(a)
            s.commit()
            article_ids.append(a.id)
        story = Story(
            vertical_id=v.id,
            canonical_headline="X",
            primary_published_at=now,
            importance=0.1,
            state="draft",
            created_at=now - timedelta(minutes=age_minutes),
        )
        s.add(story)
        s.commit()
        for aid in article_ids:
            s.add(
                StoryArticle(
                    story_id=story.id,
                    article_id=aid,
                    is_primary=(aid == article_ids[0]),
                )
            )
        s.commit()
        return story.id


class TestMarkReady:
    def test_two_class_a_promotes_to_ready(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _seed(test_engine, sources_classes=["A", "A"])
        _write_sources(
            tmp_path,
            monkeypatch,
            "- url: https://src-a-0.example.com/feed\n  agency_class: A\n"
            "- url: https://src-a-1.example.com/feed\n  agency_class: A\n",
        )
        counts = sl.mark_ready("embedding")
        assert counts["promoted"] == 1
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            assert s.get(Story, sid).state == "ready"

    def test_one_a_one_f_does_not_promote(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _seed(test_engine, sources_classes=["A", "F"])
        _write_sources(
            tmp_path,
            monkeypatch,
            "- url: https://src-a-0.example.com/feed\n  agency_class: A\n"
            "- url: https://src-f-1.example.com/feed\n  agency_class: F\n",
        )
        counts = sl.mark_ready("embedding")
        assert counts["promoted"] == 0
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            assert s.get(Story, sid).state == "draft"

    def test_cooldown_blocks_promotion(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 5 minutes old, cooldown 30 minutes → not yet ready.
        _seed(test_engine, sources_classes=["A", "A"], age_minutes=5)
        _write_sources(
            tmp_path,
            monkeypatch,
            "- url: https://src-a-0.example.com/feed\n  agency_class: A\n"
            "- url: https://src-a-1.example.com/feed\n  agency_class: A\n",
        )
        counts = sl.mark_ready("embedding", cooldown_minutes=30)
        assert counts["promoted"] == 0


class TestArchiveStale:
    def test_old_published_archived(self, test_engine) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="embedding", display_name="X")
            s.add(v)
            s.commit()
            old_updated = datetime.now(timezone.utc) - timedelta(hours=48)
            story = Story(
                vertical_id=v.id,
                canonical_headline="x",
                primary_published_at=old_updated,
                importance=0.1,
                state="published",
                narrative="...",
                narrative_updated_at=old_updated,
            )
            s.add(story)
            s.commit()
            sid = story.id
        counts = sl.archive_stale("embedding", hours=24)
        assert counts["archived"] == 1
        with SM() as s:
            assert s.get(Story, sid).state == "archived"

    def test_recent_published_not_archived(self, test_engine) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="embedding", display_name="X")
            s.add(v)
            s.commit()
            recent = datetime.now(timezone.utc) - timedelta(hours=1)
            story = Story(
                vertical_id=v.id,
                canonical_headline="x",
                primary_published_at=recent,
                importance=0.1,
                state="published",
                narrative="...",
                narrative_updated_at=recent,
            )
            s.add(story)
            s.commit()
            sid = story.id
        counts = sl.archive_stale("embedding", hours=24)
        assert counts["archived"] == 0
        with SM() as s:
            assert s.get(Story, sid).state == "published"


class TestRollupCitations:
    def test_bot_hits_aggregate_to_citation_events(self, test_engine) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="embedding", display_name="X")
            s.add(v)
            s.commit()
            now = datetime.now(timezone.utc)
            article = Article(
                vertical_id=v.id,
                hash="h-1",
                slug="my-story-slug",
                title="x",
                link="https://example.com/x",
                source="https://example.com/x",
                body="...",
                summary="",
                published_at=now,
            )
            s.add(article)
            s.commit()
            story = Story(
                vertical_id=v.id,
                canonical_headline="x",
                primary_published_at=now,
                importance=0.1,
                state="published",
            )
            s.add(story)
            s.commit()
            s.add(
                StoryArticle(
                    story_id=story.id,
                    article_id=article.id,
                    is_primary=True,
                )
            )
            for _ in range(3):
                s.add(
                    BotHit(
                        vertical_id=v.id,
                        ts=now,
                        bot_name="PerplexityBot",
                        ua="ua",
                        path="/story/my-story-slug/",
                        status=200,
                        ip_hash="h",
                    )
                )
            s.add(
                BotHit(
                    vertical_id=v.id,
                    ts=now,
                    bot_name="GPTBot",
                    ua="ua",
                    path="/story/my-story-slug/",
                    status=200,
                    ip_hash="h",
                )
            )
            s.add(
                BotHit(
                    vertical_id=v.id,
                    ts=now,
                    bot_name="PerplexityBot",
                    ua="ua",
                    path="/about/",
                    status=200,
                    ip_hash="h",
                )
            )
            s.commit()

        counts = sl.rollup_citations("embedding", since_hours=24)
        assert counts["events_written"] == 2

        with SM() as s:
            events = s.execute(select(CitationEvent)).scalars().all()
            by_bot = {e.bot_name: e.hit_count for e in events}
            assert by_bot["PerplexityBot"] == 3
            assert by_bot["GPTBot"] == 1

    def test_rollup_is_idempotent(self, test_engine) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="embedding", display_name="X")
            s.add(v)
            s.commit()
            now = datetime.now(timezone.utc)
            article = Article(
                vertical_id=v.id,
                hash="h",
                slug="story-slug",
                title="x",
                link="https://example.com/x",
                source="https://example.com/x",
                body="x",
                summary="",
                published_at=now,
            )
            s.add(article)
            s.commit()
            story = Story(
                vertical_id=v.id,
                canonical_headline="x",
                primary_published_at=now,
                importance=0.1,
                state="published",
            )
            s.add(story)
            s.commit()
            s.add(
                StoryArticle(
                    story_id=story.id, article_id=article.id, is_primary=True
                )
            )
            s.add(
                BotHit(
                    vertical_id=v.id,
                    ts=now,
                    bot_name="PerplexityBot",
                    ua="ua",
                    path="/story/story-slug/",
                    status=200,
                    ip_hash="h",
                )
            )
            s.commit()

        c1 = sl.rollup_citations("embedding", since_hours=24)
        c2 = sl.rollup_citations("embedding", since_hours=24)
        assert c1["events_written"] == 1
        assert c2["events_written"] == 0
        assert c2["events_updated"] == 1
        with SM() as s:
            events = s.execute(select(CitationEvent)).scalars().all()
            assert len(events) == 1
