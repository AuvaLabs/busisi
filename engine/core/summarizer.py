"""Grounded article summariser.

Generates the body of OUR canonical /story/<slug>/ pages. Three rules
(per BUILD-DIRECTIVE Phase 2 module 9 + Phase 3 quality bar):

  1. Strict grounding. Every claim in the summary must derive from the
     source text we pass in. The system prompt forces this; the
     post-fetch validator double-checks (rejects responses that leak
     numbers or years not present in the input).
  2. Length: 50-80 words for the lede.
  3. "Why this matters" is a SEPARATE 1-2-sentence analysis caption,
     marked as analysis on the rendered page.

Called from ``pipeline.run_vertical`` post-persist via
``enrich_pending(vertical, max_articles)``. Articles processed in
fetched_at-ascending order so the most-stale rows lose the placeholder
banner first.

Cache: Redis-backed via ``llm_cache`` (TTL 30 days). Key is
``sha256("summarize:" + body[:MAX_CONTENT_CHARS])`` so re-running on
the same body is free.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy import select

from engine.core import llm_cache, llm_client
from engine.core.config import MAX_CONTENT_CHARS
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a strict news summariser. Your job: read the article and produce a grounded summary.

RULES:
1. Every claim in your output MUST appear in the source text. If a fact is not in the source, do not invent it.
2. The summary is a tight news lede — 50-80 words, first-sentence-leads, neutral voice.
3. "why_this_matters" is a SEPARATE 1-2 sentence analytical caption explaining why a reader should care. It is editorial commentary, not fact reporting.
4. Output strictly valid JSON: {"summary": "<50-80w lede>", "why_this_matters": "<1-2 sentences>"}.
5. Do not write headlines, taglines, or commentary OUTSIDE these two fields. Do not include the article URL or your reasoning.
6. If the source is too thin to summarise meaningfully (under ~50 words of body), set summary to a single one-sentence note explaining the source is brief, and set why_this_matters to "".
"""


def _build_user_prompt(title: str, body: str) -> str:
    return (
        f"HEADLINE: {title}\n\n"
        f"ARTICLE BODY:\n{body[:MAX_CONTENT_CHARS]}\n\n"
        "Return JSON: {\"summary\": ..., \"why_this_matters\": ...}"
    )


_NUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(\s*[kKmMbB])?\s*%?"
)
_SUFFIX_MULT = {"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}
_TOLERANCE = 0.01  # ±1 % wiggle for rounding ($676k ≈ 676,000)


def _numeric_values(text: str) -> set[float]:
    out: set[float] = set()
    for raw, suffix in _NUM_TOKEN_RE.findall(text):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suffix:
            value *= _SUFFIX_MULT[suffix.strip().lower()]
        out.add(value)
    return out


def _validate_grounded(summary: str, source_text: str) -> tuple[bool, str]:
    """Lightweight grounding sanity check — flag obvious hallucinations.

    Numbers compare on value, not surface form: ``10k`` → ``10,000`` is fine.
    A summary value passes if any source value is within ±1 % (or 0.5 for
    very small magnitudes).
    """
    if not summary or not source_text:
        return True, ""

    summary_values = _numeric_values(summary)
    source_values = _numeric_values(source_text)

    def _matches(v: float) -> bool:
        for s in source_values:
            if v == 0 and s == 0:
                return True
            if abs(v - s) <= max(_TOLERANCE * max(abs(v), abs(s)), 0.5):
                return True
        return False

    leaked = sorted(v for v in summary_values if not _matches(v))
    if leaked:
        return False, f"summary cites numbers not in source: {leaked[:3]}"

    summary_years = set(re.findall(r"\b(?:19|20)\d{2}\b", summary))
    source_years = set(re.findall(r"\b(?:19|20)\d{2}\b", source_text))
    leaked_years = summary_years - source_years
    if leaked_years:
        return False, f"summary cites years not in source: {sorted(leaked_years)}"
    return True, ""


def _grounding_source(article: Article) -> str:
    """Best available grounding text. Body preferred; fall back to summary."""
    if article.body and len(article.body.strip()) >= 200:
        return article.body
    return article.summary or ""


def summarize_one(article: Article, *, vertical: str) -> dict[str, Any] | None:
    """Run the LLM summariser on a single article. Returns updated fields or None on failure."""
    grounding = _grounding_source(article).strip()
    if len(grounding) < 80:
        return {
            "summary": article.summary,
            "why_this_matters": None,
            "summary_source": "feed",
            "skipped": "source_too_thin",
        }

    cache_key = llm_cache.make_cache_key("summarize", grounding)
    cached = llm_cache.get(cache_key)
    if cached is not None:
        return {
            "summary": cached.get("summary") or article.summary,
            "why_this_matters": cached.get("why_this_matters") or None,
            "summary_source": "llm",
            "_cached": True,
        }

    user = _build_user_prompt(article.title, grounding)
    try:
        raw = llm_client.call_llm(
            user_content=user,
            system_prompt=_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            caller="summarize",
            max_tokens=400,
        )
    except RuntimeError as exc:
        logger.warning("summarize call failed for %r: %s", article.title[:60], exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("summarizer returned non-JSON for %r", article.title[:60])
        return None

    summary = (parsed.get("summary") or "").strip()
    wtm = (parsed.get("why_this_matters") or "").strip() or None
    if not summary:
        logger.warning("summarizer returned empty summary for %r", article.title[:60])
        return None

    word_count = len(summary.split())
    if word_count < 30 or word_count > 110:
        logger.info(
            "summary for %r out-of-range (%d words); accepting anyway",
            article.title[:60],
            word_count,
        )

    ok, note = _validate_grounded(summary + " " + (wtm or ""), grounding)
    if not ok:
        logger.warning("grounding-validator FAILED for %r: %s", article.title[:60], note)
        return None

    payload = {"summary": summary, "why_this_matters": wtm}
    llm_cache.put(cache_key, payload)
    return {
        **payload,
        "summary_source": "llm",
        "_cached": False,
    }


def enrich_pending(
    vertical: str,
    *,
    max_articles: int = 20,
    sleep_between: float = 1.0,
) -> dict[str, int]:
    """Find articles with summary_source='feed' for the given vertical, run
    the summariser, update the DB. Returns counts dict.

    Featherless premium-model concurrency cost is 4 (plan limit 4), so
    calls are effectively serial. ``sleep_between`` adds breathing room.
    """
    Session = get_sessionmaker()
    counts = {"considered": 0, "updated": 0, "skipped": 0, "failed": 0, "cached": 0}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            logger.warning("vertical not found: %s", vertical)
            return counts

        rows = (
            session.execute(
                select(Article)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    Article.summary_source == "feed",
                )
                .order_by(Article.fetched_at.asc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )
        counts["considered"] = len(rows)
        logger.info("[%s] enriching %d pending summaries", vertical, len(rows))

        for article in rows:
            result = summarize_one(article, vertical=vertical)
            if result is None:
                counts["failed"] += 1
                continue
            if result.get("skipped"):
                counts["skipped"] += 1
                continue
            article.summary = result["summary"]
            article.summary_source = result["summary_source"]
            article.why_this_matters = result["why_this_matters"]
            session.commit()
            if result.get("_cached"):
                counts["cached"] += 1
            counts["updated"] += 1
            if sleep_between and not result.get("_cached"):
                time.sleep(sleep_between)

    logger.info(
        "[%s] enrichment done: considered=%d updated=%d skipped=%d failed=%d cached=%d",
        vertical, counts["considered"], counts["updated"], counts["skipped"],
        counts["failed"], counts["cached"],
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.summarizer modelwatch [--max 50] [--sleep 1.0]``"""
    import argparse

    parser = argparse.ArgumentParser(description="Run grounded summariser on pending articles")
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch, vested)")
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    counts = enrich_pending(args.vertical, max_articles=args.max, sleep_between=args.sleep)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
