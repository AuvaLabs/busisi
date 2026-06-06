"""Weekly digest builder.

Produces three artefacts per vertical per ISO week:

  * HTML email body (``email/weekly_digest.html``)
  * Plaintext email body (``email/weekly_digest.txt``)
  * On-site archive page at ``/digest/<YYYY-Www>/index.html``

Story selection: top ``limit`` articles whose ``published_at`` lies inside
the [week_start, week_end) window AND whose ``summary_source == "llm"``
(skip rows still showing the feed-banner placeholder). Newest first.

Phase 10 ships generation + archive only. Sending to confirmed subscribers
is Phase 10b — needs a ``last_digest_sent_at`` column + Postmark token.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from engine.core.config import DATA_DIR, GRIMOIRE_ROOT
from engine.core.db import (
    Article,
    Story,
    StoryArticle,
    Subscriber,
    Vertical,
    get_sessionmaker,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = GRIMOIRE_ROOT / "engine" / "shared" / "templates"
_DEFAULT_LIMIT = 10


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _iso_week_key(dt: datetime) -> str:
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _week_window(
    *, week_offset: int = 0, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for the requested ISO week.

    ``week_offset=0``  → current ISO week (Mon 00:00 UTC … next Mon 00:00 UTC).
    ``week_offset=-1`` → previous full ISO week.
    """
    now = now or datetime.now(timezone.utc)
    weekday = now.isoweekday()
    monday = datetime.combine(
        (now - timedelta(days=weekday - 1)).date(),
        time(0, 0, 0),
        tzinfo=timezone.utc,
    )
    start = monday + timedelta(weeks=week_offset)
    end = start + timedelta(days=7)
    return start, end


_CITE_RE = re.compile(r"\s*\[\d+\]")


def _lead(narrative: str | None, *, max_chars: int = 280) -> str:
    """First paragraph of a rewriter narrative, citations stripped, trimmed.

    The on-site narrative carries inline ``[N]`` citation markers and runs
    several paragraphs; the digest wants a short, clean lead blurb.
    """
    if not narrative:
        return ""
    text = _CITE_RE.sub("", narrative).strip()
    text = text.split("\n\n")[0].strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > 80:
            return cut[: idx + 1]
    return cut.rsplit(" ", 1)[0] + "…"


