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

from sqlalchemy import func

from engine.core.config import DATA_DIR, GRIMOIRE_ROOT
from engine.core.db import (
    Article,
    ArticleEntity,
    Entity,
    Story,
    StoryArticle,
    Vertical,
    get_sessionmaker,
)

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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
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


def _load_story_cards(session, vertical_id: int, limit: int) -> list[dict[str, Any]]:
    """Pull recent Stories with their primary Article + n_sources count.

    Sort key is MAX(member.published_at) per story so a cluster with a
    fresh follow-up still surfaces — using primary_published_at would
    pin the story to the *oldest* member's date and hide multi-source
    coverage that picks up late.
    """
    fresh_subq = (
        select(
            StoryArticle.story_id.label("story_id"),
            func.count().label("n"),
            func.max(Article.published_at).label("latest_at"),
        )
        .join(Article, Article.id == StoryArticle.article_id)
        .group_by(StoryArticle.story_id)
        .subquery()
    )
    rows = session.execute(
        select(Story, Article, fresh_subq.c.n, fresh_subq.c.latest_at)
        .join(StoryArticle, StoryArticle.story_id == Story.id)
        .join(Article, Article.id == StoryArticle.article_id)
        .join(fresh_subq, fresh_subq.c.story_id == Story.id)
        .where(
            Story.vertical_id == vertical_id,
            StoryArticle.is_primary.is_(True),
            Article.deleted_at.is_(None),
        )
        .order_by(fresh_subq.c.latest_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "kind": "story",
            "slug": a.slug,
            "title": s.canonical_headline,
            "link": a.link,
            "source_short": _short_source(a.source),
            "feed_region": a.feed_region,
            "published_human": _human_age(latest_at or s.primary_published_at),
            "labels": a.labels or [],
            "n_sources": int(n),
            "sort_at": latest_at or s.primary_published_at or a.fetched_at,
        }
        for s, a, n, latest_at in rows
    ]


def _load_orphan_articles(
    session, vertical_id: int, limit: int
) -> list[dict[str, Any]]:
    """Pull recent Articles NOT linked to any Story."""
    clustered = select(StoryArticle.article_id)
    rows = (
        session.execute(
            select(Article)
            .where(
                Article.vertical_id == vertical_id,
                Article.deleted_at.is_(None),
                ~Article.id.in_(clustered),
            )
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": "article",
            "slug": a.slug,
            "title": a.title,
            "link": a.link,
            "source_short": _short_source(a.source),
            "feed_region": a.feed_region,
            "published_human": _human_age(a.published_at),
            "labels": a.labels or [],
            "n_sources": 1,
            "sort_at": a.published_at or a.fetched_at,
        }
        for a in rows
    ]


