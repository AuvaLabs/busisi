"""Story state machine + citation-event rollup (R7).

State transitions::

    draft       just clustered; awaiting ripeness check
       ↓ mark_ready  (>=2 Class A-C members + 30min cooldown elapsed)
    ready       queued for the rewriter (research_writer.rewrite_pending)
       ↓ research_writer
    published   narrative committed and rendered
       ↓ archive_stale  (24h since last revision)
    archived    no more rewrites
       ↑ mark_revising_on_new_link  (new A-E source joins) → revising
    revising    queued for revision-rewrite
       ↓ research_writer

The rollup converts ``BotHit`` rows whose path matches ``/story/<slug>/`` into
per-(story, bot, day) ``CitationEvent`` aggregates. The harness audit and the
front-end "Cited by" surface read from ``CitationEvent`` rather than re-doing
the join on every render.
"""
# ruff: noqa: PLC0415
# PLC0415: CLI argparse import lives in main(); pre-existing engine.core pattern.

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from engine.core.curator import _load_agency_class_map
from engine.core.db import (
    Article,
    BotHit,
    CitationEvent,
    Story,
    StoryArticle,
    Vertical,
    get_sessionmaker,
)

logger = logging.getLogger(__name__)


_PRIMARY_CLASSES = {"A", "B", "C"}
_RIPE_CLASSES = {"A", "B", "C", "D", "E"}
_STORY_PATH_RE = re.compile(r"^/story/([a-z0-9][a-z0-9-]+)/?")


def _host_of(url: str) -> str:
    h = url.replace("https://", "").replace("http://", "")
    return h.split("/", 1)[0].removeprefix("www.").lower()


def mark_ready(
    vertical_name: str,
    *,
    min_a_to_c: int = 2,
    cooldown_minutes: int = 30,
) -> dict[str, int]:
    """Promote ``draft`` Stories that satisfy ripeness to ``ready``."""
    Session = get_sessionmaker()
    counts = {"considered": 0, "promoted": 0}
    now = datetime.now(UTC)
    cooldown = timedelta(minutes=cooldown_minutes)
    agency_map = _load_agency_class_map(vertical_name)
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        rows = (
            session.execute(
                select(Story)
                .where(Story.vertical_id == v.id, Story.state == "draft")
                .order_by(Story.created_at.asc())
            )
            .scalars()
            .all()
        )
        counts["considered"] = len(rows)
        for story in rows:
            created = story.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if (now - created) < cooldown:
                continue
            members = (
                session.execute(
                    select(Article)
                    .join(StoryArticle, StoryArticle.article_id == Article.id)
                    .where(StoryArticle.story_id == story.id)
                )
                .scalars()
                .all()
            )
            primary_count = sum(
                1
                for m in members
                if agency_map.get(_host_of(m.source)) in _PRIMARY_CLASSES
            )
            if primary_count >= min_a_to_c:
                story.state = "ready"
                counts["promoted"] += 1
        session.commit()
    logger.info("[%s] mark_ready: %s", vertical_name, counts)
    return counts


def mark_revising_on_new_link(article_id: int) -> bool:
    """Called when a new article joins an existing Story.

    If the host is Class A-E and the Story is already ``published``, flip it
    to ``revising`` so the next rewriter tick refreshes the narrative.
    Returns True when the transition fires.
    """
    Session = get_sessionmaker()
    with Session() as session:
        link = session.execute(
            select(StoryArticle).where(StoryArticle.article_id == article_id)
        ).scalar_one_or_none()
        if link is None:
            return False
        story = session.get(Story, link.story_id)
        if story is None or story.state != "published":
            return False
        article = session.get(Article, article_id)
        if article is None:
            return False
        v = session.get(Vertical, story.vertical_id)
        if v is None:
            return False
        agency_map = _load_agency_class_map(v.name)
        if agency_map.get(_host_of(article.source)) not in _RIPE_CLASSES:
            return False
        story.state = "revising"
        session.commit()
        return True


