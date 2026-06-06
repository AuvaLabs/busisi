"""Public read API — versioned at /api/v1.

Programmatic access for AI ingestion (Perplexity, ChatGPT Search, RAG
pipelines), partner integrations, and our own future analytics. JSON
only. Read-only. Skip-tier articles are excluded — consistent with
sitemap.xml and the public front page (Phase 22c).

Per-IP rate-limited via the same Redis fixed-window primitive used by
/api/subscribe and /api/sponsor. Caddy reverse-proxies /api/* to the
FastAPI handler service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from engine.core.db import Article, Entity, Vertical, get_sessionmaker
from engine.handlers.security import rate_limit_hit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


_ARTICLES_LIMIT_DEFAULT = 50
_ARTICLES_LIMIT_MAX = 200
_ENTITIES_LIMIT_DEFAULT = 100
_ENTITIES_LIMIT_MAX = 500
_STORIES_LIMIT_DEFAULT = 25
_STORIES_LIMIT_MAX = 100
_ANIMA_LIMIT_DEFAULT = 40
_ANIMA_LIMIT_MAX = 100
_ANIMA_DEFAULT_VERTICAL = "vested"
_TOPICS_DAYS_DEFAULT = 14
_TOPICS_DAYS_MAX = 90
_TOPICS_LIMIT_DEFAULT = 20
_TOPICS_LIMIT_MAX = 50
_TOPICS_STORY_POOL = 150  # recent stories to cluster over


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _short_source(url: str) -> str:
    try:
        host = urlparse(url).netloc
        return host.removeprefix("www.")
    except Exception:
        return ""


def _isoformat(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        s = since.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"invalid 'since' (need ISO-8601, got: {since!r})",
        )


@router.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "version": "v1"})


@router.get("/articles")
def list_articles(
    request: Request,
    vertical: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(_ARTICLES_LIMIT_DEFAULT, ge=1, le=_ARTICLES_LIMIT_MAX),
    since: str | None = Query(None),
) -> JSONResponse:
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    since_dt = _parse_since(since)

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")

        stmt = (
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
        if since_dt is not None:
            stmt = stmt.where(Article.published_at >= since_dt)

        rows = session.execute(stmt).scalars().all()

        data: list[dict[str, Any]] = []
        for a in rows:
            data.append(
                {
                    "slug": a.slug,
                    "title": a.title,
                    "link": a.link,
                    "summary": a.summary or "",
                    "why_this_matters": a.why_this_matters or "",
                    "published_at": _isoformat(a.published_at),
                    "fetched_at": _isoformat(a.fetched_at),
                    "feed_region": a.feed_region,
                    "source_short": _short_source(a.link),
                    "labels": [
                        l.get("label") if isinstance(l, dict) else str(l)
                        for l in (a.labels or [])
                        if l
                    ],
                    "curator_tier": a.curator_tier,
                }
            )

    return JSONResponse(
        {
            "vertical": vertical,
            "count": len(data),
            "limit": limit,
            "since": since,
            "data": data,
        }
    )


@router.get("/entities")
def list_entities(
    request: Request,
    vertical: str = Query(..., min_length=1, max_length=64),
    type: str | None = Query(None, max_length=32),
    limit: int = Query(_ENTITIES_LIMIT_DEFAULT, ge=1, le=_ENTITIES_LIMIT_MAX),
) -> JSONResponse:
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")

        stmt = (
            select(Entity)
            .where(Entity.vertical_id == v.id)
            .order_by(Entity.last_seen_at.desc())
            .limit(limit)
        )
        if type:
            stmt = stmt.where(Entity.type == type)

        rows = session.execute(stmt).scalars().all()

        data = [
            {
                "type": e.type,
                "slug": e.slug,
                "name": e.name,
                "first_seen_at": _isoformat(e.first_seen_at),
                "last_seen_at": _isoformat(e.last_seen_at),
            }
            for e in rows
        ]

    return JSONResponse(
        {
            "vertical": vertical,
            "type": type,
            "count": len(data),
            "limit": limit,
            "data": data,
        }
    )


@router.get("/stories")
def list_stories(
    request: Request,
    vertical: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(_STORIES_LIMIT_DEFAULT, ge=1, le=_STORIES_LIMIT_MAX),
    since: str | None = Query(None),
    state: str | None = Query(
        None,
        pattern=r"^(draft|ready|published|revising|archived)$",
    ),
) -> JSONResponse:
    """C3 — list canonical Stories with narrative + citation graph.

    Returns one record per Story with the full multi-source narrative,
    `[N]`-indexed sources, and citation provenance. Designed for AI
    ingestion (Perplexity, ChatGPT Search) and partner RAG pipelines.

    Default ``state`` filter is ``published`` so consumers see narrative-
    bearing rows only. Pass an explicit ``state`` (e.g. ``revising``) to
    include in-progress rewrites.
    """
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    since_dt = _parse_since(since)
    target_state = state or "published"

    # Local imports keep top-of-file lean; these models are only needed here.
    from engine.core.db import Story, StorySource

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")

        stmt = (
            select(Story)
            .where(Story.vertical_id == v.id, Story.state == target_state)
            .order_by(Story.primary_published_at.desc())
            .limit(limit)
        )
        if since_dt is not None:
            stmt = stmt.where(Story.primary_published_at >= since_dt)
        stories = session.execute(stmt).scalars().all()

        story_ids = [s.id for s in stories]
        sources_by_story: dict[int, list[dict[str, Any]]] = {}
        if story_ids:
            for sr in session.execute(
                select(StorySource)
                .where(StorySource.story_id.in_(story_ids))
                .order_by(StorySource.cited_as_n)
            ).scalars().all():
                sources_by_story.setdefault(sr.story_id, []).append(
                    {
                        "n": sr.cited_as_n,
                        "url": sr.source_url,
                        "host": sr.host,
                        "agency_class": sr.agency_class,
                        "article_id": sr.article_id,
                    }
                )

        data: list[dict[str, Any]] = []
        for s in stories:
            data.append(
                {
                    "id": s.id,
                    "headline": s.canonical_headline,
                    "narrative": s.narrative,
                    "why_this_matters": s.why_this_matters,
                    "version": s.narrative_version,
                    "word_count": s.narrative_word_count,
                    "model": s.narrative_model,
                    "state": s.state,
                    "primary_published": _isoformat(s.primary_published_at),
                    "narrative_updated": _isoformat(s.narrative_updated_at),
                    "sources": sources_by_story.get(s.id, []),
                }
            )

    return JSONResponse(
        {
            "vertical": vertical,
            "state": target_state,
            "count": len(data),
            "limit": limit,
            "data": data,
        }
    )


# ---------------------------------------------------------------------------
# Anima channel feeder — §3 JSON contract + economic-release calendar.
# Additive surface for the Vested → Anima finance-channel feeder. Computed on
# read from existing story data; see engine/core/anima_enricher.py.
# ---------------------------------------------------------------------------


def _ordered_labels(articles: list[Any]) -> list[str]:
    """Union of member-article labels, highest confidence first.

    ``Article.labels`` is a JSON list of ``{"label", "confidence"}`` dicts (or
    bare strings on older rows). Aggregate by max confidence so the lane mapper
    sees the cluster's strongest topic first.
    """
    best: dict[str, float] = {}
    for a in articles:
        for item in a.labels or []:
            if isinstance(item, dict):
                name = item.get("label")
                conf = float(item.get("confidence", 0) or 0)
            else:
                name, conf = str(item), 0.0
            if not name:
                continue
            if name not in best or conf > best[name]:
                best[name] = conf
    return [name for name, _ in sorted(best.items(), key=lambda kv: kv[1], reverse=True)]


def _union_numerics(articles: list[Any]) -> list[dict[str, Any]]:
    """Flatten every member article's ``structured_extract.numerics``."""
    out: list[dict[str, Any]] = []
    for a in articles:
        extract = a.structured_extract or {}
        if isinstance(extract, dict):
            for n in extract.get("numerics", []) or []:
                out.append(n)
    return out


