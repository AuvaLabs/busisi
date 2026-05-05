"""IndexNow — push-mode indexing for Bing + Yandex (and any IndexNow consumer).

Atelier-pattern adoption. Every render tick, we tell IndexNow about
the day's new article URLs. Bing typically picks up changes within
minutes vs hours/days for crawl-mode discovery.

Per-vertical key file lives at ``verticals/<name>/.indexnow_key``
(mode 600, gitignored). Auto-generated on first run if absent.
The renderer writes a matching ``<KEY>.txt`` to
``data/output/<vertical>/<KEY>.txt`` so IndexNow's verifier can fetch
it from ``https://<vertical-domain>/<KEY>.txt``.

CLI:
  python -m engine.core.indexnow <vertical> [--max N] [--since-hours N] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from engine.core.config import canonical_base_for, vertical_dir
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


_INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
_DEFAULT_BATCH_SIZE = 50
_DEFAULT_SINCE_HOURS = 24
_KEY_LENGTH_BYTES = 16  # 32 hex chars


def _key_path(vertical_name: str) -> Path:
    return vertical_dir(vertical_name) / ".indexnow_key"


def get_or_create_key(vertical_name: str) -> str:
    """Return the IndexNow key for a vertical, generating + persisting one if
    none exists. Stored mode-600 in the per-vertical config dir."""
    path = _key_path(vertical_name)
    if path.exists():
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(_KEY_LENGTH_BYTES)
    path.write_text(key, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    logger.info("indexnow: generated new key for vertical=%s", vertical_name)
    return key


def submit_urls(
    host: str, key: str, urls: list[str], *, dry_run: bool = False
) -> tuple[int, str]:
    """POST a batch of URLs to IndexNow. Returns (status_code, response_text).

    IndexNow accepts up to 10,000 URLs per request; we batch much smaller
    (50 default) since Bing penalises repeated submissions of stale
    content."""
    if not urls:
        return (0, "no urls")
    body = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls,
    }
    if dry_run:
        return (0, json.dumps(body))
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _INDEXNOW_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (resp.status, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read().decode("utf-8", "replace") if exc.fp else str(exc))
    except urllib.error.URLError as exc:
        return (-1, str(exc))


def collect_recent_urls(
    vertical_name: str,
    *,
    since_hours: int = _DEFAULT_SINCE_HOURS,
    limit: int = _DEFAULT_BATCH_SIZE,
) -> list[str]:
    """Build canonical URLs for articles published in the last N hours.
    Skip-tier articles are excluded — same gate as sitemap.xml."""
    base = canonical_base_for(vertical_name).rstrip("/")
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")
        rows = (
            session.execute(
                select(Article.slug)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    (Article.curator_tier != "skip")
                    | Article.curator_tier.is_(None),
                    Article.published_at >= since,
                )
                .order_by(Article.published_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    urls = [f"{base}/story/{slug}/" for slug in rows]
    # Always include the front page so Bing re-crawls the index too.
    urls.insert(0, f"{base}/")
    return urls


def ping_recent_urls(
    vertical_name: str,
    *,
    since_hours: int = _DEFAULT_SINCE_HOURS,
    limit: int = _DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Ping IndexNow with the day's recent URLs. Returns (n_urls, status_code).

    Designed to be called from render_meta_files() once per vertical per
    cron tick. Fail-open: any error is logged and returned as status -1
    so the pipeline doesn't fail because Bing's API hiccupped."""
    try:
        urls = collect_recent_urls(
            vertical_name, since_hours=since_hours, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("indexnow: collect_recent_urls failed: %s", exc)
        return (0, -1)
    if not urls:
        return (0, 0)
    base = canonical_base_for(vertical_name)
    host = base.replace("https://", "").replace("http://", "").rstrip("/")
    try:
        key = get_or_create_key(vertical_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("indexnow: get_or_create_key failed: %s", exc)
        return (0, -1)
    status, body = submit_urls(host, key, urls, dry_run=dry_run)
    if status not in (0, 200, 202):
        logger.warning(
            "indexnow: %s -> %d (%s)", host, status, body[:200]
        )
    else:
        logger.info("indexnow: %s -> %d (%d urls)", host, status, len(urls))
    return (len(urls), status)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="indexnow")
    p.add_argument("vertical")
    p.add_argument(
        "--max", type=int, default=_DEFAULT_BATCH_SIZE,
        help=f"max URLs per ping (default {_DEFAULT_BATCH_SIZE})",
    )
    p.add_argument(
        "--since-hours", type=int, default=_DEFAULT_SINCE_HOURS,
        help=f"include articles published within last N hours (default {_DEFAULT_SINCE_HOURS})",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="print the payload instead of POSTing",
    )
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    n, status = ping_recent_urls(
        args.vertical,
        since_hours=args.since_hours,
        limit=args.max,
        dry_run=args.dry_run,
    )
    print(f"urls={n} status={status}")
    return 0 if status in (0, 200, 202) else 2


if __name__ == "__main__":
    sys.exit(main())
