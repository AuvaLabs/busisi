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
from typing import Any

import yaml

from engine.core import classifier, deduplicator, feed_fetcher, feed_loader
from engine.core.config import vertical_dir
from engine.core.safe_http import install_ssrf_guard

logger = logging.getLogger(__name__)


def _load_config(vertical_id: str) -> dict[str, Any]:
    path = vertical_dir(vertical_id) / "config.yaml"
    if not path.exists():
        logger.warning("config.yaml missing for %s at %s", vertical_id, path)
        return {}
    with open(path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return data


def run_vertical(
    vertical_id: str,
    *,
    max_feeds: int | None = None,
    classify: bool = True,
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

    if not classify or not topics:
        return unique

    enriched: list[dict[str, Any]] = []
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
        enriched.append(article)
    return enriched


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m engine.core.pipeline modelwatch [--max-feeds 3] [--no-classify]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run grimoire ingestion pipeline")
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch)")
    parser.add_argument("--max-feeds", type=int, default=None)
    parser.add_argument("--no-classify", action="store_true")
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
