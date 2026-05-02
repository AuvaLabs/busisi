"""Parallel feed fetcher with per-domain rate limiting.

Ported from ``modules/feed_fetcher.py`` in ThreatWatch (HEAD fffecca) with
two grimoire-specific changes:

1. **Per-domain rate limiter** uses Redis (key ``rate:domain:<host>`` holding
   the last-fetch unix ts). Default minimum interval: 2 seconds per host —
   enough to be polite without making the pipeline crawl.
2. **UA identifies as the Grimoire bot** with a link to the property's
   ``/about`` page (set per render-context; default falls back to the
   generic platform UA).

Critical lesson preserved verbatim from ThreatWatch: the urllib3 retry
adapter is configured for transport-level errors (429/5xx) on feed fetches,
because feeds typically recover quickly from transient blips. The LLM
client (separate module) does NOT use Retry — see ``llm_client.py`` for the
explanation.
"""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from engine.core.config import (
    FEED_CUTOFF_DAYS,
    MAX_FEED_FETCH_THREADS,
    REDIS_URL,
)
from engine.core.deduplicator import normalize_url

logger = logging.getLogger(__name__)


_FEED_HEADERS = {
    "User-Agent": (
        "GrimoireBot/0.1 (+https://grimoire.local/about) "
        "(content aggregator; respects robots.txt)"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}
_FEED_TIMEOUT = 10
_PER_DOMAIN_MIN_INTERVAL = 2.0

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_FEED_HEADERS)
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session


def _redis() -> Any | None:
    try:
        from redis import Redis

        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for rate limiter: %s", exc)
        return None


def _wait_for_rate_limit(host: str) -> None:
    """Sleep just long enough to satisfy the 1-req-per-2s per-domain rule."""
    client = _redis()
    if client is None:
        return
    key = f"rate:domain:{host}"
    try:
        last_str = client.get(key)
        now = time.time()
        if last_str is not None:
            elapsed = now - float(last_str)
            if elapsed < _PER_DOMAIN_MIN_INTERVAL:
                time.sleep(_PER_DOMAIN_MIN_INTERVAL - elapsed)
        client.set(key, str(time.time()), ex=300)
    except Exception as exc:
        logger.debug("rate-limit check failed for %s: %s", host, exc)


def _parse_published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        from dateutil import parser as dateparser

        dt = dateparser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, ImportError):
        return None


def _record_health(feed_url: str, *, success: bool, count: int) -> None:
    client = _redis()
    if client is None:
        return
    try:
        h = f"feed_health:{feed_url}"
        client.hincrby(h, "ok" if success else "err", 1)
        if success:
            client.hset(h, "last_ok_ts", str(time.time()))
            client.hset(h, "last_count", str(count))
        else:
            client.hset(h, "last_err_ts", str(time.time()))
        client.expire(h, 30 * 24 * 3600)
    except Exception as exc:
        logger.debug("feed_health write failed for %s: %s", feed_url, exc)


def _fetch_one(feed: dict[str, Any]) -> list[dict[str, Any]]:
    url = feed["url"]
    region = feed.get("region", "Global")
    vertical_id = feed.get("vertical_id", "default")
    host = urlparse(url).netloc

    _wait_for_rate_limit(host)

    try:
        resp = _get_session().get(url, timeout=_FEED_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        logger.error("Error fetching %s: %s", url, exc)
        _record_health(url, success=False, count=0)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=FEED_CUTOFF_DAYS)
    out: list[dict[str, Any]] = []

    for entry in parsed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue

        clean_link = normalize_url(link)
        published = entry.get("published", "") or entry.get("updated", "") or ""
        pub_dt = _parse_published(published)
        if pub_dt is None or pub_dt < cutoff:
            continue

        h = hashlib.sha256((title + clean_link).encode()).hexdigest()
        out.append(
            {
                "title": title,
                "link": link,
                "published": published,
                "summary": entry.get("summary", "") or "",
                "hash": h,
                "source": url,
                "feed_region": region,
                "vertical_id": vertical_id,
            }
        )

    logger.info("Fetched %d entries from %s", len(out), url)
    _record_health(url, success=True, count=len(out))
    return out


def fetch_articles(
    feeds: list[dict[str, Any]], *, max_workers: int | None = None
) -> list[dict[str, Any]]:
    """Fetch a list of feeds in parallel and return the flattened article list."""
    workers = max_workers or MAX_FEED_FETCH_THREADS
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch_one, f): f["url"] for f in feeds}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                out.extend(fut.result())
            except Exception as exc:
                logger.error("Exception fetching %s: %s", url, exc)
    logger.info("Total entries fetched: %d", len(out))
    return out
