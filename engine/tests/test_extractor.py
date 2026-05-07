"""Tests for engine.core.extractor (R4a — Pass 0)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import extractor as ex
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


def _seed_article(eng, body: str, *, vertical_name: str = "embedding") -> int:
    SM = sessionmaker(eng, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name=vertical_name, display_name="X")
        s.add(v)
        s.commit()
        a = Article(
            vertical_id=v.id,
            hash="abc123",
            slug="seeded-article",
            title="OpenAI raises $10B at $300B valuation today",
            link="https://example.com/x",
            source="https://example.com/x",
            body=body,
            summary="",
        )
        s.add(a)
        s.commit()
        return a.id


_SAMPLE_BODY = (
    "OpenAI announced today it has raised $10 billion at a $300 billion "
    "valuation in a Series F round led by Microsoft and SoftBank. The round "
    "values the company at roughly 30 percent more than its 2024 round. CEO "
    "Sam Altman said the new capital will fund GPT-6 training infrastructure. "
    "OpenAI plans to deploy the funds across 5 new data centers by 2027."
)


_SAMPLE_EXTRACT = {
    "lead_claim": "OpenAI raised 10 billion dollars at a 300 billion valuation.",
    "key_facts": [
        "Series F round led by Microsoft and SoftBank.",
        "Funds will be deployed across 5 new data centers.",
    ],
    "numerics": [
        {"value": "$10 billion", "context": "round size"},
        {"value": "$300 billion", "context": "valuation"},
        {"value": "30 percent", "context": "increase from 2024 round"},
        {"value": "5", "context": "data centers"},
        {"value": "2027", "context": "deployment target"},
    ],
    "entities": [
        {"name": "OpenAI", "type": "company"},
        {"name": "Microsoft", "type": "company"},
        {"name": "SoftBank", "type": "company"},
        {"name": "Sam Altman", "type": "person"},
    ],
    "quotes": [],
}


class TestValidator:
    def test_well_formed_extract_passes(self) -> None:
        ok, reason = ex._validate_extract(_SAMPLE_EXTRACT, _SAMPLE_BODY)
        assert ok, reason

    def test_missing_required_key_rejected(self) -> None:
        bad = {**_SAMPLE_EXTRACT}
        del bad["numerics"]
        ok, reason = ex._validate_extract(bad, _SAMPLE_BODY)
        assert not ok
        assert "numerics" in reason

    def test_ungrounded_numeric_rejected(self) -> None:
        bad = {
            **_SAMPLE_EXTRACT,
            "numerics": [{"value": "$999 trillion", "context": "fake"}],
        }
        ok, reason = ex._validate_extract(bad, _SAMPLE_BODY)
        assert not ok
        assert "ungrounded" in reason

    def test_empty_lead_claim_rejected(self) -> None:
        bad = {**_SAMPLE_EXTRACT, "lead_claim": "   "}
        ok, reason = ex._validate_extract(bad, _SAMPLE_BODY)
        assert not ok
        assert "lead_claim" in reason

    def test_non_object_rejected(self) -> None:
        ok, reason = ex._validate_extract([], _SAMPLE_BODY)  # type: ignore[arg-type]
        assert not ok


class TestExtractOne:
    def test_short_body_returns_none(self, test_engine) -> None:
        aid = _seed_article(test_engine, body="too short")
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.get(Article, aid)
            assert ex.extract_one(article, vertical="embedding") is None

    def test_happy_path_with_mocked_llm(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        aid = _seed_article(test_engine, body=_SAMPLE_BODY)
        # Force cache miss so we hit the LLM stub.
        monkeypatch.setattr(ex.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(ex.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            ex.llm_client,
            "call_llm",
            lambda **kw: json.dumps(_SAMPLE_EXTRACT),
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.get(Article, aid)
            result = ex.extract_one(article, vertical="embedding")
            assert result is not None
            assert result["lead_claim"].startswith("OpenAI")
            assert any(n["value"] == "$10 billion" for n in result["numerics"])

    def test_cache_hit_returns_cached(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        aid = _seed_article(test_engine, body=_SAMPLE_BODY)
        monkeypatch.setattr(ex.llm_cache, "get", lambda key: _SAMPLE_EXTRACT)
        monkeypatch.setattr(
            ex.llm_client,
            "call_llm",
            lambda **kw: pytest.fail("call_llm should not run on cache hit"),
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.get(Article, aid)
            result = ex.extract_one(article, vertical="embedding")
            assert result is not None
            assert result["_cached"] is True

    def test_invalid_json_returns_none(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        aid = _seed_article(test_engine, body=_SAMPLE_BODY)
        monkeypatch.setattr(ex.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(ex.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            ex.llm_client, "call_llm", lambda **kw: "not json {{{"
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.get(Article, aid)
            assert ex.extract_one(article, vertical="embedding") is None


class TestExtractPending:
    def test_persists_extract_and_bumps_version(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_article(test_engine, body=_SAMPLE_BODY)
        monkeypatch.setattr(ex.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(ex.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            ex.llm_client,
            "call_llm",
            lambda **kw: json.dumps(_SAMPLE_EXTRACT),
        )
        counts = ex.extract_pending("embedding", max_articles=10, sleep_between=0)
        assert counts["updated"] == 1
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.execute(select(Article)).scalar_one()
            assert article.extract_version == ex.EXTRACT_VERSION
            assert article.extracted_at is not None
            assert article.structured_extract["lead_claim"].startswith("OpenAI")

    def test_skips_short_bodies(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_article(test_engine, body="too short")
        monkeypatch.setattr(ex.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(
            ex.llm_client,
            "call_llm",
            lambda **kw: pytest.fail("should not call LLM on short body"),
        )
        counts = ex.extract_pending("embedding", max_articles=10, sleep_between=0)
        assert counts["skipped"] == 1
        assert counts["updated"] == 0