def revise_story(story_id: int) -> bool:
    """Manually flip a published Story to ``revising`` (operator-triggered).

    C2 — used when the operator wants to force a re-rewrite (e.g. after
    bumping ``REWRITER_VERSION`` or to refresh a stale published story).
    Returns True on transition; False if the story is missing or in a state
    that can't transition (already archived, draft, etc.).
    """
    Session = get_sessionmaker()
    with Session() as session:
        story = session.get(Story, story_id)
        if story is None or story.state not in ("published", "ready"):
            return False
        story.state = "revising"
        session.commit()
        return True


def archive_stale(
    vertical_name: str, *, hours: int = 24
) -> dict[str, int]:
    """Archive published Stories with no revision in the last ``hours``."""
    Session = get_sessionmaker()
    counts = {"considered": 0, "archived": 0}
    threshold = datetime.now(UTC) - timedelta(hours=hours)
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        rows = (
            session.execute(
                select(Story).where(
                    Story.vertical_id == v.id,
                    Story.state == "published",
                )
            )
            .scalars()
            .all()
        )
        counts["considered"] = len(rows)
        for story in rows:
            updated = story.narrative_updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if updated is None or updated < threshold:
                story.state = "archived"
                counts["archived"] += 1
        session.commit()
    logger.info("[%s] archive_stale: %s", vertical_name, counts)
    return counts


def rollup_citations(
    vertical_name: str, *, since_hours: int = 24
) -> dict[str, int]:
    """Aggregate ``BotHit`` rows whose path resolves to a Story slug into
    per-(story, bot, day) ``CitationEvent`` rows. Idempotent.
    """
    Session = get_sessionmaker()
    counts = {"hits_considered": 0, "events_written": 0, "events_updated": 0}
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        slug_to_story = {
            slug: sid
            for sid, slug in session.execute(
                select(Story.id, Article.slug)
                .join(StoryArticle, StoryArticle.story_id == Story.id)
                .join(Article, StoryArticle.article_id == Article.id)
                .where(Story.vertical_id == v.id, StoryArticle.is_primary)
            ).all()
        }
        if not slug_to_story:
            return counts

        hits = (
            session.execute(
                select(BotHit).where(
                    BotHit.vertical_id == v.id,
                    BotHit.ts >= since,
                )
            )
            .scalars()
            .all()
        )
        counts["hits_considered"] = len(hits)

        bucket: dict[tuple[int, str, datetime], int] = defaultdict(int)
        for hit in hits:
            m = _STORY_PATH_RE.match(hit.path)
            if not m:
                continue
            slug = m.group(1)
            sid = slug_to_story.get(slug)
            if sid is None:
                continue
            ts = hit.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
            bucket[(sid, hit.bot_name, day)] += 1

        for (sid, bot, day), n in bucket.items():
            existing = session.execute(
                select(CitationEvent).where(
                    CitationEvent.story_id == sid,
                    CitationEvent.bot_name == bot,
                    CitationEvent.ts == day,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    CitationEvent(
                        story_id=sid, bot_name=bot, ts=day, hit_count=n
                    )
                )
                counts["events_written"] += 1
            else:
                existing.hit_count = n
                counts["events_updated"] += 1
        session.commit()
    logger.info("[%s] rollup_citations: %s", vertical_name, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.story_lifecycle <vertical>``"""
    import argparse

    parser = argparse.ArgumentParser(description="Story lifecycle + citation rollup")
    parser.add_argument("vertical")
    parser.add_argument("--cooldown-minutes", type=int, default=30)
    parser.add_argument("--archive-hours", type=int, default=24)
    parser.add_argument("--rollup-hours", type=int, default=24)
    parser.add_argument(
        "--revise-story",
        type=int,
        default=None,
        help="Manually flip a published Story to revising (operator override)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.revise_story is not None:
        ok = revise_story(args.revise_story)
        print(f"revise_story({args.revise_story}): {ok}")
        return 0 if ok else 1

    print("mark_ready:", mark_ready(args.vertical, cooldown_minutes=args.cooldown_minutes))
    print("archive_stale:", archive_stale(args.vertical, hours=args.archive_hours))
    print("rollup_citations:", rollup_citations(args.vertical, since_hours=args.rollup_hours))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