def _merge_cards(
    stories: list[dict[str, Any]],
    orphans: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Merge by sort_at desc; tz-naive datetimes are coerced to UTC."""
    def _key(card: dict[str, Any]) -> datetime:
        dt = card["sort_at"]
        if dt is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    merged = sorted(stories + orphans, key=_key, reverse=True)
    return merged[:limit]


def render_index(vertical_name: str, *, limit: int = 50) -> Path:
    """Render the front-page index.html for a vertical. Returns the output path.

    Cards on the front page come from two sources:
      * Stories — multi-source clusters, render once with an "N sources" badge.
      * Orphan Articles — single-source items not in any cluster.
    Both shapes share the same template fields; ``kind`` distinguishes them.
    """
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")

        # Pull more than ``limit`` from each side so the merge can rebalance
        # if either side is heavily skewed by recency.
        stories = _load_story_cards(session, v.id, limit)
        orphans = _load_orphan_articles(session, v.id, limit)
        cards = _merge_cards(stories, orphans, limit)

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
            "articles": cards,
            "canonical_url": _canonical_url(vertical_name, "/"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    html = _env().get_template("index.html").render(**ctx)

    out_dir = _output_dir(vertical_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(
        "rendered %s (%d cards: %d stories + %d orphans) -> %s",
        vertical_name,
        len(cards),
        sum(1 for c in cards if c["kind"] == "story"),
        sum(1 for c in cards if c["kind"] == "article"),
        out_path,
    )
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


def _canonical_url(vertical_name: str, path: str) -> str:
    """Return the canonical URL for a page within a vertical.

    Uses the placeholder ``<vertical>.local`` host until the real domain
    is committed; rendering doesn't depend on TLS so http:// is fine here.
    """
    return f"http://{vertical_name}.local{path}"


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
            "canonical_url": _canonical_url(vertical_name, f"/{slug}"),
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
        "canonical_url": _canonical_url(vertical_name, "/sources"),
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


def _siblings_map(
    session, article_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Return ``{article_id: [sibling_ctx, ...]}`` for any articles that
    belong to a multi-source Story. Single-key articles map to an empty
    list. One round-trip per call regardless of input size."""
    if not article_ids:
        return {}
    # article → story_id
    story_id_rows = session.execute(
        select(StoryArticle.article_id, StoryArticle.story_id).where(
            StoryArticle.article_id.in_(article_ids)
        )
    ).all()
    if not story_id_rows:
        return {}
    article_to_story: dict[int, int] = {aid: sid for aid, sid in story_id_rows}
    story_ids = list({sid for _, sid in story_id_rows})
    # All members of those stories (including the seed articles).
    members = session.execute(
        select(StoryArticle.story_id, Article)
        .join(Article, Article.id == StoryArticle.article_id)
        .where(StoryArticle.story_id.in_(story_ids))
    ).all()
    by_story: dict[int, list[Article]] = {}
    for sid, art in members:
        by_story.setdefault(sid, []).append(art)
    out: dict[int, list[dict[str, Any]]] = {}
    for aid, sid in article_to_story.items():
        siblings = [
            {
                "slug": m.slug,
                "title": m.title,
                "link": m.link,
                "source_short": _short_source(m.source),
                "feed_region": m.feed_region,
            }
            for m in by_story.get(sid, [])
            if m.id != aid
        ]
        out[aid] = siblings
    return out


def render_stories(vertical_name: str, *, limit: int = 2000) -> dict[str, Path]:
    """Render one canonical /story/<slug>/ page per persisted article.

    The story page is OUR canonical surface — the front-page card links to
    it. Until LLM enrichment runs, the body is the feed-provided summary
    with a disclosure banner (`summary_source = "feed"`).

    When the article belongs to a multi-source Story (Phase 11 clusterer),
    sibling member articles are passed as ``article.siblings`` so the
    template can render a "more sources" panel.
    """
    Session = get_sessionmaker()
    out: dict[str, Path] = {}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

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
        siblings_by_id = _siblings_map(session, [a.id for a in rows])

    env = _env()
    base_dir = _output_dir(vertical_name) / "story"
    base_dir.mkdir(parents=True, exist_ok=True)

    for a in rows:
        article_ctx = {
            "slug": a.slug,
            "title": a.title,
            "summary": a.summary or "",
            "summary_source": a.summary_source,
            "why_this_matters": a.why_this_matters,
            "link": a.link,
            "source_short": _short_source(a.source),
            "feed_region": a.feed_region,
            "published_human": _human_age(a.published_at),
            "labels": a.labels or [],
            "siblings": siblings_by_id.get(a.id, []),
        }
        ctx = {
            "vertical": vertical_ctx,
            "title": a.title,
            "description": (a.summary or a.title)[:160],
            "theme": "light",
            "article": article_ctx,
            "canonical_url": _canonical_url(vertical_name, f"/story/{a.slug}/"),
        }
        html = env.get_template("story.html").render(**ctx)
        story_dir = base_dir / a.slug
        story_dir.mkdir(parents=True, exist_ok=True)
        story_path = story_dir / "index.html"
        story_path.write_text(html, encoding="utf-8")
        out[a.slug] = story_path

    logger.info("rendered %s stories (%d pages)", vertical_name, len(rows))
    return out


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
        canonical_url=_canonical_url(vertical_name, "/tools/"),
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
            canonical_url=_canonical_url(vertical_name, f"/tools/{meta['slug']}/"),
        )
        page_dir = idx_dir / meta["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        page_path = page_dir / "index.html"
        page_path.write_text(page_html, encoding="utf-8")
        out[meta["slug"]] = page_path

    logger.info("rendered %s tools (%d tool pages)", vertical_name, len(tools))
    return out


_ENTITY_TYPE_LABELS: dict[str, str] = {
    "lab": "Labs",
    "model": "Models",
    "person": "People",
    "company": "Companies",
    "product": "Products",
    "location": "Locations",
}


def render_entity_index(vertical_name: str) -> Path:
    """Render /entity/index.html — all entities, grouped by type, A→Z."""
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        # Per-entity article count, joined to ArticleEntity.
        rows = session.execute(
            select(Entity, func.count(ArticleEntity.article_id).label("n"))
            .outerjoin(ArticleEntity, ArticleEntity.entity_id == Entity.id)
            .where(Entity.vertical_id == v.id)
            .group_by(Entity.id)
            .order_by(Entity.type.asc(), Entity.name.asc())
        ).all()
        groups: dict[str, list[dict[str, Any]]] = {}
        for ent, n in rows:
            if int(n) == 0:
                continue
            groups.setdefault(ent.type, []).append(
                {
                    "name": ent.name,
                    "slug": ent.slug,
                    "type": ent.type,
                    "n": int(n),
                    "path": f"/entity/{ent.type}/{ent.slug}/",
                }
            )
        ordered_groups = [
            {
                "type": etype,
                "label": _ENTITY_TYPE_LABELS.get(etype, etype.title()),
                "entities": sorted(items, key=lambda e: (-e["n"], e["name"].lower())),
            }
            for etype, items in groups.items()
            if items
        ]
        ordered_groups.sort(key=lambda g: g["label"])

        ctx = {
            "vertical": _vertical_ctx(v),
            "title": "Entities",
            "description": f"{v.display_name} — every named entity we've tagged.",
            "theme": "light",
            "groups": ordered_groups,
            "total": sum(len(g["entities"]) for g in ordered_groups),
            "canonical_url": _canonical_url(vertical_name, "/entity/"),
        }

    html = _env().get_template("entity_index.html").render(**ctx)
    out_dir = _output_dir(vertical_name) / "entity"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(
        "rendered entity index %s -> %s (%d entities)",
        vertical_name,
        out_path,
        ctx["total"],
    )
    return out_path


def render_entities(vertical_name: str) -> dict[str, Path]:
    """Render /entity/<type>/<slug>/index.html for every entity with ≥1 link."""
    Session = get_sessionmaker()
    out: dict[str, Path] = {}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        vertical_ctx = _vertical_ctx(v)

        entity_rows = (
            session.execute(
                select(Entity).where(Entity.vertical_id == v.id)
            )
            .scalars()
            .all()
        )
        # Per-entity article fetch in one round-trip.
        link_rows = session.execute(
            select(ArticleEntity.entity_id, Article)
            .join(Article, Article.id == ArticleEntity.article_id)
            .where(Article.vertical_id == v.id, Article.deleted_at.is_(None))
            .order_by(Article.published_at.desc())
        ).all()
        articles_by_entity: dict[int, list[Article]] = {}
        for eid, a in link_rows:
            articles_by_entity.setdefault(eid, []).append(a)

    env = _env()
    base_dir = _output_dir(vertical_name) / "entity"
    for ent in entity_rows:
        articles = articles_by_entity.get(ent.id, [])
        if not articles:
            continue
        article_ctxs = [
            {
                "slug": a.slug,
                "title": a.title,
                "source_short": _short_source(a.source),
                "feed_region": a.feed_region,
                "published_human": _human_age(a.published_at),
            }
            for a in articles
        ]
        ctx = {
            "vertical": vertical_ctx,
            "title": ent.name,
            "description": (
                f"Articles tagged with {ent.name} on {vertical_ctx['display_name']}."
            ),
            "theme": "light",
            "entity": {
                "name": ent.name,
                "slug": ent.slug,
                "type": ent.type,
                "type_label": _ENTITY_TYPE_LABELS.get(ent.type, ent.type.title()),
                "n": len(article_ctxs),
            },
            "articles": article_ctxs,
            "canonical_url": _canonical_url(
                vertical_name, f"/entity/{ent.type}/{ent.slug}/"
            ),
        }
        html = env.get_template("entity_page.html").render(**ctx)
        ent_dir = base_dir / ent.type / ent.slug
        ent_dir.mkdir(parents=True, exist_ok=True)
        path = ent_dir / "index.html"
        path.write_text(html, encoding="utf-8")
        out[f"{ent.type}/{ent.slug}"] = path

    logger.info("rendered %s entities (%d pages)", vertical_name, len(out))
    return out


def render_all(vertical_name: str, *, index_limit: int = 50) -> dict[str, Any]:
    """Render index + stories + static pages + sources + tools + meta files."""
    return {
        "index": render_index(vertical_name, limit=index_limit),
        "stories": render_stories(vertical_name),
        "static_pages": render_static_pages(vertical_name),
        "sources": render_sources(vertical_name),
        "tools": render_tools(vertical_name),
        "entity_index": render_entity_index(vertical_name),
        "entities": render_entities(vertical_name),
        "meta": render_meta_files(vertical_name),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.output_renderer modelwatch``"""
    import argparse

    parser = argparse.ArgumentParser(description="Render a grimoire vertical")
    parser.add_argument("vertical")
    parser.add_argument(
        "--target",
        choices=(
            "all",
            "index",
            "stories",
            "static",
            "sources",
            "tools",
            "meta",
            "entities",
        ),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(message)s")

    if args.target == "all":
        out = render_all(args.vertical, index_limit=args.limit)
        print(f"rendered index   -> {out['index']}")
        print(f"rendered stories -> {len(out['stories'])} pages")
        print(f"rendered static  -> {len(out['static_pages'])} pages")
        print(f"rendered sources -> {out['sources']}")
        print(f"rendered tools   -> {len(out['tools'])} pages")
        print(f"rendered entities-> {len(out['entities'])} pages (+ index)")
        print(f"rendered meta    -> {len(out['meta'])} files")
    elif args.target == "entities":
        idx = render_entity_index(args.vertical)
        pages = render_entities(args.vertical)
        print(f"rendered entity index -> {idx}")
        print(f"rendered entities    -> {len(pages)} pages")
    elif args.target == "stories":
        for slug, p in render_stories(args.vertical).items():
            print(f"rendered story/{slug} -> {p}")
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
