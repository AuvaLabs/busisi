"""Article body scraper — trafilatura wrapper.

For feeds that ship excerpts only (most tech press, many newsletters), the
RSS summary is too thin for grounded summarisation. This module fetches the
full HTML and extracts cleaned body text + metadata.

Per architecture-derivation §11 row 3: "Port + extend — Add image
extraction, author extraction, language detect, UTC normalisation".

The shared HTTP session inherits the SSRF guard and rate-limit behaviour
already wired into ``feed_fetcher`` — no separate hardening needed here.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


_SCRAPE_TIMEOUT = 12  # seconds; longer than feed fetch — articles can be heavy


def _get_session() -> Any:
    from engine.core import feed_fetcher

    return feed_fetcher._get_session()


def _wait_for_rate_limit(host: str) -> None:
    from engine.core import feed_fetcher

    feed_fetcher._wait_for_rate_limit(host)


def scrape_article(url: str) -> dict[str, Any]:
    """Fetch and extract a single article. Never raises."""
    out: dict[str, Any] = {
        "url": url,
        "body": None,
        "html": None,
        "language": None,
        "word_count": 0,
        "image_url": None,
        "author": None,
        "success": False,
        "error": None,
    }
    try:
        host = urlparse(url).netloc
        _wait_for_rate_limit(host)
        resp = _get_session().get(url, timeout=_SCRAPE_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        out["html"] = html
    except Exception as exc:
        out["error"] = f"fetch: {exc}"
        return out

    try:
        import trafilatura

        body = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if not body:
            out["error"] = "trafilatura returned no body"
            return out
        out["body"] = body
        out["word_count"] = len(body.split())

        meta = trafilatura.extract_metadata(html)
        if meta is not None:
            out["author"] = meta.author or None
            out["image_url"] = meta.image or None
    except Exception as exc:
        out["error"] = f"extract: {exc}"
        return out

    try:
        import langid

        lang, _conf = langid.classify(out["body"][:2000])
        out["language"] = lang
    except Exception:
        out["language"] = None

    out["success"] = True
    return out


def scrape_articles(
    urls: list[str], *, max_workers: int = 8
) -> dict[str, dict[str, Any]]:
    """Scrape a batch of URLs in parallel. Returns {url: result}."""
    out: dict[str, dict[str, Any]] = {}
    if not urls:
        return out
    started = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(scrape_article, u): u for u in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                out[url] = fut.result()
            except Exception as exc:
                out[url] = {
                    "url": url,
                    "body": None,
                    "html": None,
                    "success": False,
                    "error": f"task: {exc}",
                }
    elapsed = time.time() - started
    success = sum(1 for r in out.values() if r["success"])
    logger.info(
        "scrape_articles: %d urls, %d successful in %.1fs", len(urls), success, elapsed
    )
    return out
