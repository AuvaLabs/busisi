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
    feed_fetcher,
    feed_loader,
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
) -> list[dict[str, Any]]:
    """Run the ingestion pipeline for one vertical and return enriched articles."""
    install_ssrf_guard()
    classifier.reset_escalation_budget(vertical_id)

    cfg = _load_config(vertical_id)
    topics: dict[str, list[str]] = cfg.get("topics", {}) or {}
    guard_patterns: list[str] = cfg.get("non_dedup_keys", []) or []
    always_escalate: list[str] = cfg.get("always_escalate", []) or []
    budget: int = int(cfg.get("escalation_budget", 30))

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
            )
            article["labels"] = result["labels"]
            article["_classifier"] = {
                "ai_enhanced": result.get("_ai_enhanced", False),
                "cached": result.get("_cached", False),
            }

    if persist:
        inserted = _persist_articles(vertical_id, unique)
        logger.info("[%s] persisted %d new articles", vertical_id, inserted)

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
