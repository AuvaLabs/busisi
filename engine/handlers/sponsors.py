"""Inbound sponsorship inquiry route.

POST /api/sponsor — captures the form, persists a SponsorInquiry row, and
fires an operator notification email. Plaintext email at rest is fine
here: this is a B2B contact form, not a newsletter list.
"""

from __future__ import annotations

import logging
from typing import Final

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from engine.core.config import SPONSOR_NOTIFY_TO
from engine.core.db import SponsorInquiry, Vertical, get_sessionmaker
from engine.handlers import email_sender
from engine.handlers.security import rate_limit_hit

logger = logging.getLogger(__name__)
router = APIRouter()

_BUDGETS: Final[set[str]] = {
    "under_5k",
    "5k_25k",
    "25k_100k",
    "over_100k",
    "custom",
}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/api/sponsor")
def sponsor(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    vertical: str = Form(...),
    company: str = Form(""),
    budget_band: str = Form("custom"),
    message: str = Form(""),
    hp: str = Form(""),
) -> JSONResponse:
    if hp:
        return JSONResponse({"ok": True, "status": "received"})

    ip = _client_ip(request)
    if not rate_limit_hit("sponsor", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    try:
        info = validate_email(email, check_deliverability=False)
        clean_email = info.normalized
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="invalid email") from None

    if not name.strip():
        raise HTTPException(status_code=422, detail="name required")
    if budget_band not in _BUDGETS:
        budget_band = "custom"

    name = name.strip()[:128]
    company = company.strip()[:256]
    message = message.strip()[:4000]

    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail="unknown vertical")
        row = SponsorInquiry(
            vertical_id=v.id,
            name=name,
            email=clean_email,
            company=company,
            budget_band=budget_band,
            message=message,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        inquiry_id = row.id

    email_sender.send(
        to=SPONSOR_NOTIFY_TO,
        subject=f"[grimoire/{vertical}] sponsor inquiry #{inquiry_id} — {name}",
        text_body=(
            f"Inquiry id: {inquiry_id}\n"
            f"Vertical: {vertical}\n"
            f"Name: {name}\n"
            f"Company: {company or '(not provided)'}\n"
            f"Email: {clean_email}\n"
            f"Budget: {budget_band}\n\n"
            f"Message:\n{message or '(empty)'}\n"
        ),
        reply_to=clean_email,
    )
    return JSONResponse({"ok": True, "status": "received", "id": inquiry_id})


__all__ = ["router"]