def _load_anima_story_contracts(
    session: Any,
    vertical_id: int,
    *,
    limit: int,
    since_dt: datetime | None,
) -> list[dict[str, Any]]:
    """Load recent published Stories for a vertical as §3 contract dicts.

    Shared by /anima/feed and /anima/topics — returns the per-story enriched
    records (key_stat, primary_source_url, lane, momentum, entities, ...).
    """
    from engine.core import anima_enricher
    from engine.core.db import ArticleEntity, Entity, Story, StoryArticle, StorySource

    # NOT state=="published": the lifecycle archives a story ~24h after publish,
    # so a state filter would miss almost the whole corpus. `narrative IS NOT
    # NULL` is the same "has been published" signal the front page + digest use,
    # and it excludes draft/ready clusters (which have no narrative yet).
    stmt = (
        select(Story)
        .where(
            Story.vertical_id == vertical_id,
            Story.narrative.is_not(None),
            Story.state != "draft",
        )
        .order_by(Story.primary_published_at.desc())
        .limit(limit)
    )
    if since_dt is not None:
        stmt = stmt.where(Story.primary_published_at >= since_dt)
    stories = session.execute(stmt).scalars().all()
    story_ids = [s.id for s in stories]

    members_by_story: dict[int, list[Any]] = {}
    primary_article_by_story: dict[int, Any] = {}
    article_ids: list[int] = []
    if story_ids:
        links = session.execute(
            select(StoryArticle).where(StoryArticle.story_id.in_(story_ids))
        ).scalars().all()
        article_id_set = {ln.article_id for ln in links}
        articles_by_id = {
            a.id: a
            for a in session.execute(
                select(Article).where(Article.id.in_(article_id_set))
            ).scalars().all()
        }
        article_ids = list(article_id_set)
        for ln in links:
            art = articles_by_id.get(ln.article_id)
            if art is None:
                continue
            members_by_story.setdefault(ln.story_id, []).append(art)
            if ln.is_primary:
                primary_article_by_story[ln.story_id] = art

    sources_by_story: dict[int, list[dict[str, Any]]] = {}
    if story_ids:
        for sr in session.execute(
            select(StorySource)
            .where(StorySource.story_id.in_(story_ids))
            .order_by(StorySource.cited_as_n)
        ).scalars().all():
            sources_by_story.setdefault(sr.story_id, []).append(
                {
                    "host": sr.host,
                    "agency_class": sr.agency_class,
                    "source_url": sr.source_url,
                }
            )

    entities_by_article: dict[int, list[str]] = {}
    if article_ids:
        rows = session.execute(
            select(ArticleEntity.article_id, Entity.name)
            .join(Entity, Entity.id == ArticleEntity.entity_id)
            .where(ArticleEntity.article_id.in_(article_ids))
        ).all()
        for art_id, name in rows:
            entities_by_article.setdefault(art_id, []).append(name)

    out: list[dict[str, Any]] = []
    for s in stories:
        members = members_by_story.get(s.id, [])
        primary = primary_article_by_story.get(s.id) or (
            members[0] if members else None
        )
        url = primary.link if primary is not None else ""
        summary = s.why_this_matters or (
            primary.summary if primary is not None else ""
        )
        seen: set[str] = set()
        entities: list[str] = []
        for art in members:
            for name in entities_by_article.get(art.id, []):
                if name not in seen:
                    seen.add(name)
                    entities.append(name)
        out.append(
            anima_enricher.story_to_contract(
                story_id=s.id,
                headline=s.canonical_headline,
                summary=summary,
                url=url,
                labels=_ordered_labels(members),
                numerics=_union_numerics(members),
                sources=sources_by_story.get(s.id, []),
                entities=entities,
                narrative=s.narrative,
                published_at=s.primary_published_at,
            )
        )
    return out


