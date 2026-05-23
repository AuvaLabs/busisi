"""Tests for engine.core.researcher (Phase 22e)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import responses
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import researcher as r
from engine.core.db import (
    Article,
    ArticleEntity,
    Base,
    Entity,
    ResearchBundle,
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
def stub_ssrf(monkeypatch: pytest.MonkeyPatch):
    from engine.core import safe_http

    monkeypatch.setattr(safe_http, "install_ssrf_guard", lambda: None)


def _seed_researcher_article(test_engine, *, with_entities: int = 2) -> int:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)
        a = Article(
            vertical_id=v.id,
            hash="h-1",
            slug="anthropic-claude-5",
            title="Anthropic launches Claude 5",
            link="https://example.com/c5",
            source="https://example.com/feed",
            feed_region="US",
            summary="thin source",
            summary_source="feed",
            published_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
            curator_tier="researcher",
            curator_score=0.55,
            curator_signals={},
            curator_version=1,
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        for i, name in enumerate(["Anthropic", "Claude 5"][:with_entities]):
            e = Entity(
                vertical_id=v.id,
                type="lab" if i == 0 else "model",
                name=name,
                slug=name.lower().replace(" ", "-"),
            )
            s.add(e)
            s.commit()
            s.refresh(e)
            s.add(ArticleEntity(article_id=a.id, entity_id=e.id))
        s.commit()
        return a.id


_ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.12345v1</id>
    <link href="http://arxiv.org/abs/2501.12345v1"/>
    <title>Anthropic releases Claude 5: A constitutional AI follow-up</title>
    <summary>This paper studies the deployment of Claude 5 by Anthropic.</summary>
  </entry>
</feed>
"""


_EXA_PAYLOAD = {
    "results": [
        {
            "title": "Anthropic announces Claude 5 — TechCrunch",
            "url": "https://techcrunch.com/2026/05/04/anthropic-claude-5",
            "text": "Anthropic on Monday announced Claude 5, a substantial upgrade to its flagship model.",
        }
    ]
}


class TestExpandQueries:
    def test_title_only(self) -> None:
        a = Article(
            title="OpenAI signs Pentagon AI deal",
            source="x",
            hash="x",
            slug="x",
            link="x",
            vertical_id=1,
        )
        assert r.expand_queries(a, []) == ["OpenAI signs Pentagon AI deal"]

    def test_title_plus_entity(self) -> None:
        a = Article(
            title="OpenAI deal",
            source="x",
            hash="x",
            slug="x",
            link="x",
            vertical_id=1,
        )
        e = Entity(type="lab", name="OpenAI", slug="openai", vertical_id=1)
        out = r.expand_queries(a, [e])
        assert any("OpenAI" in q for q in out)

    def test_dedup(self) -> None:
        a = Article(
            title="OpenAI",
            source="x",
            hash="x",
            slug="x",
            link="x",
            vertical_id=1,
        )
        e = Entity(type="lab", name="OpenAI", slug="openai", vertical_id=1)
        out = r.expand_queries(a, [e])
        assert len(out) == len({q.lower() for q in out})


class TestArxiv:
    @responses.activate
    def test_parses_atom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "ARXIV_ENABLED", True)
        responses.add(
            responses.GET,
            cfg.ARXIV_ENDPOINT,
            body=_ARXIV_FEED,
            status=200,
            content_type="application/atom+xml",
        )
        results = r.search_arxiv("Anthropic Claude 5")
        assert len(results) == 1
        assert results[0]["host"] == "arxiv.org"
        assert "Claude 5" in results[0]["title"]

    def test_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(r, "ARXIV_ENABLED", False)
        assert r.search_arxiv("anything") == []

    @responses.activate
    def test_non_200_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "ARXIV_ENABLED", True)
        responses.add(responses.GET, cfg.ARXIV_ENDPOINT, status=500)
        assert r.search_arxiv("query") == []


