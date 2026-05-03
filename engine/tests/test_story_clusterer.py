"""Tests for engine.core.story_clusterer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import story_clusterer as sc
from engine.core.db import (
    Article,
    ArticleEntity,
    Base,
    Entity,
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


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


def _seed(test_engine, articles: list[tuple[str, int]]) -> int:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    base = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)
        for i, (title, hb) in enumerate(articles):
            s.add(
                Article(
                    vertical_id=v.id,
                    hash=f"h-{i}",
                    slug=f"slug-{i}",
                    title=title,
                    link=f"https://example.com/a{i}",
                    source=f"https://src{i}.example.com/feed",
                    feed_region="US",
                    summary=title,
                    summary_source="llm",
                    published_at=base - timedelta(hours=hb),
                )
            )
        s.commit()
        return v.id


class TestClustering:
    def test_clusters_three_paraphrases(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Pentagon strikes AI cloud deals with major providers", 12),
                ("Pentagon inks AI cloud deals with multiple providers", 11),
                ("Pentagon awards AI cloud deals to several providers", 10),
                ("Replit founder defends Cursor acquisition publicly", 8),
            ],
        )
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_unrelated_titles_dont_cluster(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Anthropic releases Claude 4.6", 12),
                ("Vanguard cuts ETF expense ratios", 10),
                ("Levels.fyi salary report 2026", 8),
            ],
        )
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert clusters == []

    def test_window_excludes_old_articles(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Pentagon strikes AI deals OpenAI", 24),
                ("Pentagon inks AI deals Nvidia", 24),
                ("Old: Pentagon picks AI vendors", 24 * 30),
            ],
        )
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_unknown_vertical_returns_empty(self, test_engine, now) -> None:
        _seed(test_engine, [("a story headline now", 1)])
        assert sc.cluster_articles("ghost", days=7, now=now) == []


class TestPersist:
    def test_creates_one_story_per_cluster(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Pentagon strikes AI cloud deals with major providers", 12),
                ("Pentagon inks AI cloud deals with multiple providers", 11),
                ("Pentagon awards AI cloud deals to several providers", 10),
            ],
        )
        counts = sc.cluster_and_persist("modelwatch", days=7, now=now)
        assert counts["stories_created"] == 1
        assert counts["links_created"] == 3

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            stories = s.execute(select(Story)).scalars().all()
            assert len(stories) == 1
            assert stories[0].importance > 0
            links = s.execute(select(StoryArticle)).scalars().all()
            assert len(links) == 3
            primaries = [link for link in links if link.is_primary]
            assert len(primaries) == 1

    def test_canonical_is_oldest(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Pentagon awards AI cloud deals to providers latest", 10),
                ("Pentagon strikes AI cloud deals with providers oldest", 12),
                ("Pentagon inks AI cloud deals with providers middle", 11),
            ],
        )
        sc.cluster_and_persist("modelwatch", days=7, now=now)
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            story = s.execute(select(Story)).scalar_one()
            assert "oldest" in story.canonical_headline.lower()

    def test_idempotent_second_run(self, test_engine, now) -> None:
        _seed(
            test_engine,
            [
                ("Pentagon strikes AI deals OpenAI now", 12),
                ("Pentagon inks AI deals Nvidia again", 11),
            ],
        )
        first = sc.cluster_and_persist("modelwatch", days=7, now=now)
        second = sc.cluster_and_persist("modelwatch", days=7, now=now)
        assert first["stories_created"] == 1
        assert second["stories_created"] == 0
        assert second["clusters"] == 0


def _link_entities(
    test_engine, vertical_id: int, slug_to_articles: dict[str, list[str]]
) -> None:
    """Create Entity rows + ArticleEntity links keyed by article slug.

    ``slug_to_articles = {"anthropic": ["slug-0", "slug-1"]}`` means
    entity Anthropic links to articles slug-0 and slug-1.
    """
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        for ent_slug, art_slugs in slug_to_articles.items():
            ent = Entity(
                vertical_id=vertical_id,
                type="lab",
                name=ent_slug.title(),
                slug=ent_slug,
            )
            s.add(ent)
            s.flush()
            for art_slug in art_slugs:
                art = s.execute(
                    sc.select(Article).where(Article.slug == art_slug)
                ).scalar_one()
                s.add(ArticleEntity(article_id=art.id, entity_id=ent.id))
        s.commit()


class TestEntityOverlap:
    def test_shared_entity_required_when_both_have_entities(
        self, test_engine, now
    ) -> None:
        v_id = _seed(
            test_engine,
            [
                # Same vague boilerplate — title overlap will pass.
                ("Re Personal Investments thread one", 5),
                ("Re Personal Investments thread two", 4),
            ],
        )
        # Give them DIFFERENT entities so the entity rule blocks clustering.
        _link_entities(test_engine, v_id, {"vanguard": ["slug-0"]})
        _link_entities(test_engine, v_id, {"fidelity": ["slug-1"]})
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert clusters == []

    def test_shared_entity_allows_cluster(self, test_engine, now) -> None:
        v_id = _seed(
            test_engine,
            [
                ("Anthropic launches Claude 5 with new tool use", 5),
                ("Anthropic releases Claude 5 to enterprise", 4),
            ],
        )
        _link_entities(
            test_engine, v_id, {"anthropic": ["slug-0", "slug-1"]}
        )
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_one_side_lacks_entities_falls_back_to_title(
        self, test_engine, now
    ) -> None:
        v_id = _seed(
            test_engine,
            [
                ("Pentagon AI cloud deals with multiple providers a", 5),
                ("Pentagon AI cloud deals with multiple providers b", 4),
            ],
        )
        # Only one of the two has entities — the other has none, so the
        # entity check is skipped and title overlap alone wins.
        _link_entities(test_engine, v_id, {"pentagon": ["slug-0"]})
        clusters = sc.cluster_articles("modelwatch", days=7, now=now)
        assert len(clusters) == 1
