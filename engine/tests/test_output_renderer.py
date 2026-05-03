"""Regression tests for engine.core.output_renderer.render_index merging
of Stories with orphan Articles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
import engine.core.output_renderer as renderer
from engine.core.db import Article, Base, Story, StoryArticle, Vertical


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
def repo_templates(monkeypatch: pytest.MonkeyPatch):
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        renderer,
        "_TEMPLATES_DIR",
        repo_root / "engine" / "shared" / "templates",
    )


@pytest.fixture
def output_root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(renderer, "DATA_DIR", tmp_path)
    return tmp_path


def _seed(test_engine):
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    base = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)

        cluster_titles = [
            "Pentagon AI cloud deals with multiple providers",
            "Pentagon AI cloud contracts spread across vendors",
            "Pentagon AI cloud deals announced today",
        ]
        cluster_articles: list[Article] = []
        for i, title in enumerate(cluster_titles):
            a = Article(
                vertical_id=v.id,
                hash=f"c-{i}",
                slug=f"cluster-{i}",
                title=title,
                link=f"https://example.com/c{i}",
                source=f"https://src{i}.example.com/feed",
                feed_region="US",
                summary=title,
                summary_source="llm",
                published_at=base - timedelta(hours=2 + i),
            )
            s.add(a)
            cluster_articles.append(a)
        orphans = [
            Article(
                vertical_id=v.id,
                hash="o-fresh",
                slug="fresh-orphan",
                title="Fresh single-source story",
                link="https://example.com/fresh",
                source="https://fresh.example.com/feed",
                feed_region="US",
                summary="Fresh.",
                summary_source="llm",
                published_at=base - timedelta(minutes=30),
            ),
            Article(
                vertical_id=v.id,
                hash="o-stale",
                slug="stale-orphan",
                title="Stale single-source story",
                link="https://example.com/stale",
                source="https://stale.example.com/feed",
                feed_region="EU",
                summary="Stale.",
                summary_source="llm",
                published_at=base - timedelta(days=2),
            ),
        ]
        for o in orphans:
            s.add(o)
        s.commit()
        for a in cluster_articles:
            s.refresh(a)

        story = Story(
            vertical_id=v.id,
            canonical_headline=cluster_articles[0].title,
            primary_published_at=cluster_articles[0].published_at,
            importance=1.3863,
        )
        s.add(story)
        s.flush()
        for i, a in enumerate(cluster_articles):
            s.add(
                StoryArticle(
                    story_id=story.id, article_id=a.id, is_primary=(i == 0)
                )
            )
        s.commit()


class TestRenderIndexMerge:
    def test_story_card_renders_with_badge(
        self, test_engine, repo_templates, output_root
    ) -> None:
        _seed(test_engine)
        path = renderer.render_index("modelwatch", limit=10)
        body = path.read_text(encoding="utf-8")
        assert "3 sources" in body
        assert 'class="n-sources"' in body

    def test_orphan_card_has_no_badge(
        self, test_engine, repo_templates, output_root
    ) -> None:
        _seed(test_engine)
        path = renderer.render_index("modelwatch", limit=10)
        body = path.read_text(encoding="utf-8")
        assert "Fresh single-source story" in body
        assert "1 sources" not in body

    def test_fresher_orphan_outranks_older_story(
        self, test_engine, repo_templates, output_root
    ) -> None:
        _seed(test_engine)
        path = renderer.render_index("modelwatch", limit=10)
        body = path.read_text(encoding="utf-8")
        assert body.index("Fresh single-source story") < body.index(
            "Pentagon AI cloud deals"
        )

    def test_unclustered_articles_not_dropped_when_no_stories(
        self, test_engine, repo_templates, output_root
    ) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        _seed(test_engine)
        with SM() as s:
            s.query(StoryArticle).delete()
            s.query(Story).delete()
            s.commit()
        path = renderer.render_index("modelwatch", limit=10)
        body = path.read_text(encoding="utf-8")
        assert "Fresh single-source story" in body
        assert "Pentagon AI cloud deals with multiple providers" in body
        assert 'class="n-sources"' not in body