@router.get("/anima/feed")
def anima_feed(
    request: Request,
    vertical: str = Query(_ANIMA_DEFAULT_VERTICAL, min_length=1, max_length=64),
    limit: int = Query(_ANIMA_LIMIT_DEFAULT, ge=1, le=_ANIMA_LIMIT_MAX),
    since: str | None = Query(None),
) -> JSONResponse:
    """Structured story source for Anima — the §3 contract.

    One array entry per recent published Story, enriched with the fields
    Anima's scorer + fact-gate consume: ``key_stat``, ``primary_source_url``,
    ``lane``, ``evergreen``, ``momentum``, ``entities``. Read-only; derived
    on the fly from the existing cluster / source / extract data.
    """
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    since_dt = _parse_since(since)

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")
        data = _load_anima_story_contracts(
            session, v.id, limit=limit, since_dt=since_dt
        )

    return JSONResponse(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "vertical": vertical,
            "count": len(data),
            "limit": limit,
            "since": since,
            "stories": data,
        }
    )


@router.get("/anima/calendar")
def anima_calendar(
    request: Request,
    vertical: str = Query(_ANIMA_DEFAULT_VERTICAL, min_length=1, max_length=64),
    upcoming_only: bool = Query(False),
) -> JSONResponse:
    """Economic-release calendar — scheduled data drops for episode pre-planning.

    Static per-vertical ``calendar.yaml`` (CPI, FOMC, jobs, SS Trustees, ...).
    Each entry carries the release date and the ``primary_source_url`` the
    numbers land on. ``upcoming_only=true`` filters to future-dated releases.
    """
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    from engine.core import anima_enricher

    try:
        releases = anima_enricher.load_calendar(vertical)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")
    if upcoming_only:
        releases = [r for r in releases if r.get("is_upcoming")]

    return JSONResponse(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "vertical": vertical,
            "count": len(releases),
            "upcoming_only": upcoming_only,
            "releases": releases,
        }
    )


