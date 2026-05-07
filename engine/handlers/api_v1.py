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
