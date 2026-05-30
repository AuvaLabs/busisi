"""Tests for engine.core.research_writer (R4b — Pass 1 + Pass 2 rewriter)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.config as _cfg_module
import engine.core.db as db_module
from engine.core import research_writer as rw
from engine.core.db import (
    Article,
    Base,
    Story,
    StoryArticle,
    StoryRevision,
    StorySource,
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


_BODY_REUTERS = (
    "OpenAI raised $10 billion at a $300 billion valuation in a Series F "
    "round led by Microsoft and SoftBank. The round closed Tuesday."
)
_BODY_BLOOMBERG = (
    "OpenAI's Series F closed at $10 billion, valuing the company at "
    "$300 billion. The deal was led by Microsoft and SoftBank, sources said."
)


def _seed_cluster(
    eng,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    vertical_name: str = "embedding",
    bodies: list[tuple[str, str, str]] | None = None,
) -> int:
    """Create a Vertical, two Articles with structured_extracts, and a Story."""
    if bodies is None:
        bodies = [
            ("www.reuters.com", _BODY_REUTERS, "OpenAI raised $10 billion."),
            ("www.bloomberg.com", _BODY_BLOOMBERG, "OpenAI's $10B Series F closed."),
        ]
    v_dir = tmp_path / "verticals" / vertical_name
    v_dir.mkdir(parents=True)
    yaml_lines = [
        f"- url: https://{host}/feed\n  agency_class: A\n" for host, _, _ in bodies
    ]
    (v_dir / "sources.yaml").write_text("".join(yaml_lines), encoding="utf-8")
    monkeypatch.setattr(_cfg_module, "VERTICALS_DIR", tmp_path / "verticals")

    SM = sessionmaker(eng, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name=vertical_name, display_name="X")
        s.add(v)
        s.commit()
        article_ids: list[int] = []
        for i, (host, body, lead_claim) in enumerate(bodies):
            a = Article(
                vertical_id=v.id,
                hash=f"hash-{i}",
                slug=f"slug-{i}",
                title=f"Headline {i}",
                link=f"https://{host}/article/{i}",
                source=f"https://{host}/feed",
                body=body,
                summary="",
                published_at=datetime.now(timezone.utc),
                structured_extract={
                    "lead_claim": lead_claim,
                    "key_facts": ["Round led by Microsoft and SoftBank."],
                    "numerics": [
                        {"value": "$10 billion", "context": "round size"},
                        {"value": "$300 billion", "context": "valuation"},
                    ],
                    "entities": [
                        {"name": "OpenAI", "type": "company"},
                        {"name": "Microsoft", "type": "company"},
                    ],
                    "quotes": [],
                },
                extract_version=1,
                extracted_at=datetime.now(timezone.utc),
            )
            s.add(a)
            s.commit()
            article_ids.append(a.id)

        story = Story(
            vertical_id=v.id,
            canonical_headline="OpenAI raises $10B Series F",
            primary_published_at=datetime.now(timezone.utc),
            importance=0.5,
            state="ready",
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


# ---------------------------------------------------------------------------
# Validator tests — no LLM, no DB, deterministic
# ---------------------------------------------------------------------------


_GOOD_NARRATIVE = {
    "lead": (
        "OpenAI[1] raised $10 billion in a Series F round at a $300 billion "
        "valuation, the company said Tuesday."
    ),
    "body": (
        "The round was led by Microsoft and SoftBank[2]. Reuters[1] reported "
        "the deal closed Tuesday, while Bloomberg[2] put the valuation at "
        "$300 billion. Sam Altman said the new capital would fund "
        "training infrastructure across new data centers. The deal makes "
        "OpenAI one of the most valuable private companies in history. "
        "OpenAI plans to deploy the funds across 5 new data centers by the "
        "end of the deployment window described in the filings. "
        "The Series F closed Tuesday after weeks of negotiation between "
        "the parties involved in the transaction. Microsoft and SoftBank, "
        "the lead investors named in both source filings, are expected to "
        "take board observer seats as part of the round. "
        "Reuters[1] said the new infrastructure plan focuses on next-generation "
        "training facilities. Bloomberg[2] noted that the round closed "
        "without participation from sovereign wealth funds, distinguishing "
        "it from earlier OpenAI fundraises. The valuation reflects roughly "
        "a 30 percent step up from prior pricing. "
        "OpenAI confirmed in a brief statement that the proceeds would "
        "support model training and inference infrastructure expansion "
        "across the 5 announced facilities. The company declined to "
        "specify a timeline beyond the broad deployment window. "
        "Both Reuters[1] and Bloomberg[2] reported their findings based "
        "on filings and conversations with people familiar with the matter."
    ),
    "why_this_matters": (
        "$300 billion is roughly 30 percent above OpenAI's 2024 valuation, "
        "signalling investor confidence in scaling-law economics."
    ),
}
_GOOD_SOURCES = [
    {
        "n": 1,
        "host": "reuters.com",
        "agency_class": "A",
        "source_url": "https://reuters.com/x",
    },
    {
        "n": 2,
        "host": "bloomberg.com",
        "agency_class": "A",
        "source_url": "https://bloomberg.com/y",
    },
]
# Bodies pool augments the source bodies with the additional facts the
# narrative cites (5 data centers, 30 percent above 2024) so the numeric
# grounding check passes. In production, scraper bodies are richer.
_GOOD_BODIES = [
    _BODY_REUTERS
    + " Plans for 5 data centers were announced. Up 30 percent from 2024."
    " The new infrastructure represents the largest deployment yet.",
    _BODY_BLOOMBERG + " Round did not include sovereign wealth funds.",
]


class TestValidator:
    def test_well_formed_passes(self) -> None:
        ok, reason = rw.validate_narrative(
            _GOOD_NARRATIVE, _GOOD_SOURCES, _GOOD_BODIES
        )
        assert ok, reason

    def test_unresolved_citation_rejected(self) -> None:
        bad = {**_GOOD_NARRATIVE, "body": _GOOD_NARRATIVE["body"] + " Also[7]."}
        ok, reason = rw.validate_narrative(bad, _GOOD_SOURCES, _GOOD_BODIES)
        assert not ok
        assert "7" in reason

    def test_class_f_source_rejected(self) -> None:
        bad_sources = [{**s, "agency_class": "F"} for s in _GOOD_SOURCES]
        ok, reason = rw.validate_narrative(
            _GOOD_NARRATIVE, bad_sources, _GOOD_BODIES
        )
        assert not ok
        assert "F" in reason or "primary" in reason.lower()

    def test_banned_phrase_rejected(self) -> None:
        bad = {
            **_GOOD_NARRATIVE,
            "body": _GOOD_NARRATIVE["body"] + " This is a game-changer for AI.",
        }
        ok, reason = rw.validate_narrative(bad, _GOOD_SOURCES, _GOOD_BODIES)
        assert not ok
        assert "game-changer" in reason

    def test_ungrounded_number_rejected(self) -> None:
        bad = {
            **_GOOD_NARRATIVE,
            "body": _GOOD_NARRATIVE["body"] + " The fund manages $999 trillion[1].",
        }
        ok, reason = rw.validate_narrative(bad, _GOOD_SOURCES, _GOOD_BODIES)
        assert not ok
        assert "numbers" in reason.lower()

    def test_word_count_too_short_rejected(self) -> None:
        short = {"lead": "Short.", "body": "Too short.", "why_this_matters": ""}
        ok, reason = rw.validate_narrative(short, _GOOD_SOURCES, _GOOD_BODIES)
        assert not ok
        assert "word_count" in reason


# ---------------------------------------------------------------------------
# Orchestration tests — mock the LLM, exercise rewrite_story end-to-end
# ---------------------------------------------------------------------------


class TestRewriteStory:
    def test_happy_path_persists_narrative_and_sources(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        story_id = _seed_cluster(test_engine, tmp_path, monkeypatch)

        monkeypatch.setattr(rw.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(rw.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            rw,
            "pass1_merge",
            lambda members, *, vertical, **kw: {
                "canonical_events": [
                    {
                        "claim": "OpenAI raised $10B at $300B valuation.",
                        "supporting_source_idxs": [0, 1],
                        "is_numeric": True,
                    }
                ],
                "contradictions": [],
                "timeline": [],
                "headline_seed": "OpenAI raises $10B Series F",
            },
        )
        # Append the cited extra numbers (5, 30) into one of the seeded bodies
        # so the validator's numeric grounding check passes.
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            arts = s.execute(select(Article)).scalars().all()
            arts[0].body = (
                _BODY_REUTERS
                + " Plans for 5 data centers. Up 30 percent from 2024."
            )
            s.commit()

        monkeypatch.setattr(
            rw,
            "pass2_compose",
            lambda pass1, sources, tone, *, vertical, **kw: _GOOD_NARRATIVE,
        )

        result = rw.rewrite_story(story_id, vertical="embedding")
        assert result is not None
        assert result["version"] == 1
        assert result["n_sources"] == 2

        with SM() as s:
            story = s.get(Story, story_id)
            assert story.state == "published"
            assert story.narrative is not None
            assert story.narrative_version == 1
            sources = (
                s.execute(
                    select(StorySource).where(StorySource.story_id == story_id)
                )
                .scalars()
                .all()
            )
            assert len(sources) == 2
            assert {sr.cited_as_n for sr in sources} == {1, 2}
            revisions = (
                s.execute(
                    select(StoryRevision).where(
                        StoryRevision.story_id == story_id
                    )
                )
                .scalars()
                .all()
            )
            assert len(revisions) == 1
            assert revisions[0].reason == "initial"

    def test_number_past_3000_chars_is_grounded(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: a figure appearing only past char 3000 of a source body
        must validate. The validator pool was previously built from the
        3000-char tone slice (``m["body"]``), so real numbers deep in long
        articles were falsely rejected as hallucinations — the dominant cause
        of zero-write pipeline ticks. The fix grounds against ``full_body``.
        """
        story_id = _seed_cluster(test_engine, tmp_path, monkeypatch)

        monkeypatch.setattr(rw.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(rw.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            rw,
            "pass1_merge",
            lambda members, *, vertical, **kw: {
                "canonical_events": [
                    {
                        "claim": "OpenAI raised $10B at $300B valuation.",
                        "supporting_source_idxs": [0, 1],
                        "is_numeric": True,
                    }
                ],
                "contradictions": [],
                "timeline": [],
                "headline_seed": "OpenAI raises $10B Series F",
            },
        )

        # Bury a distinctive figure (47915 accelerators) PAST char 3000 of the
        # primary body — beyond the old tone-slice cutoff. Early text keeps the
        # $10B / $300B figures the narrative also cites.
        deep_number = "The cluster will run 47915 accelerators by year end."
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            arts = s.execute(select(Article).order_by(Article.id)).scalars().all()
            arts[0].body = (
                _BODY_REUTERS
                + " Plans for 5 data centers. Up 30 percent from 2024. "
                + ("filler padding sentence. " * 200)  # ~5000 chars of padding
                + deep_number
            )
            s.commit()
            # Sanity: the figure really is past char 3000.
            assert arts[0].body.index("47915") > 3000

        narrative_with_deep_num = {
            **_GOOD_NARRATIVE,
            "body": _GOOD_NARRATIVE["body"]
            + " The deployment spans 47915 accelerators[1].",
        }
        monkeypatch.setattr(
            rw,
            "pass2_compose",
            lambda pass1, sources, tone, *, vertical, **kw: narrative_with_deep_num,
        )

        result = rw.rewrite_story(story_id, vertical="embedding")
        assert result is not None, "number past char 3000 was falsely rejected"
        assert result["version"] == 1

    def test_skips_when_no_primary_class_member(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v_dir = tmp_path / "verticals" / "embedding"
        v_dir.mkdir(parents=True)
        (v_dir / "sources.yaml").write_text(
            "- url: https://commentary.example.com/feed\n  agency_class: F\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(_cfg_module, "VERTICALS_DIR", tmp_path / "verticals")

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            v = Vertical(name="embedding", display_name="X")
            s.add(v)
            s.commit()
            article_ids = []
            for i in range(2):
                a = Article(
                    vertical_id=v.id,
                    hash=f"h-{i}",
                    slug=f"s-{i}",
                    title=f"Hot take {i}",
                    link=f"https://commentary.example.com/p/{i}",
                    source="https://commentary.example.com/feed",
                    body="A" * 500,
                    summary="",
                    published_at=datetime.now(timezone.utc),
                    structured_extract={
                        "lead_claim": "Some claim.",
                        "key_facts": [],
                        "numerics": [],
                        "entities": [],
                        "quotes": [],
                    },
                    extract_version=1,
                )
                s.add(a)
                s.commit()
                article_ids.append(a.id)
            story = Story(
                vertical_id=v.id,
                canonical_headline="Commentary cluster",
                primary_published_at=datetime.now(timezone.utc),
                importance=0.1,
                state="ready",
            )
            s.add(story)
            s.commit()
            for aid in article_ids:
                s.add(
                    StoryArticle(
                        story_id=story.id, article_id=aid, is_primary=False
                    )
                )
            s.commit()
            sid = story.id

        monkeypatch.setattr(
            rw,
            "pass1_merge",
            lambda *a, **kw: pytest.fail("pass1 must not run for F-only cluster"),
        )
        result = rw.rewrite_story(sid, vertical="embedding")
        assert result is None

    def test_skips_when_pass2_fails_validation(
        self, test_engine, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        story_id = _seed_cluster(test_engine, tmp_path, monkeypatch)

        monkeypatch.setattr(rw.llm_cache, "get", lambda key: None)
        monkeypatch.setattr(rw.llm_cache, "put", lambda key, value: None)
        monkeypatch.setattr(
            rw,
            "pass1_merge",
            lambda members, *, vertical, **kw: {
                "canonical_events": [],
                "headline_seed": "x",
            },
        )
        bad_narrative = {
            "lead": _GOOD_NARRATIVE["lead"],
            "body": _GOOD_NARRATIVE["body"] + " This is a game-changer for AI.",
            "why_this_matters": _GOOD_NARRATIVE["why_this_matters"],
        }
        monkeypatch.setattr(
            rw,
            "pass2_compose",
            lambda pass1, sources, tone, *, vertical, **kw: bad_narrative,
        )
        result = rw.rewrite_story(story_id, vertical="embedding")
        assert result is None

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            story = s.get(Story, story_id)
            assert story.narrative is None
            assert story.state == "ready"


class TestPassOrphanComposeCacheHandling:
    """Regression coverage for F2 cache-hit safety.

    A prior session shipped Shape-B ({"insufficient": true}) into the cache
    but didn't honor it on cache hits — the next call returned the cached
    dict as if it were a narrative, crashing validate_orphan_narrative on
    narrative["lead"].
    """

    def test_cache_hit_insufficient_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_insufficient = {"insufficient": True, "reason": "thin"}
        monkeypatch.setattr(rw.llm_cache, "get", lambda key: cached_insufficient)
        out = rw.pass_orphan_compose(
            primary_extract={"lead_claim": "x"},
            primary_body="x",
            bundles=[],
            sources=[],
            vertical="embedding",
        )
        assert out is None

    def test_cache_hit_malformed_falls_through_to_recompute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense-in-depth: a corrupt cache entry shouldn't be served as a
        narrative — we fall through to recompute. The recompute returning a
        clean narrative confirms the malformed entry was rejected."""
        monkeypatch.setattr(
            rw.llm_cache, "get", lambda key: {"unexpected": "shape"}
        )
        monkeypatch.setattr(rw.llm_cache, "put", lambda key, value: None)
        good = {
            "lead": "Lead text.",
            "body": "Body text.",
            "why_this_matters": "Caption.",
        }
        import json as _json
        monkeypatch.setattr(
            rw.llm_client, "call_llm", lambda **kw: _json.dumps(good)
        )
        out = rw.pass_orphan_compose(
            primary_extract={"lead_claim": "x"},
            primary_body="x",
            bundles=[],
            sources=[],
            vertical="embedding",
        )
        assert out == good

    def test_cache_hit_valid_narrative_returns_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_good = {
            "lead": "Lead text.",
            "body": "Body text.",
            "why_this_matters": "Caption.",
        }
        monkeypatch.setattr(rw.llm_cache, "get", lambda key: cached_good)
        out = rw.pass_orphan_compose(
            primary_extract={"lead_claim": "x"},
            primary_body="x",
            bundles=[],
            sources=[],
            vertical="embedding",
        )
        assert out == cached_good
