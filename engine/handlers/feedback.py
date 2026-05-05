"""Reader-feedback endpoint — POST /api/feedback.

Lets readers flag a story for editorial issues (factual error, broken
link, outdated, spam, other). The flag lands in ``article_feedback``
and feeds back into curator tuning + ops triage.

Schema lives in alembic 0002 (Phase 22g originally drafted alongside
the curator arc). Reporter identity is sha256-peppered IP only — no
PII retained beyond the optional free-text note (max 1000 chars).

Per-IP rate limited via the same Redis fixed-window primitive used by
/api/subscribe + /api/sponsor.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from engine.core.bot_log_parser import hash_ip
from engine.core.db import (
    Article,
    ArticleFeedback,
    Vertical,
    get_sessionmaker,
)
from engine.handlers.security import rate_limit_hit

logger = logging.getLogger(__name__)
router = APIRouter()


_ISSUE_KINDS: Final[set[str]] = {
    "factual_error",
    "broken_link",
    "outdated",
    "spam",
    "other",
}

_NOTE_MAX = 1000
_SLUG_MAX = 256
_VERTICAL_MAX = 64


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/api/feedback")
def submit_feedback(
    request: Request,
    vertical: str = Form(..., min_length=1, max_length=_VERTICAL_MAX),
    slug: str = Form(..., min_length=1, max_length=_SLUG_MAX),
    issue_kind: str = Form(...),
    note: str = Form("", max_length=_NOTE_MAX),
    hp: str = Form(""),
) -> JSONResponse:
    # Honeypot: bots fill any visible-named field; real readers don't.
    # Return 200 silently so spammers don't learn the field name matters.
    if hp:
        return JSONResponse({"ok": True, "status": "received"})

    ip = _client_ip(request)
    if not rate_limit_hit("feedback", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    if issue_kind not in _ISSUE_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"issue_kind must be one of {sorted(_ISSUE_KINDS)}",
        )

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(
                status_code=404, detail=f"unknown vertical: {vertical}"
            )

        article = session.execute(
            select(Article).where(
                Article.vertical_id == v.id,
                Article.slug == slug,
            )
        ).scalar_one_or_none()
        if article is None:
            raise HTTPException(status_code=404, detail="article not found")

        session.add(
            ArticleFeedback(
                article_id=article.id,
                reporter_ip_hash=hash_ip(ip),
                issue_kind=issue_kind,
                note=note[:_NOTE_MAX],
            )
        )
        session.commit()

    logger.info(
        "feedback received: vertical=%s slug=%s kind=%s",
        vertical,
        slug,
        issue_kind,
    )
    return JSONResponse({"ok": True, "status": "received"})
