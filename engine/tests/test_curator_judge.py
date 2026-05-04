"""Tests for engine.core.curator_judge (Phase 22d)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import curator_judge as cj
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


def _seed_gray_zone(test_engine, *, n: int = 1) -> list[int]:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        v = (
            s.query(Vertical).filter(Vertical.name == "modelwatch").one_or_none()
        )
        if v is None:
            v = Vertical(name="modelwatch", display_name="Modelwatch")
            s.add(v)
            s.commit()
            s.refresh(v)
        ids = []
        for i in range(n):
            a = Article(
                vertical_id=v.id,
                hash=f"h-{i}",
                slug=f"slug-{i}",
                title=f"Some borderline article number {i}",
                link="https://example.com/x",
                source="https://www.example.com/feed",
                feed_region="US",
                summary="Brief summary content for a borderline article.",
                summary_source="llm",
                published_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                curator_score=0.55,
                curator_tier="researcher",
                curator_signals={
                    "source_auth": 0.2,
                    "title_shape": 0.2,
                    "entity_strength": 0.15,
                },
                curator_version=1,
            )
            s.add(a)
            s.commit()
            s.refresh(a)
            ids.append(a.id)
        return ids


class TestJudgeArticle:
    def test_high_score_lifts_to_standard(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response(
            {"score": 9, "reason": "Authoritative news event."}
        )
        ids = _seed_gray_zone(test_engine, n=1)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, ids[0])
        result = cj.judge_article(article)
        assert result is not None
        assert result["score"] == 9
        assert result["tier"] == "standard"

    def test_low_score_drops_to_skip(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response({"score": 2, "reason": "Discussion thread."})
        ids = _seed_gray_zone(test_engine, n=1)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, ids[0])
        result = cj.judge_article(article)
        assert result["tier"] == "skip"

    def test_mid_score_stays_researcher(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response({"score": 5, "reason": "Borderline."})
        ids = _seed_gray_zone(test_engine, n=1)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, ids[0])
        result = cj.judge_article(article)
        assert result["tier"] == "researcher"

    def test_score_clamped_to_1_10(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response({"score": 99, "reason": "x"})
        ids = _seed_gray_zone(test_engine, n=1)
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, ids[0])
        result = cj.judge_article(article)
        assert result["score"] == 10


class TestJudgePending:
    def test_updates_tier_and_signals(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response({"score": 9, "reason": "Real news."})
        _seed_gray_zone(test_engine, n=2)
        counts = cj.judge_pending("modelwatch", max_articles=10)
        assert counts["considered"] == 2
        assert counts["standard"] == 2

        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            rows = s.execute(select(Article)).scalars().all()
            for r in rows:
                assert r.curator_tier == "standard"
                assert r.curator_signals["judge"]["score"] == 9
                assert r.curator_signals["source_auth"] == 0.2  # preserved

    def test_skips_already_judged(
        self, test_engine, fake_llm, disable_cache
    ) -> None:
        fake_llm.set_response({"score": 8, "reason": "ok"})
        ids = _seed_gray_zone(test_engine, n=1)
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            row = s.get(Article, ids[0])
            row.curator_signals = {
                **row.curator_signals,
                "judge": {"score": 7, "reason": "old"},
            }
            s.commit()
        counts = cj.judge_pending("modelwatch", max_articles=10)
        assert counts["considered"] == 0