@router.get("/anima/topics")
def anima_topics(
    request: Request,
    vertical: str = Query(_ANIMA_DEFAULT_VERTICAL, min_length=1, max_length=64),
    days: int = Query(_TOPICS_DAYS_DEFAULT, ge=1, le=_TOPICS_DAYS_MAX),
    limit: int = Query(_TOPICS_LIMIT_DEFAULT, ge=1, le=_TOPICS_LIMIT_MAX),
    min_cluster: int = Query(2, ge=1, le=10),
) -> JSONResponse:
    """Evidence-backed finance topic candidates for Anima (deterministic).

    Clusters the last ``days`` of published Stories by shared entity into topic
    candidates, each with a fact pack — every claim tied to its ``key_stat`` and
    ``primary_source_url`` — ready for Anima to score, fact-gate, and storyboard.
    Vested supplies the sourced facts; Anima does the creative selection and
    scripting. No LLM in the request path — purely derived from the corpus.
    """
    ip = _client_ip(request)
    if not rate_limit_hit("api_v1", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    from datetime import timedelta

    from engine.core import anima_topics as topics_mod

    since_dt = datetime.now(timezone.utc) - timedelta(days=days)

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail=f"unknown vertical: {vertical}")
        stories = _load_anima_story_contracts(
            session, v.id, limit=_TOPICS_STORY_POOL, since_dt=since_dt
        )

    topics = topics_mod.build_topics(stories, min_cluster=min_cluster, limit=limit)

    return JSONResponse(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "vertical": vertical,
            "days": days,
            "story_pool": len(stories),
            "count": len(topics),
            "topics": topics,
        }
    )
