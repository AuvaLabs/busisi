"""Per-vertical HTML renderer.

Reads articles from Postgres and emits the front-page HTML to
``/srv/grimoire/data/output/<vertical>/index.html``. Caddy serves that
directory as a static site root.

Phase 3 minimum-viable output: front page only. Phase 4+ adds story pages,
glossary, learn, tools, /today, RSS, Atom, sitemap, llms.txt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from engine.core.config import DATA_DIR, GRIMOIRE_ROOT
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


_TEMPLATES_DIR = GRIMOIRE_ROOT / "engine" / "shared" / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _human_age(dt: datetime | None) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    if dt > now:
        return ""
    secs = (now - dt).total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _short_source(source_url: str) -> str:
    host = urlparse(source_url).netloc
    return host.removeprefix("www.")


def _output_dir(vertical_name: str) -> Path:
    return DATA_DIR / "output" / vertical_name


def render_index(vertical_name: str, *, limit: int = 50) -> Path:
    """Render the front-page index.html for a vertical. Returns the output path."""
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")

        rows = (
            session.execute(
                select(Article)
                .where(Article.vertical_id == v.id, Article.deleted_at.is_(None))
                .order_by(Article.fetched_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

        articles_ctx: list[dict[str, Any]] = [
            {
                "title": a.title,
                "link": a.link,
                "source_short": _short_source(a.source),
                "feed_region": a.feed_region,
                "published_human": _human_age(a.published_at),
                "labels": a.labels or [],
            }
            for a in rows
        ]

        ctx = {
            "vertical": {
                "name": v.name,
                "display_name": v.display_name,
                "accent_light": v.accent_light,
                "accent_dark": v.accent_dark,
            },
            "title": "Front",
            "description": f"{v.display_name} — front page",
            "theme": "light",
            "articles": articles_ctx,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    html = _env().get_template("index.html").render(**ctx)

    out_dir = _output_dir(vertical_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("rendered %s (%d articles) -> %s", vertical_name, len(rows), out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.output_renderer modelwatch``"""
    import argparse

    parser = argparse.ArgumentParser(description="Render a grimoire vertical front page")
    parser.add_argument("vertical")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(message)s")
    out = render_index(args.vertical, limit=args.limit)
    print(f"rendered -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
