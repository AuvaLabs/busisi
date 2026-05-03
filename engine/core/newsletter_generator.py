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
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from engine.core.config import DATA_DIR, GRIMOIRE_ROOT
from engine.core.db import Article, Vertical, get_sessionmaker

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


def _top_articles(
    vertical_name: str,
    *,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[Article]:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return []
        rows = session.execute(
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
            .limit(limit)
        ).scalars().all()
        return list(rows)


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


def _article_ctx(a: Article, vertical_name: str) -> dict[str, Any]:
    return {
        "title": a.title,
        "slug": a.slug,
        "summary": a.summary,
        "why_this_matters": a.why_this_matters,
        "source": a.source,
        "feed_region": a.feed_region,
        "published_at": a.published_at,
        "story_path": f"/story/{a.slug}/",
        "vertical": vertical_name,
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
    articles = _top_articles(
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
        "articles": [_article_ctx(a, vertical_name) for a in articles],
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
