"""Tests for engine.core.curator (Phase 22a — rule-based scoring)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.config as _cfg_module
import engine.core.db as db_module
from engine.core import curator as cur
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


# ---------------------------------------------------------------------------


class TestSourceAuthority:
    def test_tier_a_lifts_score(self) -> None:
        m = {"reuters.com": "tier_a"}
        s = cur.score_source_authority("https://www.reuters.com/feed", m)
        assert s == pytest.approx(0.40, abs=1e-6)

    def test_tier_c_low_score(self) -> None:
        m = {"reddit.com": "tier_c"}
        s = cur.score_source_authority("https://www.reddit.com/r/x", m)
        assert s == pytest.approx(0.40 * 0.30, abs=1e-6)

    def test_unknown_host_default(self) -> None:
        s = cur.score_source_authority("https://obscure.example.com/feed", {})
        assert s == pytest.approx(0.40 * 0.50, abs=1e-6)

    def test_strips_www(self) -> None:
        m = {"reuters.com": "tier_a"}
        a = cur.score_source_authority("https://www.reuters.com/feed", m)
        b = cur.score_source_authority("https://reuters.com/feed", m)
        assert a == b


class TestTitleShape:
    def test_declarative_full_weight(self) -> None:
        assert cur.score_title_shape(
            "Anthropic launches Claude 5 with new tool use"
        ) == pytest.approx(0.30)

    def test_re_prefix_zero(self) -> None:
        assert cur.score_title_shape("Re: Personal Investments thread") == 0.0

    def test_d_flair_zero(self) -> None:
        assert cur.score_title_shape("[D] Are ML PhDs becoming too incremental?") == 0.0

    def test_should_i_phrase_zero(self) -> None:
        assert cur.score_title_shape("Should I roll over my 401k to an IRA?") == 0.0

    def test_short_question_zero(self) -> None:
        assert cur.score_title_shape("Bank hacked. What now?") == 0.0

    def test_long_question_softer_penalty(self) -> None:
        assert cur.score_title_shape(
            "Did the Pentagon just sign a deal with OpenAI?"
        ) == pytest.approx(0.30 * 0.4)

    def test_empty_title_zero(self) -> None:
        assert cur.score_title_shape("") == 0.0


class TestEntityStrength:
    def test_zero_entities_zero(self) -> None:
        assert cur.score_entity_strength(0) == 0.0

    def test_one_entity_third(self) -> None:
        assert cur.score_entity_strength(1) == pytest.approx(0.30 / 3.0)

    def test_three_or_more_full(self) -> None:
        assert cur.score_entity_strength(3) == pytest.approx(0.30)
        assert cur.score_entity_strength(8) == pytest.approx(0.30)


class TestTopicRelevance:
    def test_require_off_is_noop(self) -> None:
        assert cur.score_topic_relevance([], require=False) == 1.0
        assert cur.score_topic_relevance(None, require=False) == 1.0

    def test_strong_label_full(self) -> None:
        labels = [{"label": "taxes", "confidence": 80}]
        assert cur.score_topic_relevance(labels, require=True) == 1.0

    def test_weak_label_discounted(self) -> None:
        labels = [{"label": "taxes", "confidence": 20}]
        assert cur.score_topic_relevance(labels, require=True) == pytest.approx(0.6)

    def test_no_label_knocked_down(self) -> None:
        assert cur.score_topic_relevance([], require=True) == pytest.approx(0.25)
        assert cur.score_topic_relevance(None, require=True) == pytest.approx(0.25)

    def test_bare_string_label_counts_on_topic(self) -> None:
        assert cur.score_topic_relevance(["taxes"], require=True) == 1.0


class TestRelevanceGateInScoring:
    def test_offtopic_high_authority_skipped_when_required(self, test_engine) -> None:
        """A tier-A, entity-rich, declarative headline with NO taxonomy label
        (off-topic) is forced to skip when the vertical requires relevance —
        the World Cup-drinks-on-a-finance-site case."""
        aid = _seed_article(
            test_engine,
            source="https://www.bbc.co.uk/feed",
            title="The best World Cup drinks and snacks for all 48 teams",
            n_entities=4,
            labels=[],  # classifier found no personal-finance topic
        )
        result = cur.score_article(
            aid,
            vertical_name="modelwatch",
            tier_map={"bbc.co.uk": "tier_a"},
            require_topic=True,
        )
        assert result is not None
        assert result["tier"] == "skip"
        assert result["signals"]["topic_relevance"] == pytest.approx(0.25)

    def test_ontopic_unaffected_when_required(self, test_engine) -> None:
        aid = _seed_article(
            test_engine,
            source="https://www.reuters.com/feed",
            title="Federal Reserve holds rates steady, signals one cut",
            n_entities=4,
            labels=[{"label": "brokerage-investing", "confidence": 85}],
        )
        result = cur.score_article(
            aid,
            vertical_name="modelwatch",
            tier_map={"reuters.com": "tier_a"},
            require_topic=True,
        )
        assert result is not None
        assert result["tier"] == "standard"
        assert result["score"] == pytest.approx(1.0, abs=1e-6)

    def test_offtopic_passes_when_not_required(self, test_engine) -> None:
        """Same off-topic article, gate OFF (legacy behaviour) → still passes."""
        aid = _seed_article(
            test_engine,
            source="https://www.bbc.co.uk/feed",
            title="The best World Cup drinks and snacks for all 48 teams",
            n_entities=4,
            labels=[],
        )
        result = cur.score_article(
            aid,
            vertical_name="modelwatch",
            tier_map={"bbc.co.uk": "tier_a"},
            require_topic=False,
        )
        assert result is not None
        assert result["tier"] == "standard"


class TestDecideTier:
    def test_standard(self) -> None:
        assert cur._decide_tier(0.95) == "standard"
        assert cur._decide_tier(0.70) == "standard"

    def test_researcher(self) -> None:
        assert cur._decide_tier(0.60) == "researcher"
        assert cur._decide_tier(0.40) == "researcher"

    def test_skip(self) -> None:
        assert cur._decide_tier(0.39) == "skip"
        assert cur._decide_tier(0.0) == "skip"


# ---------------------------------------------------------------------------


def _seed_article(
    test_engine,
    *,
    source: str,
    title: str,
    n_entities: int = 0,
    labels: list | None = None,
) -> int:
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
        existing = (
            s.query(Article).filter(Article.title == title).one_or_none()
        )
        if existing is not None:
            return existing.id
        a = Article(
            vertical_id=v.id,
            hash=f"h-{title[:30]}",
            slug=f"slug-{title[:20]}".replace(" ", "-").lower(),
            title=title,
            link="https://example.com/x",
            source=source,
            feed_region="US",
            summary="x",
            summary_source="llm",
            labels=labels,
            published_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        for i in range(n_entities):
            e = Entity(
                vertical_id=v.id, type="lab", name=f"E{a.id}-{i}", slug=f"e-{a.id}-{i}"
            )
            s.add(e)
            s.commit()
            s.refresh(e)
            s.add(ArticleEntity(article_id=a.id, entity_id=e.id))
        s.commit()
        return a.id


class TestScoreArticle:
    def test_high_authority_news_lands_standard(self, test_engine) -> None:
        aid = _seed_article(
            test_engine,
            source="https://www.reuters.com/feed",
            title="Pentagon signs AI cloud deal with major providers",
            n_entities=4,
        )
        result = cur.score_article(
            aid,
            vertical_name="modelwatch",
            tier_map={"reuters.com": "tier_a"},
        )
        assert result is not None
        assert result["tier"] == "standard"
        assert result["score"] == pytest.approx(0.40 + 0.30 + 0.30, abs=1e-6)

    def test_reddit_thread_lands_skip(self, test_engine) -> None:
        aid = _seed_article(
            test_engine,
            source="https://www.reddit.com/r/personalfinance/.rss",
            title="Should I roll over my 401k to an IRA?",
            n_entities=0,
        )
        result = cur.score_article(
            aid,
            vertical_name="modelwatch",
            tier_map={"reddit.com": "tier_c"},
        )
        assert result is not None
        assert result["tier"] == "skip"

    def test_persists_columns(self, test_engine) -> None:
        aid = _seed_article(
            test_engine,
            source="https://www.example.com/feed",
            title="Some declarative news headline about a topic",
            n_entities=2,
        )
        cur.score_article(aid, vertical_name="modelwatch", tier_map={})
        SM = sessionmaker(test_engine, future=True)
        with SM() as s:
            article = s.get(Article, aid)
            assert article.curator_score is not None
            assert article.curator_tier in {"skip", "researcher", "standard"}
            assert article.curator_version == cur.CURATOR_VERSION
            assert article.curator_signals["entity_count"] == 2

    def test_unknown_article_returns_none(self, test_engine) -> None:
        _seed_article(
            test_engine,
            source="https://www.example.com/feed",
            title="placeholder",
        )
        assert cur.score_article(99999, vertical_name="modelwatch") is None


class TestScorePending:
    def test_only_scores_below_version(self, test_engine) -> None:
        a1 = _seed_article(
            test_engine,
            source="https://www.reuters.com/feed",
            title="Real news headline now happening",
            n_entities=3,
        )
        a2 = _seed_article(
            test_engine,
            source="https://www.reuters.com/feed",
            title="Another real news headline today",
            n_entities=3,
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            article = s.get(Article, a2)
            article.curator_version = cur.CURATOR_VERSION
            s.commit()
        counts = cur.score_pending("modelwatch", max_articles=10)
        assert counts["considered"] == 1
        with SM() as s:
            assert s.get(Article, a1).curator_score is not None


# ---------------------------------------------------------------------------
# R1 — agency_class taxonomy
# ---------------------------------------------------------------------------


class TestAgencyClassLoader:
    """R1 — agency_class A-F is the canonical authority signal.

    The legacy ``tier:`` annotation is still accepted as a fallback during
    migration. Class G (forums/Reddit) is removed at the source-list level
    and therefore not represented in the loader.
    """

    def _write_sources(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        vertical: str,
        body: str,
    ) -> None:
        v_dir = tmp_path / "verticals" / vertical
        v_dir.mkdir(parents=True)
        (v_dir / "sources.yaml").write_text(body, encoding="utf-8")
        # vertical_dir() reads VERTICALS_DIR at call time. monkeypatch reverts.
        monkeypatch.setattr(_cfg_module, "VERTICALS_DIR", tmp_path / "verticals")

    def test_agency_class_a_maps_to_tier_a(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            "- url: https://www.reuters.com/feed\n  agency_class: A\n",
        )
        m = cur._load_source_tier_map("v1")
        assert m == {"reuters.com": "tier_a"}

    def test_agency_class_f_maps_to_tier_c(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            "- url: https://thefinancebuff.com/feed\n  agency_class: F\n",
        )
        m = cur._load_source_tier_map("v1")
        assert m == {"thefinancebuff.com": "tier_c"}

    def test_agency_class_map_returns_raw_letter(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            (
                "- url: https://www.reuters.com/feed\n  agency_class: A\n"
                "- url: https://thefinancebuff.com/feed\n  agency_class: F\n"
                "- url: https://www.theverge.com/feed\n  agency_class: C\n"
            ),
        )
        m = cur._load_agency_class_map("v1")
        assert m == {
            "reuters.com": "A",
            "thefinancebuff.com": "F",
            "theverge.com": "C",
        }

    def test_legacy_tier_annotation_still_works(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            "- url: https://example.com/feed\n  tier: tier_b\n",
        )
        m = cur._load_source_tier_map("v1")
        assert m == {"example.com": "tier_b"}

    def test_agency_class_supersedes_legacy_tier(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            (
                "- url: https://example.com/feed\n"
                "  agency_class: A\n"
                "  tier: tier_c\n"
            ),
        )
        m = cur._load_source_tier_map("v1")
        # agency_class A wins → tier_a, not legacy tier_c.
        assert m == {"example.com": "tier_a"}

    def test_unknown_class_falls_through(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 'Z' is not a valid agency_class — entry should be skipped silently.
        self._write_sources(
            tmp_path,
            monkeypatch,
            "v1",
            "- url: https://example.com/feed\n  agency_class: Z\n",
        )
        assert cur._load_agency_class_map("v1") == {}
        assert cur._load_source_tier_map("v1") == {}
