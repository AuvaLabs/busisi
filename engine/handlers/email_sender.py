"""Postmark wrapper with a dev-time log fallback.

Behaviour:
  POSTMARK_API_TOKEN unset → log at INFO, return ``False``.
  Token set + Postmark 200 → return ``True``.
  Token set + Postmark error → log ``ERROR``, return ``False``.

Return = "delivered to Postmark", not "delivered to inbox".
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from engine.core.config import (
    POSTMARK_API_TOKEN,
    POSTMARK_FROM_ADDRESS,
    POSTMARK_REPLY_TO,
)

logger = logging.getLogger(__name__)

_POSTMARK_ENDPOINT = "https://api.postmarkapp.com/email"
_TIMEOUT_SECONDS = 10


def send(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    stream: str = "outbound",
    reply_to: str | None = None,
) -> bool:
    reply_to = reply_to or POSTMARK_REPLY_TO

    if not POSTMARK_API_TOKEN:
        logger.info(
            "[mail-stub] to=%s subject=%r stream=%s body=%s",
            to,
            subject,
            stream,
            text_body.replace("\n", " ⏎ ")[:200],
        )
        return False

    payload: dict[str, Any] = {
        "From": POSTMARK_FROM_ADDRESS,
        "To": to,
        "Subject": subject,
        "TextBody": text_body,
        "MessageStream": stream,
        "ReplyTo": reply_to,
    }
    if html_body:
        payload["HtmlBody"] = html_body

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_API_TOKEN,
    }
    try:
        resp = requests.post(
            _POSTMARK_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error("postmark send failed: %s", exc)
        return False

    if resp.status_code != 200:
        logger.error(
            "postmark non-200: status=%s body=%s",
            resp.status_code,
            resp.text[:300],
        )
        return False
    return True


__all__ = ["send"]
