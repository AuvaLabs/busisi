"""Redis-backed LLM response cache.

Replaces ThreatWatch's file-based ``modules/ai_cache.py`` (fcntl-locked JSON
files) with Redis. Same key strategy: SHA256 over a caller tag + truncated
content. TTL 30 days; entries self-evict.

Why Redis: the grimoire pipeline is multi-process (pipeline container,
renderer container, batch jobs). File locks become a bottleneck; Redis
gives atomic GET/SETEX with no contention.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from engine.core.config import MAX_CONTENT_CHARS, REDIS_URL

logger = logging.getLogger(__name__)

_TTL_SECONDS = 30 * 24 * 3600
_KEY_PREFIX = "llm:cache:"


def _redis() -> Any | None:
    try:
        from redis import Redis

        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for LLM cache: %s", exc)
        return None


def make_cache_key(caller: str, content: str) -> str:
    """Stable hash for an LLM call (caller tag + truncated content)."""
    return hashlib.sha256(
        (f"{caller}:" + content[:MAX_CONTENT_CHARS]).encode()
    ).hexdigest()


def get(cache_key: str) -> dict[str, Any] | None:
    """Return cached payload or None on miss."""
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_KEY_PREFIX + cache_key)
    except Exception as exc:
        logger.debug("LLM cache read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Corrupt LLM cache entry %s: %s", cache_key[:12], exc)
        try:
            client.delete(_KEY_PREFIX + cache_key)
        except Exception:
            pass
        return None


def put(cache_key: str, value: dict[str, Any], ttl: int | None = None) -> None:
    """Store a payload under the given cache key with an optional override TTL."""
    client = _redis()
    if client is None:
        return
    try:
        client.setex(
            _KEY_PREFIX + cache_key,
            ttl or _TTL_SECONDS,
            json.dumps(value, ensure_ascii=False),
        )
    except Exception as exc:
        logger.debug("LLM cache write failed: %s", exc)


def invalidate(cache_key: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_KEY_PREFIX + cache_key)
    except Exception as exc:
        logger.debug("LLM cache invalidate failed: %s", exc)