def _week_items(
    vertical_name: str,
    *,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    """Top items for one ISO week, newest first, as digest-ctx dicts.

    Sourced from what the site actually publishes:

      * **Published Stories** — the rewriter's multi-source narratives
        (``state="published"``, ``narrative`` set), bucketed by the week the
        story broke (``primary_published_at``). This is the current product.
      * **Legacy llm Articles** — single-source items enriched before the
        rewriter migration (``summary_source == "llm"``). Kept so historical
        weeks still populate; deduped against story primaries by slug.

    Before this, selection keyed only on ``summary_source == "llm"``, so every
    week after the 2026-05-07 rewriter cutover came up empty.
    """
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return []

        items: dict[str, dict[str, Any]] = {}

        # Any story with a composed narrative — NOT only state=="published".
        # The lifecycle moves a story to "archived" ~24h after publish, so a
        # state filter would drop almost every past week. `narrative IS NOT
        # NULL` is the same "has been published" signal the front page uses and
        # already excludes draft/ready clusters (which have no narrative yet).
        story_rows = session.execute(
            select(Story, Article)
            .join(StoryArticle, StoryArticle.story_id == Story.id)
            .join(Article, Article.id == StoryArticle.article_id)
            .where(
                Story.vertical_id == v.id,
                Story.narrative.is_not(None),
                Story.state != "draft",
                StoryArticle.is_primary.is_(True),
                Article.deleted_at.is_(None),
                Story.primary_published_at >= start,
                Story.primary_published_at < end,
            )
            .order_by(Story.primary_published_at.desc())
        ).all()
        for s, a in story_rows:
            items[a.slug] = {
                "title": s.canonical_headline,
                "slug": a.slug,
                "summary": _lead(s.narrative) or (s.why_this_matters or ""),
                "why_this_matters": s.why_this_matters,
                "source": a.source,
                "feed_region": a.feed_region,
                "published_at": s.primary_published_at,
                "story_path": f"/story/{a.slug}/",
                "vertical": vertical_name,
                "_sort": s.primary_published_at,
            }

        art_rows = session.execute(
            select(Article)
            .where(
                Article.vertical_id == v.id,
                Article.published_at.is_not(None),
                Article.published_at >= start,
                Article.published_at < end,
                Article.summary_source == "llm",
                Article.deleted_at.is_(None),
            )
            .order_by(Article.published_at.desc())
        ).scalars().all()
        for a in art_rows:
            if a.slug in items:
                continue
            items[a.slug] = {
                "title": a.title,
                "slug": a.slug,
                "summary": a.summary,
                "why_this_matters": a.why_this_matters,
                "source": a.source,
                "feed_region": a.feed_region,
                "published_at": a.published_at,
                "story_path": f"/story/{a.slug}/",
                "vertical": vertical_name,
                "_sort": a.published_at,
            }

        ordered = sorted(
            items.values(), key=lambda d: d["_sort"], reverse=True
        )[:limit]
        for d in ordered:
            d.pop("_sort", None)
        return ordered


def _vertical_meta(vertical_name: str) -> dict[str, Any]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return {"name": vertical_name, "display_name": vertical_name.title()}
        return {
            "name": v.name,
            "display_name": v.display_name,
            "accent_light": v.accent_light or "#B8743A",
            "accent_dark": v.accent_dark or "#D49464",
        }


def generate_digest(
    vertical_name: str,
    *,
    week_offset: int = 0,
    limit: int = _DEFAULT_LIMIT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the digest for one vertical / one ISO week.

    Returns ``{subject, html, text, articles, week_key, start, end, vertical}``.
    Empty ``articles`` is allowed — caller decides whether to suppress send.
    """
    start, end = _week_window(week_offset=week_offset, now=now)
    articles = _week_items(
        vertical_name, start=start, end=end, limit=limit
    )
    vertical = _vertical_meta(vertical_name)
    week_key = _iso_week_key(start)

    subject = f"{vertical['display_name']} — week of {start:%b %d, %Y}"
    if not articles:
        subject = f"{vertical['display_name']} — quiet week ({week_key})"

    env = _env()
    ctx: dict[str, Any] = {
        "vertical": vertical,
        "week_key": week_key,
        "week_start": start,
        "week_end": end,
        "subject": subject,
        "articles": articles,
    }
    html = env.get_template("email/weekly_digest.html").render(**ctx)
    text = env.get_template("email/weekly_digest.txt").render(**ctx)

    return {
        "subject": subject,
        "html": html,
        "text": text,
        "articles": ctx["articles"],
        "week_key": week_key,
        "start": start,
        "end": end,
        "vertical": vertical,
    }


def _output_dir(vertical_name: str) -> Path:
    return DATA_DIR / "output" / vertical_name


def _render_archive_html(digest: dict[str, Any]) -> str:
    """Render the branded on-site archive page (extends base.html).

    Distinct from ``digest["html"]``, which is the email-styled body kept
    for the email send path. Visitors hitting ``/digest/<key>/`` see the
    full site chrome (nav, footer, accent colours).
    """
    env = _env()
    vertical = digest["vertical"]
    archive_path = f"/digest/{digest['week_key']}/"
    return env.get_template("digest_archive.html").render(
        vertical=vertical,
        week_key=digest["week_key"],
        week_start=digest["start"],
        week_end=digest["end"],
        articles=digest["articles"],
        title=f"Weekly digest · {digest['week_key']}",
        description=(
            f"{vertical['display_name']} weekly digest — week of "
            f"{digest['start']:%b %d, %Y}."
        ),
        canonical_url=archive_path,
    )


def render_archive(
    vertical_name: str,
    *,
    week_offset: int = 0,
    limit: int = _DEFAULT_LIMIT,
    now: datetime | None = None,
) -> Path:
    digest = generate_digest(
        vertical_name, week_offset=week_offset, limit=limit, now=now
    )
    out_dir = _output_dir(vertical_name) / "digest" / digest["week_key"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(_render_archive_html(digest), encoding="utf-8")
    logger.info(
        "rendered digest archive -> %s (%d stories)",
        path,
        len(digest["articles"]),
    )
    return path


def send_pending_digests(
    vertical_name: str,
    *,
    week_offset: int = -1,
    limit: int = _DEFAULT_LIMIT,
    sleep_between: float = 0.1,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send the digest to confirmed subscribers who haven't received this week.

    Default ``week_offset=-1`` ships the previous full ISO week — designed to
    run Sunday afternoon UTC, after the cron pipeline has finished its last
    enrichment tick of the week.

    Idempotent at the row level: a subscriber whose
    ``last_digest_sent_at >= week_start`` is skipped. Successful sends advance
    the timestamp; failures leave the row untouched so the next run retries.
    """
    from time import sleep

    from engine.handlers import email_sender
    from engine.handlers.security import (
        CryptoUnavailable,
        decrypt_email,
    )

    digest = generate_digest(
        vertical_name, week_offset=week_offset, limit=limit, now=now
    )
    if not digest["articles"]:
        logger.info(
            "[%s] no stories for %s — skipping send",
            vertical_name,
            digest["week_key"],
        )
        return {"considered": 0, "sent": 0, "skipped_no_articles": 1, "failed": 0}

    SessionLocal = get_sessionmaker()
    counts = {"considered": 0, "sent": 0, "already": 0, "failed": 0}

    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            logger.warning("vertical %s not found — abort", vertical_name)
            return {"considered": 0, "sent": 0, "already": 0, "failed": 0}

        rows = session.execute(
            select(Subscriber).where(
                Subscriber.vertical_id == v.id,
                Subscriber.confirmed.is_(True),
                Subscriber.unsubscribed_at.is_(None),
            )
        ).scalars().all()

        for sub in rows:
            counts["considered"] += 1
            last_sent = sub.last_digest_sent_at
            # SQLite drops the tzinfo on read; normalize before comparing
            # against ``digest["start"]`` which is always UTC-aware.
            if last_sent is not None and last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if last_sent is not None and last_sent >= digest["start"]:
                counts["already"] += 1
                continue
            try:
                addr = decrypt_email(sub.email_encrypted)
            except CryptoUnavailable:
                logger.error(
                    "fernet key missing — abort %s digest blast", vertical_name
                )
                counts["failed"] += len(rows) - counts["sent"] - counts["already"]
                break
            except Exception as exc:
                logger.warning(
                    "decrypt failed for sub %d: %s", sub.id, exc
                )
                counts["failed"] += 1
                continue

            personal_html = digest["html"].replace(
                "__UNSUB_TOKEN__", sub.unsubscribe_token
            )
            personal_text = digest["text"].replace(
                "__UNSUB_TOKEN__", sub.unsubscribe_token
            )
            ok = email_sender.send(
                to=addr,
                subject=digest["subject"],
                text_body=personal_text,
                html_body=personal_html,
                stream="broadcast",
            )
            if ok:
                sub.last_digest_sent_at = datetime.now(timezone.utc)
                session.commit()
                counts["sent"] += 1
            else:
                counts["failed"] += 1
            if sleep_between:
                sleep(sleep_between)

    logger.info(
        "[%s] digest blast %s: %s",
        vertical_name,
        digest["week_key"],
        counts,
    )
    return counts


def _parse_week_key(week_key: str) -> datetime | None:
    """Parse ``YYYY-Www`` into the Monday 00:00 UTC of that ISO week."""
    try:
        year_str, w_str = week_key.split("-W")
        return datetime.fromisocalendar(int(year_str), int(w_str), 1).replace(
            tzinfo=timezone.utc
        )
    except (ValueError, IndexError):
        return None


def render_digest_index(vertical_name: str) -> Path:
    """Build /digest/index.html listing every archived week, newest first.

    Reads the on-disk archive directories under
    ``data/output/<vertical>/digest/`` so the index is a true reflection of
    what is actually published — no stale DB rows.
    """
    out_dir = _output_dir(vertical_name) / "digest"
    out_dir.mkdir(parents=True, exist_ok=True)

    weeks: list[dict[str, Any]] = []
    for entry in sorted(out_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        idx = entry / "index.html"
        if not idx.exists():
            continue
        start = _parse_week_key(entry.name)
        if start is None:
            continue
        end = start + timedelta(days=7)
        # Story count: count <li> in .digest-stories — cheap and avoids a
        # second pass through the DB just for the index.
        body = idx.read_text(encoding="utf-8", errors="ignore")
        n_stories = body.count("<li>")
        weeks.append(
            {
                "week_key": entry.name,
                "label_start": start.strftime("%b %d, %Y"),
                "label_end": end.strftime("%b %d, %Y"),
                "n_stories": n_stories,
                "path": f"/digest/{entry.name}/",
            }
        )

    vertical = _vertical_meta(vertical_name)
    env = _env()
    html = env.get_template("digest_index.html").render(
        vertical=vertical,
        weeks=weeks,
        title=f"{vertical['display_name']} digest archive",
        description=(
            f"Weekly {vertical['display_name']} digests — every issue we've "
            f"published, archived for reference."
        ),
        canonical_url="/digest/",
    )
    idx_path = out_dir / "index.html"
    idx_path.write_text(html, encoding="utf-8")
    logger.info(
        "rendered digest index -> %s (%d weeks)", idx_path, len(weeks)
    )
    return idx_path


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.newsletter_generator modelwatch [--print html]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate the weekly digest")
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch)")
    parser.add_argument(
        "--week-offset",
        type=int,
        default=0,
        help="0 = current ISO week, -1 = previous full ISO week",
    )
    parser.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    parser.add_argument(
        "--render-archive",
        action="store_true",
        help="Write the archive page to data/output/<vertical>/digest/<key>/",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Email the digest to confirmed subscribers (idempotent per ISO week)",
    )
    parser.add_argument(
        "--print",
        choices=["html", "text", "subject", "summary"],
        default="summary",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    digest = generate_digest(
        args.vertical, week_offset=args.week_offset, limit=args.limit
    )
    if args.render_archive:
        render_archive(
            args.vertical, week_offset=args.week_offset, limit=args.limit
        )
        # Always refresh the index when an archive is rebuilt — cheap and
        # keeps /digest/ in sync.
        render_digest_index(args.vertical)
    if args.send:
        send_pending_digests(
            args.vertical, week_offset=args.week_offset, limit=args.limit
        )

    if args.print == "html":
        print(digest["html"])
    elif args.print == "text":
        print(digest["text"])
    elif args.print == "subject":
        print(digest["subject"])
    else:
        print(f"week:    {digest['week_key']}")
        print(f"window:  {digest['start']:%Y-%m-%d} -> {digest['end']:%Y-%m-%d}")
        print(f"subject: {digest['subject']}")
        print(f"stories: {len(digest['articles'])}")
        for a in digest["articles"]:
            print(f"  - {a['title'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
