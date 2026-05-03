"""Tests for engine.core.entity_extractor."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import entity_extractor as ee
from engine.core.db import (
    Article,
    ArticleEntity,
    Base,
    Entity,
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
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    def _make_response(payload: dict):
        def _stub(**kwargs):
            calls.append(kwargs)
            return json.dumps(payload)

        return _stub

    def set_response(payload: dict) -> None:
        from engine.core import llm_client

        monkeypatch.setattr(llm_client, "call_llm", _make_response(payload))

    return type(
        "FakeLLM", (), {"set_response": staticmethod(set_response), "calls": calls}
    )


@pytest.fixture
def disable_cache(monkeypatch: pytest.MonkeyPatch):
    from engine.core import llm_cache

    monkeypatch.setattr(llm_cache, "get", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_cache, "put", lambda *_a, **_kw: None)


def _seed_one(test_engine, *, body: str | None = None) -> tuple[int, int]:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)
        a = Article(
            vertical_id=v.id,
            hash="h-0",
            slug="anthropic-launches-claude-5",
            title="Anthropic launches Claude 5 with new tool use",
            link="https://example.com/anthropic-claude-5",
            source="https://example.com/feed",
            feed_region="US",
            summary=(
                "Anthropic, the AI lab founded by Dario Amodei and Daniela "
                "Amodei, announced Claude 5 today. The model competes with "
                "OpenAI's GPT-4o and Google's Gemini 2.5 Pro."
            ),
            body=body,
            summary_source="llm",
            published_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        return v.id, a.id


class TestExtractEntities:
    def test_returns_normalized_entities(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response(
            {
                "entities": [
                    {"type": "lab", "name": "Anthropic"},
                    {"type": "model", "name": "Claude 5"},
                    {"type": "lab", "name": "OpenAI"},
                    {"type": "model", "name": "GPT-4o"},
                ]
            }
        )
        _, aid = _seed_one(test_engine)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, aid)
        ents = ee.extract_entities(article)
        assert {(e["type"], e["slug"]) for e in ents} == {
            ("lab", "anthropic"),
            ("model", "claude-5"),
            ("lab", "openai"),
            ("model", "gpt-4o"),
        }

    def test_drops_invalid_types_and_dedupes(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response(
            {
                "entities": [
                    {"type": "lab", "name": "Anthropic"},
                    {"type": "lab", "name": "Anthropic "},
                    {"type": "spaceship", "name": "Falcon Heavy"},
                    {"type": "model", "name": ""},
                ]
            }
        )
        _, aid = _seed_one(test_engine)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, aid)
        ents = ee.extract_entities(article)
        assert ents == [{"type": "lab", "name": "Anthropic", "slug": "anthropic"}]

    def test_too_thin_source_returns_empty(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)
            a = Article(
                vertical_id=v.id,
                hash="thin",
                slug="thin",
                title="Hi",
                link="https://example.com/thin",
                source="https://example.com",
                feed_region="US",
                summary="Hi",
                summary_source="llm",
                published_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            article = s.get(Article, a.id)
        assert ee.extract_entities(article) == []


class TestPersist:
    def test_upsert_creates_then_relinks(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response(
            {
                "entities": [
                    {"type": "lab", "name": "Anthropic"},
                    {"type": "model", "name": "Claude 5"},
                ]
            }
        )
        v_id, aid = _seed_one(test_engine)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, aid)
        ents = ee.extract_entities(article)
        written = ee.persist_for_article(aid, v_id, ents)
        assert written == 2

        with SM() as s:
            ent_rows = s.execute(select(Entity)).scalars().all()
            link_rows = s.execute(select(ArticleEntity)).scalars().all()
            article = s.get(Article, aid)
            assert {e.slug for e in ent_rows} == {"anthropic", "claude-5"}
            assert len(link_rows) == 2
            assert article.entities_extracted_at is not None

        again = ee.persist_for_article(aid, v_id, ents)
        assert again == 0
        with SM() as s:
            assert (
                len(s.execute(select(ArticleEntity)).scalars().all()) == 2
            )

    def test_enrich_pending_skips_processed(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response(
            {"entities": [{"type": "lab", "name": "Anthropic"}]}
        )
        _, aid = _seed_one(test_engine, body=None)
        first = ee.enrich_pending(
            "modelwatch", max_articles=10, sleep_between=0
        )
        assert first["considered"] == 1
        assert first["extracted"] == 1
        second = ee.enrich_pending(
            "modelwatch", max_articles=10, sleep_between=0
        )
        assert second["considered"] == 0
