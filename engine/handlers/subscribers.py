"""Newsletter subscribe / confirm / unsubscribe routes.

Flow:
  1. POST /api/subscribe {email, vertical}
       → upsert by SHA256(pepper||email_lower)
       → store Fernet(email_lower) at rest, mint unsubscribe_token
       → mail "Confirm your email" with sign_token("c|<sub_id>") link
  2. GET /confirm?token=…   flips ``confirmed`` + sets confirmed_at
  3. GET /unsubscribe?token=<unsubscribe_token>   sets unsubscribed_at

Idempotent: re-subscribing a confirmed address is a no-op. Re-subscribing
a previously-unsubscribed address re-arms the row + resends confirmation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from engine.core.config import site_origins
from engine.core.db import Subscriber, Vertical, get_sessionmaker
from engine.handlers import email_sender
from engine.handlers.security import (
    CryptoUnavailable,
    encrypt_email,
    hash_email,
    random_token,
    rate_limit_hit,
    sign_token,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _origin_for(vertical_name: str) -> str:
    return site_origins().get(vertical_name, "")


def _resolve_vertical(session, name: str) -> Vertical | None:
    return session.execute(
        select(Vertical).where(Vertical.name == name)
    ).scalar_one_or_none()


@router.post("/api/subscribe")
def subscribe(
    request: Request,
    email: str = Form(...),
    vertical: str = Form(...),
    hp: str = Form("", description="honeypot — must be empty"),
) -> JSONResponse:
    if hp:
        return JSONResponse({"ok": True, "status": "queued"})

    ip = _client_ip(request)
    if not rate_limit_hit("subscribe", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    try:
        info = validate_email(email, check_deliverability=False)
        clean_email = info.normalized
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="invalid email") from None

    Session = get_sessionmaker()
    with Session() as session:
        v = _resolve_vertical(session, vertical)
        if v is None:
            raise HTTPException(status_code=404, detail="unknown vertical")

        try:
            digest = hash_email(clean_email)
            encrypted = encrypt_email(clean_email)
        except CryptoUnavailable:
            logger.error("SUBSCRIBER_FERNET_KEY missing — refusing write")
            raise HTTPException(
                status_code=503, detail="signup temporarily unavailable"
            ) from None

        existing = session.execute(
            select(Subscriber).where(
                Subscriber.vertical_id == v.id,
                Subscriber.email_hash == digest,
            )
        ).scalar_one_or_none()

        if existing is None:
            sub = Subscriber(
                vertical_id=v.id,
                email_hash=digest,
                email_encrypted=encrypted,
                unsubscribe_token=random_token(),
            )
            session.add(sub)
            session.commit()
            session.refresh(sub)
            sub_id = sub.id
            already_confirmed = False
        elif existing.confirmed and existing.unsubscribed_at is None:
            sub_id = existing.id
            already_confirmed = True
        else:
            existing.email_encrypted = encrypted
            existing.unsubscribed_at = None
            session.commit()
            sub_id = existing.id
            already_confirmed = False

    if already_confirmed:
        return JSONResponse({"ok": True, "status": "already_confirmed"})

    confirm_path = "/confirm?token=" + sign_token(f"c|{sub_id}")
    origin = _origin_for(vertical)
    confirm_url = origin + confirm_path if origin else confirm_path

    email_sender.send(
        to=clean_email,
        subject="Confirm your subscription",
        text_body=(
            "Click to confirm your subscription:\n\n"
            f"{confirm_url}\n\n"
            "If you didn't sign up, ignore this email."
        ),
    )
    return JSONResponse({"ok": True, "status": "confirmation_sent"})


@router.get("/confirm")
def confirm(token: str = Query(...)) -> HTMLResponse:
    payload = verify_token(token)
    if not payload or not payload.startswith("c|"):
        return HTMLResponse("<h1>Invalid or expired link</h1>", status_code=400)
    try:
        sub_id = int(payload.split("|", 1)[1])
    except (ValueError, IndexError):
        return HTMLResponse("<h1>Invalid link</h1>", status_code=400)

    Session = get_sessionmaker()
    with Session() as session:
        sub = session.get(Subscriber, sub_id)
        if sub is None:
            return HTMLResponse("<h1>Subscription not found</h1>", status_code=404)
        if not sub.confirmed:
            sub.confirmed = True
            sub.confirmed_at = datetime.now(timezone.utc)
            session.commit()

    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Subscribed</title>"
        "<h1>You're confirmed</h1>"
        "<p>Thanks for subscribing. You'll get the weekly digest "
        "every Sunday.</p>"
    )


@router.get("/unsubscribe")
def unsubscribe(token: str = Query(...)) -> HTMLResponse:
    Session = get_sessionmaker()
    with Session() as session:
        sub = session.execute(
            select(Subscriber).where(Subscriber.unsubscribe_token == token)
        ).scalar_one_or_none()
        if sub is None:
            return HTMLResponse(
                "<h1>Already unsubscribed or invalid link</h1>", status_code=404
            )
        if sub.unsubscribed_at is None:
            sub.unsubscribed_at = datetime.now(timezone.utc)
            session.commit()

    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Unsubscribed</title>"
        "<h1>You've been unsubscribed</h1>"
        "<p>You won't receive further emails. Sorry to see you go.</p>"
    )


__all__ = ["router"]
