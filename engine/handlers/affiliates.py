"""Affiliate-link redirect surface — /r/<partner>/<slug>.

The author-side macro at engine/shared/templates/_affiliate.html turns
every affiliate link into <a href="..."> with rel=sponsored. This module
ships the click-tracking peer: a 302 redirect through /r/<partner>/<slug>
that records an AffiliateClick row before sending the user to the
partner URL. UTM tags are auto-appended so partners can attribute clicks
without us depending on third-party trackers.

Partner registry lives at verticals/<vertical>/partners.yaml. Vertical
is resolved from the Host header (matching the Caddyfile site blocks).

Caddy needs a /r/* reverse-proxy block per vertical:

  handle /r/* {
    reverse_proxy 127.0.0.1:8001
  }
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode, urlparse

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from engine.core.bot_log_parser import hash_ip
from engine.core.config import vertical_dir
from engine.core.db import AffiliateClick, Vertical, get_sessionmaker
from engine.handlers.security import rate_limit_hit

logger = logging.getLogger(__name__)
router = APIRouter()


@lru_cache(maxsize=8)
def _load_partners(vertical: str) -> dict[str, dict[str, Any]]:
    """Load and cache the partner registry for a vertical.

    Format::
        partners:
          anthropic:
            url: https://anthropic.com/?ref=auvalabs
            name: Anthropic
          interactive_brokers:
            url: https://www.interactivebrokers.com/?ref=auvalabs
            name: Interactive Brokers

    Missing/empty file → empty registry (all partners 404).
    """
    try:
        path = vertical_dir(vertical) / "partners.yaml"
    except ValueError:
        return {}
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("partners.yaml parse failed for %s: %s", vertical, exc)
        return {}
    raw = data.get("partners") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for slug, body in raw.items():
        if isinstance(body, dict) and isinstance(body.get("url"), str):
            url = body["url"].strip()
            if url.startswith("https://") or url.startswith("http://"):
                out[str(slug)] = {
                    "url": url,
                    "name": str(body.get("name", slug)),
                }
    return out


def reload_partners() -> None:
    """Drop the partner cache (call after editing partners.yaml in dev)."""
    _load_partners.cache_clear()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _vertical_from_host(host: str) -> str | None:
    """`modelwatch.local:80` / `modelwatch.local` → `modelwatch`. Returns
    None if the host doesn't look like a known vertical."""
    if not host:
        return None
    bare = host.split(":", 1)[0].lower()
    label = bare.split(".", 1)[0]
    if not label or not label.isalnum():
        return None
    return label


def _append_utm(url: str, *, vertical: str, slug: str) -> str:
    parsed = urlparse(url)
    sep = "&" if parsed.query else "?"
    utm = urlencode(
        {
            "utm_source": vertical,
            "utm_medium": "affiliate",
            "utm_campaign": slug or "default",
        }
    )
    return f"{url}{sep}{utm}"


@router.get("/r/{partner}")
def redirect_partner_default(request: Request, partner: str) -> RedirectResponse:
    """Shortcut: /r/<partner> behaves like /r/<partner>/_."""
    return redirect_partner(request, partner, "_")


@router.get("/r/{partner}/{slug}")
def redirect_partner(
    request: Request, partner: str, slug: str
) -> RedirectResponse:
    ip = _client_ip(request)
    if not rate_limit_hit("affiliate", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    host = request.headers.get("host", "")
    vname = _vertical_from_host(host)
    if vname is None:
        raise HTTPException(status_code=400, detail="missing or invalid host")

    partners = _load_partners(vname)
    record = partners.get(partner)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown partner: {partner}")

    safe_slug = "".join(c for c in slug if c.isalnum() or c in ("-", "_"))[:256]

    target = _append_utm(record["url"], vertical=vname, slug=safe_slug)

    Session = get_sessionmaker()
    try:
        with Session() as session:
            v = session.execute(
                select(Vertical).where(Vertical.name == vname)
            ).scalar_one_or_none()
            if v is not None:
                session.add(
                    AffiliateClick(
                        vertical_id=v.id,
                        partner=partner,
                        slug=safe_slug,
                        ip_hash=hash_ip(ip),
                    )
                )
                session.commit()
    except Exception as exc:  # noqa: BLE001 — never block the redirect
        logger.warning("affiliate click log failed: %s", exc)

    return RedirectResponse(url=target, status_code=302)
