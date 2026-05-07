"""Editorial curator — gates articles into tiers before LLM enrichment.

Rule-based scoring (Phase 22a — no LLM). Combines three signals into a
0..1 confidence:

  source_auth   ∈ [0, 0.40]  — source-domain authority from sources.yaml
                               tier annotations (tier_a/b/c).
  title_shape   ∈ [0, 0.30]  — penalty applied for discussion-style
                               headlines ("re:", "should i", "anyone
                               else", "[D]", question-marks at end of
                               short titles, etc.).
  entity_strength ∈ [0, 0.30] — capped function of named-entity count
                               from the entity_extractor (Phase 14a).

Tier mapping:

  score ≥ 0.7   → "standard"     (summarizer)
  0.4 ≤ s < 0.7 → "researcher"   (researcher → rewriter; for now this
                                   bucket is also where 22d will hand
                                   the LLM-judge for refinement).
  s < 0.4       → "skip"         (no enrichment, hidden from front page,
                                   /story/ rendered with noindex)

Bumping ``CURATOR_VERSION`` retroactively re-triggers scoring on rows
where ``articles.curator_version < CURATOR_VERSION`` so weight tweaks
fan out cleanly.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import yaml
from sqlalchemy import func, select

from engine.core.config import vertical_dir
from engine.core.db import (
    Article,
    ArticleEntity,
    Vertical,
    get_sessionmaker,
)

logger = logging.getLogger(__name__)


# Bump on rule-weight changes — backfill re-scores rows where
# Article.curator_version < this value.
CURATOR_VERSION = 1


# Score weights — keep total of max contributions == 1.0.
_SOURCE_AUTH_WEIGHT = 0.40
_TITLE_SHAPE_WEIGHT = 0.30
_ENTITY_STRENGTH_WEIGHT = 0.30


# Tier thresholds.
_TIER_STANDARD = 0.70
_TIER_RESEARCHER = 0.40


# Title shape — discussion-style penalties (lowercased title matched).
_DISCUSSION_PREFIXES = (
    "re:",
    "re :",
    "re-",
    "[d]",
    "[r]",
    "[discussion]",
    "[question]",
    "ask hn",
)
_DISCUSSION_PHRASES = (
    "should i ",
    "anyone else ",
    "any tips",
    "what would you do",
    "what should i",
    "is this normal",
    "am i the only one",
    "talk me out of",
    "am i crazy",
)
_QUESTION_END = re.compile(r"\?\s*$")
_SHORT_TITLE_THRESHOLD = 6  # words


# Default source authority — applied when sources.yaml has no annotation.
_SOURCE_AUTH_DEFAULT = 0.20

# Authority-tier → multiplier on _SOURCE_AUTH_WEIGHT.
# Legacy `tier:` keys are kept for backward compatibility; new sources should
# use `agency_class:` (A-F).
_TIER_WEIGHTS: dict[str, float] = {
    "tier_a": 1.00,   # Reuters, AP, Bloomberg, official lab blogs
    "tier_b": 0.65,   # trade press, established blogs, gov agencies
    "tier_c": 0.30,   # forums, Reddit, discussion sites (deprecated; Class G removed)
    "default": 0.50,
}

# R1 — agency_class → multiplier on _SOURCE_AUTH_WEIGHT.
#   A  Wire / news agency           full authority
#   B  Newspaper of record          full authority
#   C  Trade press                  mid authority (original reporting, not wire)
#   D  Primary / official source    full authority for own announcements
#   E  Research aggregator          mid authority (credible, not breaking)
#   F  Analysis / commentary        low authority (NEVER primary citation;
#                                    rewriter validator rejects F-only sources)
# Class G is removed at the source-list level — see verticals/*/sources.yaml.
_AGENCY_CLASS_WEIGHTS: dict[str, float] = {
    "a": 1.00,
    "b": 1.00,
    "c": 0.65,
    "d": 1.00,
    "e": 0.65,
    "f": 0.30,
}


def _load_source_tier_map(vertical_name: str) -> dict[str, str]:
    """Read ``verticals/<v>/sources.yaml`` → ``{host: 'tier_x'}``.

    Reads `agency_class` first (canonical, R1+), falls back to legacy `tier:`.
    Returned values use the legacy `tier_a/b/c` vocabulary so downstream
    weighting stays uniform; ``_load_agency_class_map`` exposes the raw
    A-F letter for the rewriter's primary-citation eligibility check.
    """
    path = vertical_dir(vertical_name) / "sources.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        logger.warning("could not read %s: %s", path, exc)
        return {}
    out: dict[str, str] = {}
    sources = data.get("sources", []) if isinstance(data, dict) else data
    if not isinstance(sources, list):
        return out
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or entry.get("rss") or entry.get("feed")
        if not url:
            continue
        host = urlparse(url).netloc.removeprefix("www.").lower()
        if not host:
            continue
        agency = str(entry.get("agency_class", "")).strip().lower()
        if agency in _AGENCY_CLASS_WEIGHTS:
            # Translate A-F into the legacy tier vocabulary so downstream
            # weighting stays uniform.
            weight = _AGENCY_CLASS_WEIGHTS[agency]
            if weight >= 0.95:
                out[host] = "tier_a"
            elif weight >= 0.50:
                out[host] = "tier_b"
            else:
                out[host] = "tier_c"
            continue
        legacy = str(entry.get("tier", "")).strip().lower()
        if legacy:
            out[host] = legacy
    return out


def _load_agency_class_map(vertical_name: str) -> dict[str, str]:
    """Read ``verticals/<v>/sources.yaml`` → ``{host: 'A'..'F'}``.

    Used by the rewriter validator to enforce primary-citation eligibility
    (Class F can never be the sole source of a factual claim).
    """
    path = vertical_dir(vertical_name) / "sources.yaml"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        logger.warning("could not read %s: %s", path, exc)
        return {}
    out: dict[str, str] = {}
    sources = data.get("sources", []) if isinstance(data, dict) else data
    if not isinstance(sources, list):
        return out
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or entry.get("rss") or entry.get("feed")
        agency = str(entry.get("agency_class", "")).strip().upper()
        if not url or agency not in {"A", "B", "C", "D", "E", "F"}:
            continue
        host = urlparse(url).netloc.removeprefix("www.").lower()
        if host:
            out[host] = agency
    return out


def _short_host(source_url: str) -> str:
    return urlparse(source_url).netloc.removeprefix("www.").lower()


# ---- Per-signal scorers -----------------------------------------------------


def score_source_authority(
    source_url: str, tier_map: dict[str, str]
) -> float:
    host = _short_host(source_url)
    tier = tier_map.get(host)
    weight = _TIER_WEIGHTS.get(tier or "default", _SOURCE_AUTH_DEFAULT)
    return _SOURCE_AUTH_WEIGHT * weight


def score_title_shape(title: str) -> float:
    """Higher = more declarative, news-like. Lower = discussion/question."""
    if not title:
        return 0.0
    t = title.strip().lower()
    for prefix in _DISCUSSION_PREFIXES:
        if t.startswith(prefix):
            return 0.0
    for phrase in _DISCUSSION_PHRASES:
        if phrase in t:
            return 0.0
    if _QUESTION_END.search(t):
        words = len(t.split())
        if words <= _SHORT_TITLE_THRESHOLD:
            return 0.0
        return _TITLE_SHAPE_WEIGHT * 0.4
    return _TITLE_SHAPE_WEIGHT


def score_entity_strength(entity_count: int) -> float:
    """0 entities → 0; ≥3 → full weight; 1 or 2 → linear."""
    if entity_count <= 0:
        return 0.0
    if entity_count >= 3:
        return _ENTITY_STRENGTH_WEIGHT
    return _ENTITY_STRENGTH_WEIGHT * (entity_count / 3.0)


def _decide_tier(score: float) -> str:
    if score >= _TIER_STANDARD:
        return "standard"
    if score >= _TIER_RESEARCHER:
        return "researcher"
    return "skip"


# ---- Public API -------------------------------------------------------------


def score_article(
    article_id: int,
    *,
    vertical_name: str,
    tier_map: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Score one article in-DB. Persists ``curator_*`` columns."""
    if tier_map is None:
        tier_map = _load_source_tier_map(vertical_name)

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        article = session.get(Article, article_id)
        if article is None:
            return None
        entity_count = (
            session.execute(
                select(func.count())
                .select_from(ArticleEntity)
                .where(ArticleEntity.article_id == article_id)
            ).scalar()
            or 0
        )
        signals = {
            "source_auth": round(
                score_source_authority(article.source, tier_map), 4
            ),
            "title_shape": round(score_title_shape(article.title), 4),
            "entity_strength": round(score_entity_strength(entity_count), 4),
            "entity_count": int(entity_count),
            "judge": None,  # Filled in Phase 22d for gray-zone rows.
        }
        score = round(
            signals["source_auth"]
            + signals["title_shape"]
            + signals["entity_strength"],
            4,
        )
        tier = _decide_tier(score)

        article.curator_score = score
        article.curator_tier = tier
        article.curator_signals = signals
        article.curator_version = CURATOR_VERSION
        session.commit()

        return {
            "article_id": article_id,
            "score": score,
            "tier": tier,
            "signals": signals,
        }


def score_pending(
    vertical_name: str,
    *,
    max_articles: int = 500,
) -> dict[str, int]:
    """Score every article whose ``curator_version < CURATOR_VERSION``."""
    SessionLocal = get_sessionmaker()
    counts = {
        "considered": 0,
        "scored": 0,
        "skip": 0,
        "researcher": 0,
        "standard": 0,
    }
    tier_map = _load_source_tier_map(vertical_name)
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        ids = (
            session.execute(
                select(Article.id)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    Article.curator_version < CURATOR_VERSION,
                )
                .order_by(Article.fetched_at.asc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )

    for aid in ids:
        result = score_article(aid, vertical_name=vertical_name, tier_map=tier_map)
        if result is None:
            continue
        counts["considered"] += 1
        counts["scored"] += 1
        counts[result["tier"]] += 1
    logger.info("[%s] curator: %s", vertical_name, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.curator modelwatch [--max 500]``"""
    import argparse

    parser = argparse.ArgumentParser(description="Score articles into editorial tiers")
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=500, dest="max_articles")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    counts = score_pending(args.vertical, max_articles=args.max_articles)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
