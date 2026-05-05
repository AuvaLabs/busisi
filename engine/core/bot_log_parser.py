"""Caddy access-log parser → BotHit rows.

Reads the per-vertical Caddy JSON log (default: /var/log/caddy/<vertical>.log),
identifies AI/answer-engine + search-engine crawlers by User-Agent, and
persists each hit to ``bot_hits``. Idempotent: re-runs skip log lines whose
``ts`` is <= the most-recent recorded ``BotHit.ts`` for the vertical.

CLI:
  python -m engine.core.bot_log_parser <vertical> [--log /path/to/log] [--max N]

The pipeline cron wires this in after render so the same tick that
republishes the site captures the crawlers fetching it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select

from engine.core.config import SUBSCRIBER_EMAIL_PEPPER
from engine.core.db import BotHit, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


# Ordered most-specific to least-specific so e.g. "Perplexity-User" matches
# before a hypothetical broader "Perplexity" pattern. Match is case-insensitive
# substring against the raw User-Agent. The first hit wins; anything not
# matching is ignored (browsers, monitoring probes).
_BOT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("perplexity-user", "Perplexity-User"),
    ("perplexitybot", "PerplexityBot"),
    ("oai-searchbot", "OAI-SearchBot"),
    ("chatgpt-user", "ChatGPT-User"),
    ("gptbot", "GPTBot"),
    ("claude-web", "Claude-Web"),
    ("claudebot", "ClaudeBot"),
    ("anthropic-ai", "anthropic-ai"),
    ("google-extended", "Google-Extended"),
    ("googlebot", "Googlebot"),
    ("bingbot", "Bingbot"),
    ("duckduckbot", "DuckDuckBot"),
    ("applebot-extended", "Applebot-Extended"),
    ("applebot", "Applebot"),
    ("amazonbot", "Amazonbot"),
    ("cohere-ai", "cohere-ai"),
    ("ccbot", "CCBot"),
    ("bytespider", "Bytespider"),
)


def classify_ua(ua: str) -> str | None:
    """Return the canonical bot name for a User-Agent, or None if no match."""
    if not ua:
        return None
    lower = ua.lower()
    for needle, canonical in _BOT_PATTERNS:
        if needle in lower:
            return canonical
    return None


def hash_ip(ip: str) -> str:
    """SHA256(pepper || '|' || ip). Reuses SUBSCRIBER_EMAIL_PEPPER —
    bot IPs are public infrastructure so the goal is correlation grouping,
    not PII protection."""
    h = hashlib.sha256()
    h.update(SUBSCRIBER_EMAIL_PEPPER.encode("utf-8"))
    h.update(b"|")
    h.update((ip or "").encode("utf-8"))
    return h.hexdigest()


def _parse_ts(ts_field: object) -> datetime | None:
    """Caddy logs `ts` as a Unix epoch float by default. Tolerate strings too."""
    if isinstance(ts_field, (int, float)):
        return datetime.fromtimestamp(float(ts_field), tz=timezone.utc)
    if isinstance(ts_field, str):
        try:
            return datetime.fromtimestamp(float(ts_field), tz=timezone.utc)
        except ValueError:
            try:
                s = ts_field.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return None
    return None


def _extract_ua(headers: object) -> str:
    """Caddy logs request.headers as either a dict[str, list[str]] or absent."""
    if isinstance(headers, dict):
        v = headers.get("User-Agent") or headers.get("user-agent")
        if isinstance(v, list) and v:
            return str(v[0])
        if isinstance(v, str):
            return v
    return ""


def _extract_cf_ip(headers: object) -> str:
    """Cloudflare-proxied traffic carries the real client IP in
    ``CF-Connecting-IP``. When orange-cloud is on, request.remote_ip is a
    Cloudflare edge IP; the real bot IP lives in the header. For
    non-proxied direct requests (local dev, origin-IP probes), the header
    is absent and the caller falls back to the connection's remote_ip."""
    if isinstance(headers, dict):
        v = (
            headers.get("Cf-Connecting-Ip")
            or headers.get("CF-Connecting-IP")
            or headers.get("cf-connecting-ip")
        )
        if isinstance(v, list) and v:
            return str(v[0])
        if isinstance(v, str):
            return v
    return ""


def parse_lines(lines: Iterable[str]) -> Iterable[dict]:
    """Yield {ts, ua, bot_name, path, status, remote_ip} for matching lines.

    Lines that aren't valid JSON, lack a User-Agent, or don't match any bot
    pattern are skipped silently.
    """
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        ts = _parse_ts(entry.get("ts"))
        if ts is None:
            continue

        req = entry.get("request") or {}
        ua = _extract_ua(req.get("headers"))
        bot_name = classify_ua(ua)
        if bot_name is None:
            continue

        path = str(req.get("uri") or "")
        # Prefer CF-Connecting-IP — real client/bot IP behind Cloudflare
        # proxy. Fall back to the connection's remote_ip for direct-origin
        # requests (local dev, edge-IP probes).
        remote_ip = (
            _extract_cf_ip(req.get("headers"))
            or str(req.get("remote_ip") or req.get("client_ip") or "")
        )
        status = entry.get("status")
        try:
            status_int = int(status) if status is not None else 0
        except (TypeError, ValueError):
            status_int = 0

        yield {
            "ts": ts,
            "ua": ua,
            "bot_name": bot_name,
            "path": path,
            "status": status_int,
            "remote_ip": remote_ip,
        }


def ingest(
    vertical_name: str,
    *,
    log_path: Path | None = None,
    max_rows: int | None = None,
) -> int:
    """Read the Caddy log for the vertical and persist new BotHit rows.

    Returns the number of rows inserted.
    """
    Session = get_sessionmaker()
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"vertical not found: {vertical_name}")

        last_ts = session.execute(
            select(func.max(BotHit.ts)).where(BotHit.vertical_id == v.id)
        ).scalar_one_or_none()
        # SQLite (test backend) returns naive datetimes even for TIMESTAMPTZ
        # columns. Coerce so the comparison below stays in UTC.
        if last_ts is not None and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        path = log_path or Path(f"/var/log/caddy/{vertical_name}.log")
        if not path.exists():
            logger.warning("caddy log not found: %s", path)
            return 0

        inserted = 0
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for hit in parse_lines(fh):
                if last_ts is not None and hit["ts"] <= last_ts:
                    continue
                row = BotHit(
                    vertical_id=v.id,
                    ts=hit["ts"],
                    bot_name=hit["bot_name"],
                    ua=hit["ua"][:4096],
                    path=hit["path"][:4096],
                    status=hit["status"],
                    ip_hash=hash_ip(hit["remote_ip"]),
                )
                session.add(row)
                inserted += 1
                if max_rows is not None and inserted >= max_rows:
                    break
        session.commit()
        logger.info(
            "bot_log_parser: vertical=%s inserted=%d", vertical_name, inserted
        )
        return inserted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bot_log_parser")
    p.add_argument("vertical")
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="path to Caddy access log (default: /var/log/caddy/<vertical>.log)",
    )
    p.add_argument(
        "--max",
        type=int,
        default=None,
        help="stop after this many new rows (testing aid)",
    )
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        n = ingest(args.vertical, log_path=args.log, max_rows=args.max)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    print(f"inserted={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
