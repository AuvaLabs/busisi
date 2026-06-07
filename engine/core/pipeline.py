"""Minimal pipeline orchestrator — composes the implemented core modules.

This is the Phase 2/3 minimum-viable runner. It chains:

    feed_loader.load_feeds(vertical)
      ↓
    feed_fetcher.fetch_articles(feeds)
      ↓
    deduplicator.deduplicate_articles(articles, vertical=..., guard_patterns=...)
      ↓
    classifier.classify_article(...)  for each article
      ↓
    return list[dict]   (downstream: story_clusterer + summarizer + renderer)

Phase 3+ will extend this with article_scraper (full content fetch),
entity_extractor, story_clusterer, summarizer, and Postgres persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from engine.core import (
    article_scraper,
    classifier,
    deduplicator,
    extractor,
    feed_fetcher,
    feed_loader,
    research_writer,
    story_lifecycle,
    summarizer,
)
from engine.core.config import vertical_dir
from engine.core.db import Article, Vertical, get_sessionmaker
from engine.core.safe_http import install_ssrf_guard
from engine.core.slug import make_slug, make_unique_slug

logger = logging.getLogger(__name__)


def _load_config(vertical_id: str) -> dict[str, Any]:
    path = vertical_dir(vertical_id) / "config.yaml"
    if not path.exists():
        logger.warning("config.yaml missing for %s at %s", vertical_id, path)
        return {}
    with open(path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return data


def _parse_published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        from dateutil import parser as dateparser

        dt = dateparser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, ImportError):
        return None


def _persist_articles(vertical_id: str, articles: list[dict[str, Any]]) -> int:
    """Insert articles for the named vertical, skipping (vertical_id, hash) dups.

    Returns the count of newly-inserted rows.
    """
    Session = get_sessionmaker()
    inserted = 0
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_id)
        ).scalar_one_or_none()
        if v is None:
            logger.warning(
                "vertical row not found for %s — skipping persist", vertical_id
            )
            return 0
        for article in articles:
            base = make_slug(article["title"])
            slug = make_unique_slug(session, v.id, base)
            row = Article(
                vertical_id=v.id,
                hash=article["hash"],
                slug=slug,
                title=article["title"],
                link=article["link"],
                source=article.get("source", ""),
                feed_region=article.get("feed_region", "Global"),
                summary=article.get("summary", ""),
                summary_source="feed",
                body=article.get("body"),
                published_at=_parse_published(article.get("published", "")),
                labels=article.get("labels"),
            )
            session.add(row)
            try:
                session.commit()
                inserted += 1
            except IntegrityError:
                session.rollback()
                logger.debug("article hash %s already in db", article["hash"][:12])
    return inserted


def run_vertical(
    vertical_id: str,
    *,
    max_feeds: int | None = None,
    classify: bool = True,
    persist: bool = False,
    scrape: bool = False,
    enrich: bool = False,
    enrich_max: int = 20,
    extract: bool = False,
    extract_max: int = 20,
    rewrite: bool = False,
    rewrite_max: int = 10,
    rewrite_orphans: bool = False,
    rewrite_orphans_max: int = 20,
) -> list[dict[str, Any]]:
    """Run the ingestion pipeline for one vertical and return enriched articles."""
    install_ssrf_guard()
    classifier.reset_escalation_budget(vertical_id)

    cfg = _load_config(vertical_id)
    topics: dict[str, list[str]] = cfg.get("topics", {}) or {}
    guard_patterns: list[str] = cfg.get("non_dedup_keys", []) or []
    always_escalate: list[str] = cfg.get("always_escalate", []) or []
    budget: int = int(cfg.get("escalation_budget", 30))
    title_anchored: frozenset[str] = frozenset(
        (cfg.get("classifier", {}) or {}).get("title_anchored_topics", []) or []
    )

    feeds = feed_loader.load_feeds(vertical_id)
    if max_feeds is not None:
        feeds = feeds[:max_feeds]
    logger.info("[%s] fetching %d feeds", vertical_id, len(feeds))

    raw = feed_fetcher.fetch_articles(feeds)
    logger.info("[%s] fetched %d entries", vertical_id, len(raw))

    unique = deduplicator.deduplicate_articles(
        raw, vertical=vertical_id, guard_patterns=guard_patterns
    )
    logger.info("[%s] %d unique after dedup", vertical_id, len(unique))

    if scrape and unique:
        scraped = article_scraper.scrape_articles([a["link"] for a in unique])
        for article in unique:
            result = scraped.get(article["link"]) or {}
            if result.get("success"):
                article["body"] = result.get("body")
                article["image_url"] = result.get("image_url")
                article["author"] = result.get("author")
                article["language"] = result.get("language")
                article["word_count"] = result.get("word_count")

    if classify and topics:
        for article in unique:
            result = classifier.classify_article(
                title=article["title"],
                content=article.get("summary") or None,
                taxonomy=topics,
                vertical=vertical_id,
                always_escalate=always_escalate,
                escalation_budget=budget,
                title_anchored=title_anchored,
            )
            article["labels"] = result["labels"]
            article["_classifier"] = {
                "ai_enhanced": result.get("_ai_enhanced", False),
                "cached": result.get("_cached", False),
            }

    if persist:
        inserted = _persist_articles(vertical_id, unique)
        logger.info("[%s] persisted %d new articles", vertical_id, inserted)

    if enrich and persist:
        # Run AFTER persist so we summarise the rows we just stored. Cap per
        # tick to keep LLM cost predictable; older rows tagged summary_source
        # = 'feed' are processed oldest-first.
        counts = summarizer.enrich_pending(vertical_id, max_articles=enrich_max)
        logger.info("[%s] summariser enrichment: %s", vertical_id, counts)

    if extract and persist:
        # R4a — Pass 0 per-article structured extract. Runs after summarizer
        # so the same per-tick budget visibility applies. The extract is the
        # input to R4b's cluster-level rewriter (Pass 1 + Pass 2).
        ex_counts = extractor.extract_pending(
            vertical_id, max_articles=extract_max
        )
        logger.info("[%s] pass0_extract: %s", vertical_id, ex_counts)

    if rewrite and persist:
        # R7 — pre-rewrite lifecycle: promote draft Stories that satisfy the
        # ripeness criterion (≥2 Class A-C members + cooldown elapsed), then
        # archive stale published Stories before the rewriter runs.
        ready_counts = story_lifecycle.mark_ready(vertical_id)
        logger.info("[%s] mark_ready: %s", vertical_id, ready_counts)
        archive_counts = story_lifecycle.archive_stale(vertical_id)
        logger.info("[%s] archive_stale: %s", vertical_id, archive_counts)

        # R4b — multi-source rewriter. Operates on Stories whose state is
        # draft/ready/revising, requires ≥2 cluster members each carrying a
        # Pass 0 structured_extract. Pass 1 (Qwen 32B, 2u) + Pass 2 (DeepSeek
        # V3 / Llama 4 Maverick, 4u).
        rw_counts = research_writer.rewrite_pending(
            vertical_id, max_stories=rewrite_max
        )
        logger.info("[%s] research_writer: %s", vertical_id, rw_counts)

        # R7 — post-rewrite citation rollup: aggregate any new bot_hits whose
        # path resolves to a Story slug into per-(story, bot, day) buckets.
        rollup_counts = story_lifecycle.rollup_citations(vertical_id)
        logger.info("[%s] rollup_citations: %s", vertical_id, rollup_counts)

    if rewrite_orphans and persist:
        # F2 (2026-05-10) — single-source enriched rewriter for orphan
        # articles (cluster of 1). Cluster-wins precedence: skips articles
        # already in a published Story.narrative. Targets standard +
        # researcher tier articles with structured_extract.
        orphan_counts = research_writer.rewrite_orphan_pending(
            vertical_id, max_articles=rewrite_orphans_max
        )
        logger.info("[%s] rewrite_orphan_pending: %s", vertical_id, orphan_counts)

    return unique


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m engine.core.pipeline modelwatch [--max-feeds 3] [--no-classify]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run grimoire ingestion pipeline")
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch)")
    parser.add_argument("--max-feeds", type=int, default=None)
    parser.add_argument("--no-classify", action="store_true")
    parser.add_argument("--persist", action="store_true",
                        help="Insert deduped articles into postgres")
    parser.add_argument("--scrape", action="store_true",
                        help="Fetch full article body via trafilatura")
    parser.add_argument("--enrich", action="store_true",
                        help="Run grounded LLM summariser on pending rows")
    parser.add_argument("--enrich-max", type=int, default=20,
                        help="Max rows to summarise per call (cron-friendly)")
    parser.add_argument("--extract", action="store_true",
                        help="Run Pass 0 structured extractor (R4a)")
    parser.add_argument("--extract-max", type=int, default=20,
                        help="Max rows to Pass-0-extract per call")
    parser.add_argument("--rewrite", action="store_true",
                        help="Run multi-source rewriter (R4b)")
    parser.add_argument("--rewrite-max", type=int, default=10,
                        help="Max stories to rewrite per call")
    parser.add_argument("--rewrite-orphans", action="store_true",
                        help="Run single-source enriched rewriter for orphan articles (F2)")
    parser.add_argument("--rewrite-orphans-max", type=int, default=20,
                        help="Max orphan articles to rewrite per call")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    out = run_vertical(
        args.vertical,
        max_feeds=args.max_feeds,
        classify=not args.no_classify,
        persist=args.persist,
        scrape=args.scrape,
        enrich=args.enrich,
        enrich_max=args.enrich_max,
        extract=args.extract,
        extract_max=args.extract_max,
        rewrite=args.rewrite,
        rewrite_max=args.rewrite_max,
        rewrite_orphans=args.rewrite_orphans,
        rewrite_orphans_max=args.rewrite_orphans_max,
    )
    print(f"\n=== summary ===\n{len(out)} articles after pipeline\n")
    for article in out[:10]:
        labels = ", ".join(
            f"{label['label']}({label['confidence']})"
            for label in article.get("labels", [])
        )
        print(f"- [{article['feed_region']}] {article['title'][:80]}")
        if labels:
            print(f"    labels: {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
