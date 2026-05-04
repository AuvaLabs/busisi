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


class TestRenderSearch:
    def test_writes_index_json_and_page(
        self, test_engine, repo_templates, output_root
    ) -> None:
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from engine.core.db import Article, Vertical

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)
            a = Article(
                vertical_id=v.id,
                hash="h1",
                slug="anthropic-claude-5",
                title="Anthropic launches Claude 5",
                link="https://example.com/c5",
                source="https://example.com/feed",
                feed_region="US",
                summary="A short summary about Anthropic.",
                summary_source="llm",
                published_at=_dt(2026, 5, 4, tzinfo=_tz.utc),
            )
            s.add(a)
            s.commit()
        out = renderer.render_search("modelwatch")
        body = out["page"].read_text(encoding="utf-8")
        assert "Search Modelwatch" in body
        assert "/search-index.json" in body
        json_body = out["index_json"].read_text(encoding="utf-8")
        assert '"s":"anthropic-claude-5"' in json_body
        assert '"t":"Anthropic launches Claude 5"' in json_body


class TestRenderEntities:
    def _seed_entities(self, test_engine):
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from engine.core.db import (
            Article,
            ArticleEntity,
            Entity,
            Vertical,
        )

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)

            a = Article(
                vertical_id=v.id,
                hash="h1",
                slug="anthropic-claude-5",
                title="Anthropic releases Claude 5",
                link="https://example.com/c5",
                source="https://reuters.example.com/feed",
                feed_region="US",
                summary="x",
                summary_source="llm",
                published_at=_dt(2026, 5, 4, 12, 0, tzinfo=_tz.utc),
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            anthropic = Entity(
                vertical_id=v.id, type="lab", name="Anthropic", slug="anthropic"
            )
            claude = Entity(
                vertical_id=v.id, type="model", name="Claude 5", slug="claude-5"
            )
            ghost = Entity(
                vertical_id=v.id, type="lab", name="Ghost Lab", slug="ghost-lab"
            )
            s.add_all([anthropic, claude, ghost])
            s.commit()
            for ent in (anthropic, claude):
                s.add(ArticleEntity(article_id=a.id, entity_id=ent.id))
            s.commit()
            return v.id

    def test_entity_index_lists_only_linked(
        self, test_engine, repo_templates, output_root
    ) -> None:
        self._seed_entities(test_engine)
        path = renderer.render_entity_index("modelwatch")
        body = path.read_text(encoding="utf-8")
        assert "Anthropic" in body
        assert "Claude 5" in body
        assert "Ghost Lab" not in body
        assert "/entity/lab/anthropic/" in body
        assert "/entity/model/claude-5/" in body

    def test_per_entity_page_lists_articles(
        self, test_engine, repo_templates, output_root
    ) -> None:
        self._seed_entities(test_engine)
        pages = renderer.render_entities("modelwatch")
        assert "lab/anthropic" in pages
        body = pages["lab/anthropic"].read_text(encoding="utf-8")
        assert "Anthropic releases Claude 5" in body
        assert "/story/anthropic-claude-5/" in body
        assert "1 article tagged" in body


class TestRenderStoriesSiblings:
    def test_clustered_article_lists_siblings(
        self, test_engine, repo_templates, output_root
    ) -> None:
        _seed(test_engine)
        renderer.render_stories("modelwatch")
        primary = output_root / "output" / "modelwatch" / "story" / "cluster-0" / "index.html"
        body = primary.read_text(encoding="utf-8")
        # Header shows the count
        assert "Sources covering this (3)" in body
        # Primary article still listed
        assert "Pentagon AI cloud deals with multiple providers" in body
        # Sibling titles appear with internal /story/ links
        assert "/story/cluster-1/" in body
        assert "/story/cluster-2/" in body

    def test_story_emits_newsarticle_jsonld(
        self, test_engine, repo_templates, output_root
    ) -> None:
        import json as _json
        import re as _re
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from engine.core.db import Article, Vertical

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)
            a = Article(
                vertical_id=v.id,
                hash="h1",
                slug="claude-5-launch",
                title="Anthropic launches Claude 5",
                link="https://example.com/c5",
                source="https://example.com/feed",
                feed_region="US",
                summary="A short summary.",
                summary_source="llm",
                published_at=_dt(2026, 5, 4, 12, 0, tzinfo=_tz.utc),
            )
            s.add(a)
            s.commit()
        renderer.render_stories("modelwatch")
        body = (
            output_root
            / "output"
            / "modelwatch"
            / "story"
            / "claude-5-launch"
            / "index.html"
        ).read_text(encoding="utf-8")
        m = _re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            body,
            _re.DOTALL,
        )
        assert m, "ld+json block missing"
        data = _json.loads(m.group(1))
        assert data["@type"] == "NewsArticle"
        assert data["headline"] == "Anthropic launches Claude 5"
        assert data["datePublished"] == "2026-05-04T12:00:00+00:00"
        assert data["publisher"]["name"] == "Modelwatch"

    def test_entity_chips_render_on_story_page(
        self, test_engine, repo_templates, output_root
    ) -> None:
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from engine.core.db import (
            Article,
            ArticleEntity,
            Entity,
            Vertical,
        )

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)
            a = Article(
                vertical_id=v.id,
                hash="h1",
                slug="claude-5-launch",
                title="Anthropic launches Claude 5",
                link="https://example.com/c5",
                source="https://example.com/feed",
                feed_region="US",
                summary="x",
                summary_source="llm",
                published_at=_dt(2026, 5, 4, tzinfo=_tz.utc),
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            e1 = Entity(vertical_id=v.id, type="lab", name="Anthropic", slug="anthropic")
            e2 = Entity(vertical_id=v.id, type="model", name="Claude 5", slug="claude-5")
            s.add_all([e1, e2])
            s.commit()
            s.add_all(
                [
                    ArticleEntity(article_id=a.id, entity_id=e1.id),
                    ArticleEntity(article_id=a.id, entity_id=e2.id),
                ]
            )
            s.commit()
        renderer.render_stories("modelwatch")
        body = (
            output_root
            / "output"
            / "modelwatch"
            / "story"
            / "claude-5-launch"
            / "index.html"
        ).read_text(encoding="utf-8")
        assert 'class="entity-chips"' in body
        assert "/entity/lab/anthropic/" in body
        assert "/entity/model/claude-5/" in body

    def test_orphan_article_keeps_simple_sources(
        self, test_engine, repo_templates, output_root
    ) -> None:
        _seed(test_engine)
        renderer.render_stories("modelwatch")
        orphan = output_root / "output" / "modelwatch" / "story" / "fresh-orphan" / "index.html"
        body = orphan.read_text(encoding="utf-8")
        assert "<h2>" in body
        assert "Sources covering this" not in body
        assert "Sources" in body
