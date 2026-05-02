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


_STATIC_PAGES = (
    ("about", "About", "What this is and who runs it."),
    ("methodology", "Methodology", "How sources, AI usage, and editorial rules work."),
    ("privacy", "Privacy", "Data we collect, what we don't, and your rights."),
    ("terms", "Terms", "Usage terms and operating-entity disclosure."),
)


def _vertical_ctx(v: Any) -> dict[str, Any]:
    return {
        "name": v.name,
        "display_name": v.display_name,
        "accent_light": v.accent_light,
        "accent_dark": v.accent_dark,
    }


def render_static_pages(vertical_name: str) -> list[Path]:
    """Render about/methodology/privacy/terms for a vertical. Returns paths."""
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

    env = _env()
    paths: list[Path] = []
    for slug, title, description in _STATIC_PAGES:
        ctx = {
            "vertical": vertical_ctx,
            "title": title,
            "description": description,
            "theme": "light",
        }
        html = env.get_template(f"{slug}.html").render(**ctx)
        out_dir = _output_dir(vertical_name) / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "index.html"
        out_path.write_text(html, encoding="utf-8")
        paths.append(out_path)
        logger.info("rendered %s/%s", vertical_name, slug)
    return paths


def render_sources(vertical_name: str) -> Path:
    """Render the public /sources page from feed_loader + Redis health data."""
    from engine.core import feed_loader
    from engine.core.source_health import get_status

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

    feeds = feed_loader.load_feeds(vertical_name)
    sources_ctx: list[dict[str, Any]] = []
    for f in feeds:
        url = f["url"]
        sources_ctx.append({
            "url": url,
            "host_short": _short_source(url),
            "priority_weight": f.get("priority_weight", 0.7),
            "region": f.get("region", "Global"),
            "category_hints": f.get("category_hints", []),
            "health": get_status(url),
        })
    sources_ctx.sort(key=lambda s: (-s["priority_weight"], s["host_short"]))

    ctx = {
        "vertical": vertical_ctx,
        "title": "Sources",
        "description": f"All sources {vertical_ctx['display_name']} ingests.",
        "theme": "light",
        "sources": sources_ctx,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    html = _env().get_template("sources.html").render(**ctx)
    out_dir = _output_dir(vertical_name) / "sources"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("rendered %s/sources (%d sources)", vertical_name, len(sources_ctx))
    return out_path


def render_meta_files(
    vertical_name: str, *, canonical_url: str | None = None
) -> dict[str, Path]:
    """Render llms.txt, robots.txt, sitemap.xml for the vertical."""
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

        # Collect URLs for sitemap: index + static pages + sources + each article
        articles = (
            session.execute(
                select(Article)
                .where(Article.vertical_id == v.id, Article.deleted_at.is_(None))
                .order_by(Article.fetched_at.desc())
                .limit(500)
            )
            .scalars()
            .all()
        )

    base = canonical_url or f"http://{vertical_name}.local"
    base = base.rstrip("/")
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls: list[dict[str, Any]] = [
        {"loc": f"{base}/", "lastmod": now_date, "changefreq": "hourly", "priority": 1.0},
        {"loc": f"{base}/about", "lastmod": now_date, "changefreq": "monthly", "priority": 0.5},
        {"loc": f"{base}/methodology", "lastmod": now_date, "changefreq": "monthly", "priority": 0.5},
        {"loc": f"{base}/privacy", "lastmod": now_date, "changefreq": "yearly", "priority": 0.3},
        {"loc": f"{base}/terms", "lastmod": now_date, "changefreq": "yearly", "priority": 0.3},
        {"loc": f"{base}/sources", "lastmod": now_date, "changefreq": "daily", "priority": 0.6},
    ]
    for a in articles:
        loc = a.link  # external links — we sitemap our own canonical pages once they exist
        if loc.startswith(base):
            urls.append({
                "loc": loc,
                "lastmod": (a.fetched_at or a.published_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                "changefreq": "weekly",
                "priority": 0.7,
            })

    env = _env()
    out_dir = _output_dir(vertical_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    paths: dict[str, Path] = {}

    llms = env.get_template("llms.txt").render(
        vertical=vertical_ctx, generated_at=generated_at
    )
    p = out_dir / "llms.txt"
    p.write_text(llms, encoding="utf-8")
    paths["llms"] = p

    robots = env.get_template("robots.txt").render(
        vertical=vertical_ctx, canonical_url=base
    )
    p = out_dir / "robots.txt"
    p.write_text(robots, encoding="utf-8")
    paths["robots"] = p

    sitemap = env.get_template("sitemap.xml").render(urls=urls)
    p = out_dir / "sitemap.xml"
    p.write_text(sitemap, encoding="utf-8")
    paths["sitemap"] = p

    logger.info("rendered %s meta-files (llms.txt, robots.txt, sitemap.xml)", vertical_name)
    return paths


def render_tools(vertical_name: str) -> dict[str, Path]:
    """Render /tools/ index + per-tool pages for a vertical."""
    from engine.core import tools_engine

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

    tools = tools_engine.list_tools(vertical_name)
    env = _env()
    out: dict[str, Path] = {}

    # Index
    idx_html = env.get_template("tools_index.html").render(
        vertical=vertical_ctx,
        title="Tools",
        description=f"{vertical_ctx['display_name']} tools — calculators and decision aids.",
        theme="light",
        tools=tools,
    )
    idx_dir = _output_dir(vertical_name) / "tools"
    idx_dir.mkdir(parents=True, exist_ok=True)
    idx_path = idx_dir / "index.html"
    idx_path.write_text(idx_html, encoding="utf-8")
    out["index"] = idx_path

    # Per-tool pages
    for meta in tools:
        tool = tools_engine.get_tool(vertical_name, meta["slug"])
        if tool is None or tool["calculate"] is None:
            continue
        try:
            default_result = tool["calculate"](dict(tool["defaults"]))
        except Exception as exc:
            logger.warning("tool %s default-run failed: %s", meta["slug"], exc)
            default_result = {"headline": "—", "breakdown": []}
        page_html = env.get_template("tool_page.html").render(
            vertical=vertical_ctx,
            title=meta["title"],
            description=meta.get("description", ""),
            theme="light",
            tool=meta,
            default_result=default_result,
        )
        page_dir = idx_dir / meta["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / "index.html"
        page_path.write_text(page_html, encoding="utf-8")
        out[meta["slug"]] = page_path

    logger.info("rendered %s tools (%d tool pages)", vertical_name, len(tools))
    return out


def render_all(vertical_name: str, *, index_limit: int = 50) -> dict[str, Any]:
    """Render index + static pages + sources page + tools + meta files."""
    return {
        "index": render_index(vertical_name, limit=index_limit),
        "static_pages": render_static_pages(vertical_name),
        "sources": render_sources(vertical_name),
        "tools": render_tools(vertical_name),
        "meta": render_meta_files(vertical_name),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.output_renderer modelwatch``"""
    import argparse

    parser = argparse.ArgumentParser(description="Render a grimoire vertical")
    parser.add_argument("vertical")
    parser.add_argument(
        "--target",
        choices=("all", "index", "static", "sources", "tools", "meta"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(message)s")

    if args.target == "all":
        out = render_all(args.vertical, index_limit=args.limit)
        print(f"rendered index   -> {out['index']}")
        print(f"rendered static  -> {len(out['static_pages'])} pages")
        print(f"rendered sources -> {out['sources']}")
        print(f"rendered meta    -> {len(out['meta'])} files")
    elif args.target == "index":
        print(f"rendered -> {render_index(args.vertical, limit=args.limit)}")
    elif args.target == "static":
        for p in render_static_pages(args.vertical):
            print(f"rendered -> {p}")
    elif args.target == "sources":
        print(f"rendered -> {render_sources(args.vertical)}")
    elif args.target == "meta":
        for name, p in render_meta_files(args.vertical).items():
            print(f"rendered {name:8s} -> {p}")
    elif args.target == "tools":
        for name, p in render_tools(args.vertical).items():
            print(f"rendered tools/{name} -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