class TestExa:
    @responses.activate
    def test_returns_results_when_keyed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "EXA_API_KEY", "test_key_123")
        responses.add(
            responses.POST, cfg.EXA_ENDPOINT, json=_EXA_PAYLOAD, status=200
        )
        results = r.search_exa("Anthropic Claude 5")
        assert len(results) == 1
        assert results[0]["host"] == "techcrunch.com"

    def test_empty_key_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(r, "EXA_API_KEY", "")
        assert r.search_exa("anything") == []

    @responses.activate
    def test_non_200_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "EXA_API_KEY", "k")
        responses.add(responses.POST, cfg.EXA_ENDPOINT, status=403)
        assert r.search_exa("q") == []


_WIKI_PAYLOAD = {
    "query": {
        "pages": {
            "5043734": {
                "pageid": 5043734,
                "index": 1,
                "title": "OpenAI",
                "fullurl": "https://en.wikipedia.org/wiki/OpenAI",
                "extract": (
                    "OpenAI is an American artificial intelligence research "
                    "laboratory founded in December 2015 in San Francisco."
                ),
            },
            "9999999": {
                "pageid": 9999999,
                "index": 2,
                "title": "Claude (AI model)",
                "fullurl": "https://en.wikipedia.org/wiki/Claude_(AI_model)",
                "extract": (
                    "Claude is a family of large language models developed by "
                    "Anthropic, first released in March 2023."
                ),
            },
        }
    }
}


class TestWikipedia:
    @responses.activate
    def test_parses_extract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "WIKIPEDIA_ENABLED", True)
        responses.add(
            responses.GET, cfg.WIKIPEDIA_ENDPOINT, json=_WIKI_PAYLOAD, status=200
        )
        results = r.search_wikipedia("OpenAI Claude")
        assert len(results) == 2
        assert results[0]["host"] == "en.wikipedia.org"
        assert results[0]["title"] == "OpenAI"
        assert "founded in December 2015" in results[0]["text"]
        # Results respect the MediaWiki `index` ordering, not dict iteration.
        assert results[1]["title"] == "Claude (AI model)"

    def test_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(r, "WIKIPEDIA_ENABLED", False)
        assert r.search_wikipedia("anything") == []

    @responses.activate
    def test_non_200_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "WIKIPEDIA_ENABLED", True)
        responses.add(responses.GET, cfg.WIKIPEDIA_ENDPOINT, status=500)
        assert r.search_wikipedia("q") == []

    @responses.activate
    def test_missing_extract_or_url_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "WIKIPEDIA_ENABLED", True)
        responses.add(
            responses.GET,
            cfg.WIKIPEDIA_ENDPOINT,
            json={"query": {"pages": {"1": {"title": "Stub", "index": 1}}}},
            status=200,
        )
        # Page without an extract or url should be skipped, not returned
        # with empty fields the rewriter can't use.
        assert r.search_wikipedia("q") == []


class TestPersistBundle:
    def test_writes_rows_and_marks_article(
        self, test_engine, stub_ssrf
    ) -> None:
        aid = _seed_researcher_article(test_engine)
        docs = [
            {
                "url": "https://arxiv.org/abs/2501.12345",
                "host": "arxiv.org",
                "title": "Paper",
                "text": "Abstract paragraph.",
            },
            {
                "url": "https://techcrunch.com/2026/05/04/anthropic-claude-5",
                "host": "techcrunch.com",
                "title": "TechCrunch",
                "text": "News write-up.",
            },
        ]
        n = r.persist_bundle(aid, docs)
        assert n == 2
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            rows = s.execute(select(ResearchBundle)).scalars().all()
            assert len(rows) == 2
            assert rows[0].article_id == aid
            assert rows[0].sha256 != ""
            article = s.get(Article, aid)
            assert article.researched_at is not None

    def test_replaces_prior_bundle(self, test_engine, stub_ssrf) -> None:
        aid = _seed_researcher_article(test_engine)
        r.persist_bundle(
            aid,
            [
                {
                    "url": "https://a.example/",
                    "host": "a.example",
                    "title": "x",
                    "text": "x",
                }
            ],
        )
        r.persist_bundle(
            aid,
            [
                {
                    "url": "https://b.example/",
                    "host": "b.example",
                    "title": "y",
                    "text": "y",
                }
            ],
        )
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            rows = s.execute(select(ResearchBundle)).scalars().all()
            assert len(rows) == 1
            assert rows[0].host == "b.example"


