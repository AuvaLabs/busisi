"""LLM-judge stage for the curator (Phase 22d).

Refines tier decisions for articles whose rule-based score lands in
the gray zone (i.e. ``curator_tier == 'researcher'``). The judge sees
the title, source host, and short summary, and returns a 1-10
editorial-grade score plus a one-line reason. The score is mapped onto
the same tier ladder used by the rule-based curator:

  judge_score >= 7  → "standard"
  judge_score >= 4  → "researcher"
  judge_score < 4   → "skip"

The output is merged into ``Article.curator_signals["judge"]`` and the
final ``curator_tier`` reflects the judge's decision (overrides the
rule-based gray-zone bucket).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from engine.core import llm_cache, llm_client
from engine.core.config import MAX_CONTENT_CHARS
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


_JUDGE_TIER_STANDARD = 7
_JUDGE_TIER_RESEARCHER = 4


_SYSTEM_PROMPT = """You are a strict editorial curator for a grounded
news platform. Your job: rate one article on a 1-10 scale for whether
it is a news-grade story worth publishing.

Score guide:
  10 — major newsworthy event from an authoritative source
  7-9 — solid news from a reputable source
  4-6 — borderline / explainer / opinion piece / minor follow-up
  1-3 — discussion thread, personal anecdote, advice question, off-topic

RULES:
1. Score ONLY on what is in the input. Do not invent context.
2. Penalise discussion-style headlines, advice questions, and
   forum-thread reposts (Reddit, Hacker News meta-posts, etc.).
3. Reward named entities (organisations, products, people), verifiable
   claims, and authoritative source domains.
4. Output strictly valid JSON: {"score": <int 1..10>, "reason": "<one
   sentence, plain English, no quotes>"}.
"""


def _build_user_prompt(title: str, summary: str, source_host: str) -> str:
    return (
        f"SOURCE HOST: {source_host}\n"
        f"HEADLINE: {title}\n\n"
        f"SUMMARY:\n{(summary or '')[:MAX_CONTENT_CHARS]}\n\n"
        'Return JSON: {"score": <1-10>, "reason": "..."}'
    )


def _decide_tier(score: int) -> str:
    if score >= _JUDGE_TIER_STANDARD:
        return "standard"
    if score >= _JUDGE_TIER_RESEARCHER:
        return "researcher"
    return "skip"


def judge_article(article: Article) -> dict[str, Any] | None:
    """Run the LLM judge on one article. Returns ``{score, reason, tier}``
    or ``None`` on hard LLM failure or insufficient input."""
    title = article.title or ""
    summary = article.summary or ""
    if len(title) < 8 and len(summary) < 8:
        return None

    host = urlparse(article.source or "").netloc.removeprefix("www.").lower()
    cache_key = llm_cache.make_cache_key(
        "judge", f"{host}|{title}|{summary[:1000]}"
    )
    cached = llm_cache.get(cache_key)
    if isinstance(cached, dict) and "score" in cached:
        score = int(cached["score"])
        return {
            "score": score,
            "reason": str(cached.get("reason", ""))[:240],
            "tier": _decide_tier(score),
        }

    user = _build_user_prompt(title, summary, host)
    try:
        raw = llm_client.call_llm(
            user_content=user,
            system_prompt=_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            caller="judge",
            max_tokens=120,
        )
    except RuntimeError as exc:
        logger.warning(
            "curator-judge call failed for %r: %s", title[:60], exc
        )
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "curator-judge returned non-JSON for %r", title[:60]
        )
        return None

    try:
        score = int(parsed.get("score", 0))
    except (TypeError, ValueError):
        return None
    score = max(1, min(10, score))
    reason = str(parsed.get("reason", "")).strip()[:240]
    payload = {"score": score, "reason": reason}
    llm_cache.put(cache_key, payload)
    return {"score": score, "reason": reason, "tier": _decide_tier(score)}


def judge_pending(
    vertical: str,
    *,
    max_articles: int = 30,
) -> dict[str, int]:
    """Judge gray-zone rule-based curator results for the vertical."""
    SessionLocal = get_sessionmaker()
    counts = {
        "considered": 0,
        "standard": 0,
        "researcher": 0,
        "skip": 0,
        "failed": 0,
    }
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            return counts
        rows = (
            session.execute(
                select(Article)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    Article.curator_tier == "researcher",
                )
                .order_by(Article.fetched_at.asc())
                .limit(max_articles * 4)
            )
            .scalars()
            .all()
        )
        rows = [
            a
            for a in rows
            if not (
                isinstance(a.curator_signals, dict)
                and a.curator_signals.get("judge")
            )
        ][:max_articles]

    for article in rows:
        counts["considered"] += 1
        result = judge_article(article)
        if result is None:
            counts["failed"] += 1
            continue
        with SessionLocal() as session:
            row = session.get(Article, article.id)
            if row is None:
                continue
            signals = dict(row.curator_signals or {})
            signals["judge"] = {
                "score": result["score"],
                "reason": result["reason"],
            }
            row.curator_signals = signals
            row.curator_tier = result["tier"]
            session.commit()
        counts[result["tier"]] += 1

    logger.info("[%s] curator-judge: %s", vertical, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.curator_judge modelwatch [--max 30]``"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM-judge gray-zone articles")
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=30, dest="max_articles")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    counts = judge_pending(args.vertical, max_articles=args.max_articles)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
