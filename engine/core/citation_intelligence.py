"""Cited-by intelligence — read views over CitationEvent (C4).

Surfaces the AI-citation telemetry the rollup populates (R7 fed it). Three
read primitives:

  - top_cited_stories(vertical, days=7, allowlist_only=False)
        Stories ranked by total bot hits in the window. Used by the operator
        weekly report and (later) the public "Cited by" page.

  - citations_by_bot(vertical, days=7)
        Per-bot hit totals — quick view of which AI surface is citing us.

  - cited_today_count(vertical)
        Single-number daily summary for the command-center dashboard.

Crawler allowlist is the union of bots that surface citations to humans.
Filtering to allowlist-only gives a clean revenue-relevant signal; raw
totals include every crawler that hits a /story/<slug>/ URL.
"""
# ruff: noqa: PLC0415

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select

from engine.core.db import (
    Article,
    CitationEvent,
    Story,
    StoryArticle,
    Vertical,
    get_sessionmaker,
)

logger = logging.getLogger(__name__)


# Bots whose hits are "real citations" — they surface a clickable link to
# humans. Other crawler hits (training, archival, etc.) still get rolled up
# into ``citation_events`` for completeness but should be filtered for the
# revenue-relevant view.
KNOWN_CRAWLERS = frozenset(
    {
        # OpenAI
        "OAI-SearchBot",
        "ChatGPT-User",
        "GPTBot",
        # Anthropic
        "Claude-SearchBot",
        "Claude-User",
        "ClaudeBot",
        "anthropic-ai",
        # Perplexity
        "PerplexityBot",
        "Perplexity-User",
        # Google
        "Googlebot",
        "Google-Extended",
        # Microsoft / Bing
        "Bingbot",
        # Apple
        "Applebot",
        "Applebot-Extended",
        # Cohere
        "cohere-ai",
        # Meta
        "Meta-ExternalAgent",
    }
)


def top_cited_stories(
    vertical_name: str,
    *,
    days: int = 7,
    limit: int = 25,
    allowlist_only: bool = True,
) -> list[dict[str, Any]]:
    """Return the top stories by bot hit count in the last ``days``."""
    Session = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return out

        stmt = (
            select(
                CitationEvent.story_id,
                func.coalesce(func.sum(CitationEvent.hit_count), 0).label("hits"),
            )
            .join(Story, Story.id == CitationEvent.story_id)
            .where(Story.vertical_id == v.id, CitationEvent.ts >= since)
            .group_by(CitationEvent.story_id)
            .order_by(desc("hits"))
            .limit(limit)
        )
        if allowlist_only:
            stmt = stmt.where(CitationEvent.bot_name.in_(KNOWN_CRAWLERS))

        rows = session.execute(stmt).all()
        if not rows:
            return out

        story_ids = [r.story_id for r in rows]
        stories = {
            st.id: st
            for st in session.execute(
                select(Story).where(Story.id.in_(story_ids))
            ).scalars()
        }
        primary_slug_by_story = dict(
            session.execute(
                select(StoryArticle.story_id, Article.slug)
                .join(Article, Article.id == StoryArticle.article_id)
                .where(
                    StoryArticle.story_id.in_(story_ids),
                    StoryArticle.is_primary.is_(True),
                )
            ).all()
        )

        for r in rows:
            story = stories.get(r.story_id)
            if story is None:
                continue
            out.append(
                {
                    "story_id": story.id,
                    "headline": story.canonical_headline,
                    "primary_slug": primary_slug_by_story.get(story.id),
                    "narrative_version": story.narrative_version or 0,
                    "hits": int(r.hits),
                    "state": story.state,
                }
            )
    return out


def citations_by_bot(
    vertical_name: str,
    *,
    days: int = 7,
    allowlist_only: bool = True,
) -> dict[str, int]:
    """Return ``{bot_name: total_hits}`` for the last ``days``."""
    Session = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=days)
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return {}
        stmt = (
            select(
                CitationEvent.bot_name,
                func.coalesce(func.sum(CitationEvent.hit_count), 0).label("hits"),
            )
            .join(Story, Story.id == CitationEvent.story_id)
            .where(Story.vertical_id == v.id, CitationEvent.ts >= since)
            .group_by(CitationEvent.bot_name)
            .order_by(desc("hits"))
        )
        if allowlist_only:
            stmt = stmt.where(CitationEvent.bot_name.in_(KNOWN_CRAWLERS))
        return {row.bot_name: int(row.hits) for row in session.execute(stmt).all()}


def cited_today_count(
    vertical_name: str, *, allowlist_only: bool = True
) -> int:
    """Return total bot hits resolved to citations today (UTC)."""
    Session = get_sessionmaker()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return 0
        stmt = (
            select(func.coalesce(func.sum(CitationEvent.hit_count), 0))
            .join(Story, Story.id == CitationEvent.story_id)
            .where(Story.vertical_id == v.id, CitationEvent.ts >= today_start)
        )
        if allowlist_only:
            stmt = stmt.where(CitationEvent.bot_name.in_(KNOWN_CRAWLERS))
        return int(session.execute(stmt).scalar() or 0)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.citation_intelligence <vertical> [--days 7]``"""
    import argparse

    parser = argparse.ArgumentParser(description="Cited-by intelligence report")
    parser.add_argument("vertical")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--include-all-bots",
        action="store_true",
        help="Include hits from non-allowlisted crawlers",
    )
    args = parser.parse_args(argv)

    allow_only = not args.include_all_bots
    print(f"\n=== Cited by (last {args.days}d, vertical={args.vertical}) ===")
    print(
        f"Today's allowlisted hits: "
        f"{cited_today_count(args.vertical, allowlist_only=allow_only)}"
    )

    print("\nBy bot:")
    for bot, hits in citations_by_bot(
        args.vertical, days=args.days, allowlist_only=allow_only
    ).items():
        marker = " " if bot in KNOWN_CRAWLERS else "?"
        print(f"  {marker} {bot:<28} {hits:>6}")

    print(f"\nTop {args.limit} stories:")
    for s in top_cited_stories(
        args.vertical,
        days=args.days,
        limit=args.limit,
        allowlist_only=allow_only,
    ):
        print(
            f"  {s['hits']:>6}  /story/{s['primary_slug']}/  "
            f"v{s['narrative_version']}  [{s['state']}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
