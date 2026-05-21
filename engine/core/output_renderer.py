"""Per-vertical HTML renderer.

Reads articles from Postgres and emits the front-page HTML to
``/srv/grimoire/data/output/<vertical>/index.html``. Caddy serves that
directory as a static site root.

Phase 3 minimum-viable output: front page only. Phase 4+ adds story pages,
glossary, learn, tools, /today, RSS, Atom, sitemap, llms.txt.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from sqlalchemy import func

from engine.core.config import DATA_DIR, GRIMOIRE_ROOT, canonical_base_for
from engine.core.db import (
    Article,
    ArticleEntity,
    Entity,
    ResearchBundle,
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


def _renderable_article_clause():
    """SQLAlchemy clause: True iff the Article should appear on the public site.

    Path A (2026-05-21) — only render articles whose body is a quality rewrite:
      * ``summary_source = 'rewrite_single'`` (F2 orphan rewriter output), OR
      * the article belongs to a cluster whose Story.narrative is set
        (F1 multi-source cluster rewriter output).

    Articles that only have a feed-supplied summary are hidden from the index,
    /story pages, sitemap, and llms-full.txt. They stay in the database so the
    rewriter can pick them up once they're researched + extracted.
    """
    cluster_member_with_narrative = (
        select(StoryArticle.article_id)
        .join(Story, Story.id == StoryArticle.story_id)
        .where(Story.narrative.is_not(None))
    )
    return (
        (Article.summary_source == "rewrite_single")
        | Article.id.in_(cluster_member_with_narrative)
    )


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
            (Article.curator_tier != "skip") | Article.curator_tier.is_(None),
            # Path A — only surface clusters whose multi-source narrative
            # has been composed by the F1 rewriter. Draft/ready clusters
            # without a narrative would render an empty body otherwise.
            Story.narrative.is_not(None),
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
    """Pull recent Articles NOT linked to any Story.

    Excludes ``curator_tier='skip'`` articles (Phase 22c). NULL tier passes
    through — pre-curator-backfill rows stay visible until scored.
    """
    clustered = select(StoryArticle.article_id)
    rows = (
        session.execute(
            select(Article)
            .where(
                Article.vertical_id == vertical_id,
                Article.deleted_at.is_(None),
                ~Article.id.in_(clustered),
                (Article.curator_tier != "skip") | Article.curator_tier.is_(None),
                # Path A — only orphans with an F2 rewrite are quality
                # enough to appear on the index. Feed-only summaries are
                # hidden until the rewriter catches up.
                Article.summary_source == "rewrite_single",
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
    ("licensing", "Licensing", "Quotation, AI inference, and reuse terms."),
    ("advertise", "Advertise", "Sponsorship, ads, and affiliate partnerships."),
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

    Base resolves via ``engine.core.config.canonical_base_for`` —
    env-overridable per vertical (``<VERTICAL>_CANONICAL_BASE``) so the
    domain commit is a one-line ``.env`` change. Falls back to
    ``http://<vertical>.local`` when no env override is set (local dev /
    pre-domain).
    """
    return f"{canonical_base_for(vertical_name)}{path}"


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

        # Collect URLs for sitemap + RSS — skip-tier articles are excluded
        # from public discovery surfaces (Phase 22c). Their /story/<slug>/
        # pages are still rendered (with noindex meta) so existing inbound
        # links don't 404.
        articles = (
            session.execute(
                select(Article)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    (Article.curator_tier != "skip")
                    | Article.curator_tier.is_(None),
                    # Path A — llms-full.txt and sitemap entries below should
                    # match what we actually render. Feed-only articles are
                    # not on the public site, so they don't belong in either.
                    _renderable_article_clause(),
                )
                .order_by(Article.fetched_at.desc())
                .limit(500)
            )
            .scalars()
            .all()
        )

    base = canonical_url or canonical_base_for(vertical_name)
    base = base.rstrip("/")
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls: list[dict[str, Any]] = [
        {"loc": f"{base}/", "lastmod": now_date, "changefreq": "hourly", "priority": 1.0},
        {"loc": f"{base}/about", "lastmod": now_date, "changefreq": "monthly", "priority": 0.5},
        {"loc": f"{base}/methodology", "lastmod": now_date, "changefreq": "monthly", "priority": 0.5},
        {"loc": f"{base}/privacy", "lastmod": now_date, "changefreq": "yearly", "priority": 0.3},
        {"loc": f"{base}/terms", "lastmod": now_date, "changefreq": "yearly", "priority": 0.3},
        {"loc": f"{base}/licensing", "lastmod": now_date, "changefreq": "yearly", "priority": 0.3},
        {"loc": f"{base}/advertise", "lastmod": now_date, "changefreq": "monthly", "priority": 0.4},
        {"loc": f"{base}/sources", "lastmod": now_date, "changefreq": "daily", "priority": 0.6},
        {"loc": f"{base}/entity/", "lastmod": now_date, "changefreq": "daily", "priority": 0.6},
        {"loc": f"{base}/tools/", "lastmod": now_date, "changefreq": "weekly", "priority": 0.5},
        {"loc": f"{base}/digest/", "lastmod": now_date, "changefreq": "weekly", "priority": 0.5},
        {"loc": f"{base}/search/", "lastmod": now_date, "changefreq": "weekly", "priority": 0.5},
    ]

    # Stories: separate query (no 500-row cap, all live non-skip
    # articles with a slug). Sitemap.xml supports up to 50K URLs per
    # file — embedding ~3K + vested ~2K stays well under.
    Session = get_sessionmaker()
    with Session() as session:
        story_rows = session.execute(
            select(Article.slug, Article.fetched_at, Article.published_at)
            .where(
                Article.vertical_id == v.id,
                Article.deleted_at.is_(None),
                (Article.curator_tier != "skip") | Article.curator_tier.is_(None),
                Article.slug.is_not(None),
                # Path A — only emit sitemap entries for URLs we render.
                _renderable_article_clause(),
            )
            .order_by(Article.published_at.desc())
        ).all()
        for slug, fetched_at, published_at in story_rows:
            mod = published_at or fetched_at or datetime.now(timezone.utc)
            urls.append({
                "loc": f"{base}/story/{slug}/",
                "lastmod": mod.strftime("%Y-%m-%d"),
                "changefreq": "weekly",
                "priority": 0.7,
            })

        # Per-entity pages: only those with ≥1 linked article — same
        # gate render_entities() applies, so every URL we emit is a
        # rendered page on disk.
        entity_rows = session.execute(
            select(Entity.type, Entity.slug)
            .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
            .join(Article, Article.id == ArticleEntity.article_id)
            .where(
                Entity.vertical_id == v.id,
                Article.deleted_at.is_(None),
                (Article.curator_tier != "skip") | Article.curator_tier.is_(None),
            )
            .distinct()
        ).all()
        for ent_type, ent_slug in entity_rows:
            urls.append({
                "loc": f"{base}/entity/{ent_type}/{ent_slug}/",
                "lastmod": now_date,
                "changefreq": "weekly",
                "priority": 0.5,
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

    # llms-full.txt — plain-text content index for AI ingestion. Same
    # query as sitemap (skip-tier excluded), capped to the 500-row limit
    # already applied above.
    llms_full_articles: list[dict[str, Any]] = []
    for a in articles:
        pub_dt = a.published_at or a.fetched_at
        if pub_dt is not None and pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        llms_full_articles.append(
            {
                "title": a.title,
                "slug": a.slug,
                "summary": a.summary or "",
                "link": a.link,
                "source_short": _short_source(a.link),
                "feed_region": a.feed_region,
                "why_this_matters": a.why_this_matters or "",
                "published_iso": (
                    pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if pub_dt else ""
                ),
            }
        )
    llms_full = env.get_template("llms-full.txt").render(
        vertical=vertical_ctx,
        generated_at=generated_at,
        base_url=base,
        articles=llms_full_articles,
    )
    p = out_dir / "llms-full.txt"
    p.write_text(llms_full, encoding="utf-8")
    paths["llms_full"] = p

    robots = env.get_template("robots.txt").render(
        vertical=vertical_ctx, canonical_url=base
    )
    p = out_dir / "robots.txt"
    p.write_text(robots, encoding="utf-8")
    paths["robots"] = p

    # /.well-known/ assets — RSL inference licensing manifest +
    # RFC 9116 security.txt. Both are referenced from llms.txt,
    # robots.txt, terms.html, and licensing.html.
    well_known_dir = out_dir / ".well-known"
    well_known_dir.mkdir(parents=True, exist_ok=True)

    rsl = env.get_template(".well-known/rsl.json").render(
        vertical=vertical_ctx,
        base_url=base,
        generated_at=generated_at,
    )
    p = well_known_dir / "rsl.json"
    p.write_text(rsl, encoding="utf-8")
    paths["rsl"] = p

    # RSL 1.0 XML — industry-adopted standard (rslstandard.org); the JSON
    # variant above is a legacy placeholder retained during transition.
    rsl_xml = env.get_template(".well-known/rsl.xml").render(
        vertical=vertical_ctx,
        base_url=base,
        generated_at=generated_at,
    )
    p = well_known_dir / "rsl.xml"
    p.write_text(rsl_xml, encoding="utf-8")
    paths["rsl_xml"] = p

    expires = (
        datetime.now(timezone.utc) + timedelta(days=365)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    security = env.get_template(".well-known/security.txt").render(
        vertical=vertical_ctx,
        base_url=base,
        expires=expires,
    )
    p = well_known_dir / "security.txt"
    p.write_text(security, encoding="utf-8")
    paths["security"] = p

    sitemap = env.get_template("sitemap.xml").render(urls=urls)
    p = out_dir / "sitemap.xml"
    p.write_text(sitemap, encoding="utf-8")
    paths["sitemap"] = p

    def _aware(dt: datetime | None) -> datetime:
        if dt is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    feed_articles = sorted(
        articles,
        key=lambda a: _aware(a.published_at or a.fetched_at),
        reverse=True,
    )[:30]
    feed_items: list[dict[str, Any]] = []
    for a in feed_articles:
        pub_dt = a.published_at or a.fetched_at
        if pub_dt is not None and pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        feed_items.append(
            {
                "title": a.title,
                "link": f"{base}/story/{a.slug}/",
                "source_url": a.link,
                "pub_date": (
                    pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000") if pub_dt else ""
                ),
                "date_published": (pub_dt.isoformat() if pub_dt else ""),
                "summary": (a.summary or "")[:1200],
                "description": (a.summary or "")[:1200],
                "categories": [
                    label.get("label", "") if isinstance(label, dict) else str(label)
                    for label in (a.labels or [])
                    if label
                ],
            }
        )
    last_build_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    feed = env.get_template("feed.rss.xml").render(
        vertical=vertical_ctx,
        base_url=base,
        last_build_date=last_build_date,
        items=feed_items,
    )
    p = out_dir / "feed.rss"
    p.write_text(feed, encoding="utf-8")
    paths["feed"] = p

    feed_description = (
        f"{vertical_ctx['display_name']} — multi-source coverage with "
        "grounded summaries and source link-back."
    )
    feed_json = env.get_template("feed.json").render(
        vertical=vertical_ctx,
        base_url=base,
        feed_description=feed_description,
        items=feed_items,
    )
    p = out_dir / "feed.json"
    p.write_text(feed_json, encoding="utf-8")
    paths["feed_json"] = p

    # IndexNow key file — must be reachable at https://<vertical>/<KEY>.txt
    # for Bing/Yandex to verify push-mode index requests. Atelier-pattern.
    try:
        from engine.core import indexnow

        in_key = indexnow.get_or_create_key(vertical_name)
        in_key_path = out_dir / f"{in_key}.txt"
        in_key_path.write_text(in_key, encoding="utf-8")
        paths["indexnow_key"] = in_key_path
    except Exception as exc:  # noqa: BLE001 — never block render on IndexNow
        logger.warning("indexnow: key-file write failed: %s", exc)

    logger.info(
        "rendered %s meta-files (llms.txt, llms-full.txt, robots.txt, "
        "sitemap.xml, feed.rss, feed.json, indexnow key)",
        vertical_name,
    )
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


def _entities_map(
    session, article_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Return ``{article_id: [{type, slug, name, path}, ...]}`` in one query.

    Empty list for articles with no extracted entities."""
    if not article_ids:
        return {}
    rows = session.execute(
        select(ArticleEntity.article_id, Entity)
        .join(Entity, Entity.id == ArticleEntity.entity_id)
        .where(ArticleEntity.article_id.in_(article_ids))
        .order_by(Entity.type.asc(), Entity.name.asc())
    ).all()
    out: dict[int, list[dict[str, Any]]] = {}
    for aid, ent in rows:
        out.setdefault(aid, []).append(
            {
                "type": ent.type,
                "slug": ent.slug,
                "name": ent.name,
                "path": f"/entity/{ent.type}/{ent.slug}/",
            }
        )
    return out


def _research_bundles_map(
    session, article_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Return ``{article_id: [{url, host, excerpt, ord}, ...]}`` ordered by ord."""
    if not article_ids:
        return {}
    rows = session.execute(
        select(ResearchBundle)
        .where(ResearchBundle.article_id.in_(article_ids))
        .order_by(ResearchBundle.article_id, ResearchBundle.ord)
    ).scalars().all()
    out: dict[int, list[dict[str, Any]]] = {}
    for b in rows:
        out.setdefault(b.article_id, []).append(
            {
                "url": b.source_url,
                "host": b.host,
                "excerpt": (b.excerpt or "")[:280],
                "ord": b.ord,
            }
        )
    return out


def _non_primary_redirects(
    session, article_ids: list[int]
) -> dict[int, str]:
    """Return ``{non_primary_article_id: primary_slug}``.

    C2 — non-primary cluster members get a 0-byte redirect page pointing to
    the primary's /story/<slug>/ instead of a duplicate full render. Reduces
    near-duplicate-content SEO penalty and concentrates link equity.
    """
    if not article_ids:
        return {}
    link_rows = session.execute(
        select(StoryArticle.article_id, StoryArticle.story_id, StoryArticle.is_primary)
        .where(StoryArticle.article_id.in_(article_ids))
    ).all()
    if not link_rows:
        return {}
    story_ids = list({sid for _, sid, _ in link_rows})
    primaries = session.execute(
        select(StoryArticle.story_id, Article.slug)
        .join(Article, Article.id == StoryArticle.article_id)
        .where(
            StoryArticle.story_id.in_(story_ids),
            StoryArticle.is_primary.is_(True),
        )
    ).all()
    primary_slug_by_story: dict[int, str] = {sid: slug for sid, slug in primaries}
    out: dict[int, str] = {}
    for aid, sid, is_primary in link_rows:
        if is_primary:
            continue
        primary_slug = primary_slug_by_story.get(sid)
        if primary_slug:
            out[aid] = primary_slug
    return out


_AGENCY_CLASS_LABELS = {
    "A": "wire",
    "B": "newspaper",
    "C": "trade press",
    "D": "primary",
    "E": "research",
    "F": "commentary",
}

_CITATION_TOKEN_RE = re.compile(r"\[(\d+)\]")


def _linkify_citations(narrative: str) -> str:
    """Wrap inline ``[N]`` tokens with ``<sup><a href="#cite-N">[N]</a></sup>``.

    The escape is enough for plain news prose — narrative comes from our LLM
    pipeline and never carries hostile HTML. The renderer template also calls
    this through Jinja's ``| safe`` filter, so HTML entities in the narrative
    are preserved in the surrounding text but the citation wrapper itself is
    structurally HTML.
    """
    return _CITATION_TOKEN_RE.sub(
        lambda m: (
            f'<sup class="cite-ref">'
            f'<a href="#cite-{m.group(1)}">[{m.group(1)}]</a>'
            f'</sup>'
        ),
        narrative,
    )


def _story_rewrite_map(
    session, article_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Return ``{article_id: rewrite_dict}`` for articles whose Story has a
    committed narrative. ``rewrite_dict`` contains the rendered fields the
    story.html template consumes.
    """
    if not article_ids:
        return {}
    from engine.core.db import StorySource as _SS

    link_rows = session.execute(
        select(StoryArticle.article_id, StoryArticle.story_id).where(
            StoryArticle.article_id.in_(article_ids)
        )
    ).all()
    if not link_rows:
        return {}
    article_to_story: dict[int, int] = {aid: sid for aid, sid in link_rows}
    story_ids = list({sid for _, sid in link_rows})

    story_rows = session.execute(
        select(Story).where(Story.id.in_(story_ids))
    ).scalars().all()
    by_story_id: dict[int, Story] = {st.id: st for st in story_rows}

    source_rows = session.execute(
        select(_SS).where(_SS.story_id.in_(story_ids)).order_by(_SS.cited_as_n)
    ).scalars().all()
    # C5 — fetch article title + datePublished per source for richer JSON-LD.
    cited_article_ids = [sr.article_id for sr in source_rows if sr.article_id]
    article_meta_by_id: dict[int, dict[str, Any]] = {}
    if cited_article_ids:
        for art in session.execute(
            select(Article).where(Article.id.in_(cited_article_ids))
        ).scalars():
            published = art.published_at
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            article_meta_by_id[art.id] = {
                "headline": art.title,
                "datePublished": published.isoformat() if published else None,
            }
    sources_by_story: dict[int, list[dict[str, Any]]] = {}
    for sr in source_rows:
        meta = article_meta_by_id.get(sr.article_id, {}) if sr.article_id else {}
        sources_by_story.setdefault(sr.story_id, []).append(
            {
                "n": sr.cited_as_n,
                "host": sr.host,
                "url": sr.source_url,
                "agency_class": sr.agency_class,
                "agency_label": _AGENCY_CLASS_LABELS.get(
                    sr.agency_class, sr.agency_class
                ),
                "article_id": sr.article_id,
                "headline": meta.get("headline"),
                "date_published": meta.get("datePublished"),
            }
        )

    out: dict[int, dict[str, Any]] = {}
    for aid, sid in article_to_story.items():
        story = by_story_id.get(sid)
        if story is None or not story.narrative:
            continue
        updated = story.narrative_updated_at
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        out[aid] = {
            "narrative": story.narrative,
            "narrative_html": _linkify_citations(story.narrative),
            "why_this_matters": story.why_this_matters,
            "version": story.narrative_version or 0,
            "model": story.narrative_model,
            "word_count": story.narrative_word_count,
            "updated_iso": updated.isoformat() if updated else "",
            "state": story.state,
            "sources": sources_by_story.get(sid, []),
            "n_sources": len(sources_by_story.get(sid, [])),
        }
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
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    # Path A — only render articles with a quality rewrite.
                    _renderable_article_clause(),
                )
                .order_by(Article.fetched_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        article_ids = [a.id for a in rows]
        siblings_by_id = _siblings_map(session, article_ids)
        entities_by_id = _entities_map(session, article_ids)
        research_by_id = _research_bundles_map(session, article_ids)
        rewrite_by_id = _story_rewrite_map(session, article_ids)
        redirect_by_id = _non_primary_redirects(session, article_ids)

    env = _env()
    base_dir = _output_dir(vertical_name) / "story"
    base_dir.mkdir(parents=True, exist_ok=True)

    for a in rows:
        # C2 — non-primary cluster members redirect to the primary's slug
        # rather than emit a duplicate full page.
        redirect_to = redirect_by_id.get(a.id)
        if redirect_to:
            redirect_html = (
                "<!doctype html>\n<html><head>"
                f'<meta http-equiv="refresh" content="0; url=/story/{redirect_to}/">'
                f'<link rel="canonical" href="/story/{redirect_to}/">'
                f'<title>{a.title}</title></head>'
                f'<body><p>This story has moved to <a href="/story/{redirect_to}/">'
                f'/story/{redirect_to}/</a>.</p></body></html>'
            )
            story_dir = base_dir / a.slug
            story_dir.mkdir(parents=True, exist_ok=True)
            (story_dir / "index.html").write_text(redirect_html, encoding="utf-8")
            out[a.slug] = story_dir / "index.html"
            continue
        pub_dt = a.published_at
        if pub_dt is not None and pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        fetched_dt = a.fetched_at
        if fetched_dt is not None and fetched_dt.tzinfo is None:
            fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
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
            "published_iso": pub_dt.isoformat() if pub_dt else "",
            "fetched_iso": fetched_dt.isoformat() if fetched_dt else "",
            "labels": a.labels or [],
            "siblings": siblings_by_id.get(a.id, []),
            "entities": entities_by_id.get(a.id, []),
            "is_skip": (a.curator_tier == "skip"),
            "curator_tier": a.curator_tier,
            "curator_score": a.curator_score,
            "research": research_by_id.get(a.id, []),
            "story_rewrite": rewrite_by_id.get(a.id),
        }
        ctx = {
            "vertical": vertical_ctx,
            "title": a.title,
            "description": (a.summary or a.title)[:160],
            "theme": "light",
            "article": article_ctx,
            "canonical_url": _canonical_url(vertical_name, f"/story/{a.slug}/"),
            "noindex": (a.curator_tier == "skip"),
        }
        html = env.get_template("story.html").render(**ctx)
        story_dir = base_dir / a.slug
        story_dir.mkdir(parents=True, exist_ok=True)
        story_path = story_dir / "index.html"
        story_path.write_text(html, encoding="utf-8")
        out[a.slug] = story_path

    # Sweep stale on-disk story directories whose slug no longer qualifies
    # under Path A — feed-only articles previously rendered before the
    # filter was added, and any slugs whose Article row was deleted.
    # Idempotent: only removes slugs not in the freshly-rendered set.
    kept_slugs = set(out.keys())
    swept = 0
    if base_dir.exists():
        for child in base_dir.iterdir():
            if not child.is_dir() or child.name in kept_slugs:
                continue
            index_html = child / "index.html"
            if index_html.exists():
                try:
                    index_html.unlink()
                    # Clean up other files (assets) in the dir if present,
                    # then the dir itself.
                    for leftover in child.iterdir():
                        leftover.unlink()
                    child.rmdir()
                    swept += 1
                except OSError as exc:
                    logger.warning(
                        "sweep: failed to remove %s: %s", child, exc
                    )
    if swept:
        logger.info(
            "swept %s stale %s story dirs (Path A filter)", swept, vertical_name
        )

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


def render_search(vertical_name: str, *, limit: int = 5000) -> dict[str, Path]:
    """Write the client-side search index + the /search/ page.

    The index is a JSON array of compact records (short keys to keep the
    payload tight — at 1k articles it's roughly 200 KB). The page does
    fuzzy substring ranking in inline JS, no server endpoint.
    """
    import json as _json

    Session = get_sessionmaker()
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
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    (Article.curator_tier != "skip")
                    | Article.curator_tier.is_(None),
                )
                .order_by(Article.published_at.desc().nullslast())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    payload = [
        {
            "s": a.slug,
            "t": a.title,
            "x": (a.summary or "")[:200],
            "r": a.feed_region or "",
        }
        for a in rows
    ]

    out_dir = _output_dir(vertical_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "search-index.json"
    json_path.write_text(
        _json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    env = _env()
    page_dir = out_dir / "search"
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / "index.html"
    page_path.write_text(
        env.get_template("search.html").render(
            vertical=vertical_ctx,
            title="Search",
            description=(
                f"Search every {vertical_ctx['display_name']} article we've "
                "indexed. Client-side, no server lookups."
            ),
            theme="light",
            canonical_url=_canonical_url(vertical_name, "/search/"),
            article_count=len(payload),
        ),
        encoding="utf-8",
    )
    logger.info(
        "rendered %s search index (%d records, %d KB)",
        vertical_name,
        len(payload),
        json_path.stat().st_size // 1024,
    )
    return {"index_json": json_path, "page": page_path}


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
        "search": render_search(vertical_name),
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