class TestResearchPending:
    @responses.activate
    def test_researches_pending_with_arxiv_only(
        self, test_engine, stub_ssrf, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "ARXIV_ENABLED", True)
        monkeypatch.setattr(r, "EXA_API_KEY", "")
        responses.add(
            responses.GET,
            cfg.ARXIV_ENDPOINT,
            body=_ARXIV_FEED,
            status=200,
            content_type="application/atom+xml",
        )
        _seed_researcher_article(test_engine)
        counts = r.research_pending("modelwatch", max_articles=5)
        assert counts["considered"] == 1
        assert counts["researched"] == 1
        assert counts["empty"] == 0

    @responses.activate
    def test_empty_when_no_results(
        self, test_engine, stub_ssrf, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from engine.core import config as cfg

        monkeypatch.setattr(r, "ARXIV_ENABLED", True)
        monkeypatch.setattr(r, "EXA_API_KEY", "")
        responses.add(
            responses.GET,
            cfg.ARXIV_ENDPOINT,
            body='<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
            status=200,
        )
        _seed_researcher_article(test_engine)
        counts = r.research_pending("modelwatch", max_articles=5)
        assert counts["empty"] == 1
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.execute(select(Article)).scalar_one()
            assert article.researched_at is not None


# ---- Phase 22h: cache + daily budget cap ----------------------------------


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    import fakeredis

    fr = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(r, "_redis", lambda: fr)
    monkeypatch.setattr(r, "_exa_cap_warned", False)
    return fr


class TestCacheAndBudget:
    def test_cache_round_trip(self, fake_redis) -> None:
        rows = [
            {"url": "https://arxiv.org/abs/2024.00001", "title": "x",
             "text": "abstract", "host": "arxiv.org"}
        ]
        assert r._cache_get("arxiv", "GPT-5 release") is None
        r._cache_put("arxiv", "GPT-5 release", rows)
        out = r._cache_get("arxiv", "GPT-5 release")
        assert out == rows

    def test_search_arxiv_uses_cache_on_repeat_call(
        self, fake_redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def fake_uncached(query: str, *, max_results: int = 3):
            calls["n"] += 1
            return [
                {
                    "url": "https://arxiv.org/abs/2024.00002",
                    "title": "Paper",
                    "text": "abstract",
                    "host": "arxiv.org",
                }
            ]

        monkeypatch.setattr(r, "_search_arxiv_uncached", fake_uncached)
        first = r.search_arxiv("query alpha")
        assert calls["n"] == 1
        second = r.search_arxiv("query alpha")
        assert calls["n"] == 1
        assert first == second
        r.search_arxiv("query beta")
        assert calls["n"] == 2

    def test_exa_daily_cap_blocks_calls_when_exceeded(
        self, fake_redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(r, "EXA_DAILY_CAP", 2)
        called = {"n": 0}

        def fake_uncached(query: str, *, max_results: int = 3):
            called["n"] += 1
            return [
                {
                    "url": f"https://exa.example/{query}",
                    "title": "x",
                    "text": "x",
                    "host": "exa.example",
                }
            ]

        monkeypatch.setattr(r, "_search_exa_uncached", fake_uncached)
        r.search_exa("a")
        r.search_exa("b")
        third = r.search_exa("c")
        assert called["n"] == 2
        assert third == []

    def test_exa_cap_zero_disables(
        self, fake_redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(r, "EXA_DAILY_CAP", 0)
        called = {"n": 0}

        def fake_uncached(query: str, *, max_results: int = 3):
            called["n"] += 1
            return []

        monkeypatch.setattr(r, "_search_exa_uncached", fake_uncached)
        for q in ("a", "b", "c", "d", "e"):
            r.search_exa(q)
        assert called["n"] == 5

    def test_cache_fails_open_when_redis_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(r, "_redis", lambda: None)
        assert r._cache_get("arxiv", "x") is None
        r._cache_put("arxiv", "x", [{"url": "u", "title": "t",
                                     "text": "x", "host": "h"}])
        assert r._cache_get("arxiv", "x") is None

    def test_exa_cap_fails_open_when_redis_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(r, "_redis", lambda: None)
        monkeypatch.setattr(r, "EXA_DAILY_CAP", 1)
        assert r._exa_under_daily_cap() is True
