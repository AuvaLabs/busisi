"""Per-feed health tracking — Redis-backed counters + status rollup.

Counters are written by ``engine.core.feed_fetcher._record_health`` on every
fetch attempt (success or failure). This module reads them back into a
status mapping for the public ``/sources`` page and the future
``monitoring.py`` health endpoint.

Per BUILD-DIRECTIVE Phase 6: "Each source SLO: successful fetch within 24
hours. Sources with consecutive failures > 5 auto-disabled. Public source
health visible at /sources page."
"""

from __future__ import annotations

import logging
import time
from typing import Any

from engine.core.config import REDIS_URL

logger = logging.getLogger(__name__)


def _redis() -> Any | None:
    try:
        from redis import Redis

        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for source_health: %s", exc)
        return None


def _human_age(ts: float | None) -> str | None:
    if ts is None:
        return None
    now = time.time()
    secs = now - ts
    if secs < 0:
        return None
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_status(url: str) -> dict[str, Any]:
    """Return a status mapping for a single feed url."""
    cold = {"status": "cold", "last_count": None, "last_ok_human": None, "err": 0}
    client = _redis()
    if client is None:
        return cold
    try:
        data: dict[str, Any] = client.hgetall(f"feed_health:{url}") or {}
    except Exception as exc:
        logger.debug("source_health read failed for %s: %s", url, exc)
        return cold

    if not data:
        return cold

    ok_count = _safe_int(data.get("ok"))
    err_count = _safe_int(data.get("err"))
    last_ok_ts = _safe_float(data.get("last_ok_ts"))
    last_err_ts = _safe_float(data.get("last_err_ts"))
    last_count = _safe_int(data.get("last_count")) if "last_count" in data else None

    if ok_count == 0 and err_count == 0:
        return cold

    if last_err_ts and (last_ok_ts is None or last_err_ts > last_ok_ts):
        status = "err"
    elif last_count == 0:
        status = "warn"
    else:
        status = "ok"

    return {
        "status": status,
        "last_count": last_count,
        "last_ok_human": _human_age(last_ok_ts),
        "err": err_count,
        "ok": ok_count,
    }


def overview(vertical_id: str) -> dict[str, int]:
    """Aggregate status counts across all feeds for a vertical."""
    from engine.core.feed_loader import load_feeds

    feeds = load_feeds(vertical_id)
    counters: dict[str, int] = {"ok": 0, "warn": 0, "err": 0, "cold": 0}
    for f in feeds:
        s = get_status(f["url"])
        counters[s["status"]] += 1
    counters["total"] = len(feeds)
    return counters
