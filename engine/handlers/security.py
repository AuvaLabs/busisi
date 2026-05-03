"""Crypto, token, and rate-limit primitives for the handler app.

Subscriber emails are stored two ways:
  * SHA256(pepper || email_lower)  — fast lookup, no PII recoverable
  * Fernet(email_lower)            — recoverable for sending mail

Tokens (confirm/unsubscribe) carry ``payload|exp`` body + HMAC-SHA256 sig.
Single-use enforcement is the caller's job — we just bound lifetime +
integrity-check.

Rate limiting is a Redis fixed-window counter keyed by ``handler:rl:{family}:{ip}``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from engine.core.config import (
    HANDLER_RATE_LIMIT_PER_5MIN,
    SUBSCRIBER_EMAIL_PEPPER,
    SUBSCRIBER_FERNET_KEY,
)
from engine.core.llm_cache import _redis

logger = logging.getLogger(__name__)

_RATE_WINDOW_SECONDS: Final[int] = 300


class CryptoUnavailable(RuntimeError):
    """Raised when SUBSCRIBER_FERNET_KEY is unset and a write would proceed."""


def _fernet() -> Fernet:
    if not SUBSCRIBER_FERNET_KEY:
        raise CryptoUnavailable(
            "SUBSCRIBER_FERNET_KEY is unset; refusing to encrypt subscriber data"
        )
    return Fernet(SUBSCRIBER_FERNET_KEY.encode("utf-8"))


def hash_email(email: str) -> str:
    norm = email.strip().lower()
    h = hashlib.sha256()
    h.update(SUBSCRIBER_EMAIL_PEPPER.encode("utf-8"))
    h.update(b"|")
    h.update(norm.encode("utf-8"))
    return h.hexdigest()


def encrypt_email(email: str) -> str:
    norm = email.strip().lower()
    return _fernet().encrypt(norm.encode("utf-8")).decode("utf-8")


def decrypt_email(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def random_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def sign_token(payload: str, *, expires_in: int = 60 * 60 * 48) -> str:
    if not SUBSCRIBER_FERNET_KEY:
        raise CryptoUnavailable("cannot sign token without SUBSCRIBER_FERNET_KEY")
    exp = int(time.time()) + max(expires_in, 60)
    body = f"{payload}|{exp}".encode("utf-8")
    sig = hmac.new(
        SUBSCRIBER_FERNET_KEY.encode("utf-8"), body, hashlib.sha256
    ).digest()
    return (
        base64.urlsafe_b64encode(body).rstrip(b"=").decode("utf-8")
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode("utf-8")
    )


def verify_token(token: str) -> str | None:
    if not SUBSCRIBER_FERNET_KEY or "." not in token:
        return None
    body_b64, sig_b64 = token.split(".", 1)
    try:
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except (ValueError, base64.binascii.Error):
        return None
    expected = hmac.new(
        SUBSCRIBER_FERNET_KEY.encode("utf-8"), body, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload, exp_str = body.decode("utf-8").rsplit("|", 1)
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError):
        return None
    if int(time.time()) > exp:
        return None
    return payload


def rate_limit_hit(family: str, ip: str) -> bool:
    """True = under the limit (allowed). Fail-open on Redis hiccup."""
    if not ip:
        return True
    key = f"handler:rl:{family}:{ip}"
    try:
        client = _redis()
        if client is None:
            return True
        n = client.incr(key)
        if n == 1:
            client.expire(key, _RATE_WINDOW_SECONDS)
        return int(n) <= HANDLER_RATE_LIMIT_PER_5MIN
    except Exception as exc:
        logger.warning("rate-limit redis check failed: %s", exc)
        return True


__all__ = [
    "CryptoUnavailable",
    "InvalidToken",
    "decrypt_email",
    "encrypt_email",
    "hash_email",
    "random_token",
    "rate_limit_hit",
    "sign_token",
    "verify_token",
]
