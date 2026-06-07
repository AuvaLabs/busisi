"""Researcher tier — fetches supporting docs for tier=researcher articles.

Targets articles where the source body is too thin for the standard
summarizer to ground on (Reddit threads, arXiv-listing-only items,
press-release stubs, etc.). Returns a "bundle" of 3-5 supporting
documents that the rewriter (Phase 22f) will fold into a grounded
synthesis.

Sources:

  * **arXiv** (free, keyless) — search by title + extracted entities;
    retrieves 0-3 abstract-rich results. Particularly effective for
    modelwatch where the corpus skews toward AI/ML.
  * **Exa.ai** (semantic search, $5/M after free tier) — 0-3 results
    when ``EXA_API_KEY`` is configured. Falls back to arXiv-only when
    unset, so the researcher works out of the box and grows in
    capability when an operator wires the key.
  * **Wikipedia** (free, keyless, no quota) — 0-3 encyclopedic
    extracts. Especially useful for the "history, regulation, comparable
    cases, expert commentary" expansion the F2 prompt asks bundles for.
    Added 2026-05-23 to backfill bundle depth on verticals/articles
    where Exa's daily cap leaves rows under-researched.

All HTTP goes through the existing SSRF guard (``safe_http``) and a
soft timeout (``RESEARCH_QUERY_TIMEOUT``). Per-source results are
deduped by host+url-path and trimmed to ``RESEARCH_BUNDLE_SIZE``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from sqlalchemy import select

from engine.core.config import (
    ARXIV_ENABLED,
    ARXIV_ENDPOINT,
    EXA_API_KEY,
    EXA_DAILY_CAP,
    EXA_ENDPOINT,
    RESEARCH_BUNDLE_SIZE,
    RESEARCH_CACHE_TTL_DAYS,
    RESEARCH_MAX_PER_TICK,
    RESEARCH_QUERY_TIMEOUT,
    WIKIPEDIA_ENABLED,
    WIKIPEDIA_ENDPOINT,
    vertical_dir,
)
from engine.core.db import (
    Article,
    ArticleEntity,
    Entity,
    ResearchBundle,
    Vertical,
    get_sessionmaker,
)
from engine.core.llm_cache import _redis
from engine.core.safe_http import install_ssrf_guard

logger = logging.getLogger(__name__)


# ---- Cache + budget helpers (Phase 22h) ------------------------------------


def _cache_key(provider: str, query: str) -> str:
    h = hashlib.sha256(query.encode("utf-8", "replace")).hexdigest()
    return f"grimoire:researcher:cache:{provider}:{h}"


def _cache_get(provider: str, query: str) -> list[dict[str, Any]] | None:
    """Return cached results or None on miss / Redis hiccup. Fail-open."""
    try:
        client = _redis()
        if client is None:
            return None
        raw = client.get(_cache_key(provider, query))
    except Exception as exc:  # noqa: BLE001 — never block research on cache
        logger.debug("researcher cache get failed: %s", exc)
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return data


def _cache_put(
    provider: str, query: str, results: list[dict[str, Any]]
) -> None:
    """Persist results JSON with the configured TTL. Silent on errors."""
    try:
        client = _redis()
        if client is None:
            return
        ttl = max(int(RESEARCH_CACHE_TTL_DAYS), 0) * 86400
        if ttl <= 0:
            return
        client.set(
            _cache_key(provider, query),
            json.dumps(results),
            ex=ttl,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("researcher cache put failed: %s", exc)


def _exa_daily_counter_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"grimoire:researcher:exa:{today}"


def _exa_under_daily_cap() -> bool:
    """True = OK to spend an Exa call. False = cap reached, skip silently.
    Fails open on Redis hiccup so a broken cache doesn't kill research."""
    cap = max(int(EXA_DAILY_CAP), 0)
    if cap <= 0:
        return True  # cap disabled
    try:
        client = _redis()
        if client is None:
            return True
        n = client.incr(_exa_daily_counter_key())
        if int(n) == 1:
            # First call of the day — auto-expire after 48h so stale
            # day-keys don't accumulate even if cleanup misses.
            client.expire(_exa_daily_counter_key(), 172800)
        return int(n) <= cap
    except Exception as exc:  # noqa: BLE001
        logger.debug("researcher exa cap check failed: %s", exc)
        return True


# ---- Query expansion -------------------------------------------------------


def _entities_for_article(session, article_id: int) -> list[Entity]:
    return list(
        session.execute(
            select(Entity)
            .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
            .where(ArticleEntity.article_id == article_id)
            .order_by(Entity.type, Entity.name)
        )
        .scalars()
        .all()
    )


def _load_research_opts(vertical_name: str) -> dict[str, Any]:
    """Read the ``research:`` block from ``verticals/<v>/config.yaml``.

    Supports ``category`` (e.g. "news") and ``include_domains`` (a per-vertical
    allowlist biasing Exa toward authoritative sources — for Vested, finance +
    fiscal-research domains like pgpf.org). Missing → {} (no bias). Per-vertical
    so Embedding's Exa stays AI/ML-relevant.
    """
    try:
        path = vertical_dir(vertical_name) / "config.yaml"
    except ValueError:
        return {}
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read research config %s: %s", path, exc)
        return {}
    block = data.get("research") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else {}


def expand_queries(article: Article, entities: list[Entity]) -> list[str]:
    """Build up to 3 search queries for one article.

    Strategy:
      1. Title verbatim — the most direct query.
      2. Top entity + title-noun-stub — context-anchored.
      3. Top two entities concatenated — entity-overlap retrieval.

    De-duped, capped at 3, all stripped to ≤ 200 chars.
    """
    title = (article.title or "").strip()
    queries: list[str] = []
    if title:
        queries.append(title[:200])
    if entities:
        e1 = entities[0]
        if title:
            queries.append(f"{e1.name} {title[:150]}".strip()[:200])
        else:
            queries.append(e1.name[:200])
        if len(entities) >= 2:
            queries.append(f"{e1.name} {entities[1].name}"[:200])
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key in seen or not q:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 3:
            break
    return out


# ---- Source clients --------------------------------------------------------


def _search_arxiv_uncached(
    query: str, *, max_results: int = 3
) -> list[dict[str, Any]]:
    """Hit the arXiv Atom API. No key, no rate-limit issues at our volume."""
    if not ARXIV_ENABLED or not query:
        return []
    params = {
        "search_query": f'all:"{query}"',
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        resp = requests.get(
            ARXIV_ENDPOINT,
            params=params,
            timeout=RESEARCH_QUERY_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("arxiv search failed for %r: %s", query[:40], exc)
        return []
    if resp.status_code != 200:
        logger.warning(
            "arxiv non-200 for %r: %s", query[:40], resp.status_code
        )
        return []

    parsed = feedparser.parse(resp.text)
    out: list[dict[str, Any]] = []
    for entry in parsed.entries[:max_results]:
        url = entry.get("link") or entry.get("id") or ""
        if not url:
            continue
        out.append(
            {
                "url": url,
                "title": (entry.get("title") or "").strip(),
                "text": (entry.get("summary") or "").strip(),
                "host": "arxiv.org",
            }
        )
    return out


def _search_exa_uncached(
    query: str,
    *,
    max_results: int = 3,
    category: str | None = None,
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Hit Exa.ai /search (current API). Returns [] if EXA_API_KEY is unset.

    Current API (per docs.exa.ai/reference/search-api-guide-for-coding-agents):
    auth via ``x-api-key``; ``type="auto"``; content via ``contents.highlights``
    (token-efficient excerpts — the right mode for our bundle pipeline). The
    legacy ``Authorization: Bearer`` + ``useAutoprompt`` + ``contents.text`` of
    the prior build are deprecated.
    """
    if not EXA_API_KEY or not query:
        return []
    headers = {
        "x-api-key": EXA_API_KEY,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "query": query,
        "type": "auto",
        "numResults": max_results,
        "contents": {"highlights": True},
    }
    if category:
        payload["category"] = category
    if include_domains:
        payload["includeDomains"] = list(include_domains)
    try:
        resp = requests.post(
            EXA_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=RESEARCH_QUERY_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("exa search failed for %r: %s", query[:40], exc)
        return []
    if resp.status_code != 200:
        logger.warning(
            "exa non-200 for %r: %s body=%s",
            query[:40],
            resp.status_code,
            resp.text[:200],
        )
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    out: list[dict[str, Any]] = []
    for item in (data.get("results") or [])[:max_results]:
        url = item.get("url") or ""
        if not url:
            continue
        host = urlparse(url).netloc.removeprefix("www.").lower()
        # `highlights` is a list of query-relevant excerpts (our requested mode).
        hl = item.get("highlights")
        if isinstance(hl, list) and hl:
            text = " … ".join(h for h in hl if h)
        else:
            text = item.get("text") or item.get("summary") or item.get("snippet") or ""
        out.append(
            {
                "url": url,
                "title": (item.get("title") or "").strip(),
                "text": text[:4000],
                "host": host,
            }
        )
    return out


def _search_wikipedia_uncached(
    query: str, *, max_results: int = 3
) -> list[dict[str, Any]]:
    """Hit the Wikipedia MediaWiki API. Free, no key, no quota.

    Uses ``generator=search`` + ``prop=extracts`` so titles + intro extracts
    arrive in a single round-trip. Returns at most ``max_results`` entries
    with the same dict shape as the arXiv / Exa helpers.
    """
    if not WIKIPEDIA_ENABLED or not query:
        return []
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query[:300],
        "gsrlimit": max_results,
        "gsrnamespace": 0,
        "prop": "extracts|info",
        "exintro": 1,
        "explaintext": 1,
        "exlimit": max_results,
        "inprop": "url",
        "utf8": 1,
    }
    try:
        resp = requests.get(
            WIKIPEDIA_ENDPOINT,
            params=params,
            headers={"User-Agent": "grimoire-researcher/1.0 (+https://embedding.report)"},
            timeout=RESEARCH_QUERY_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("wikipedia search failed for %r: %s", query[:40], exc)
        return []
    if resp.status_code != 200:
        logger.warning(
            "wikipedia non-200 for %r: %s", query[:40], resp.status_code
        )
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    pages = ((data.get("query") or {}).get("pages") or {})
    # Wikipedia returns a dict keyed by page id; preserve search rank via
    # the `index` field MediaWiki includes for generator=search.
    ordered = sorted(
        pages.values(), key=lambda p: p.get("index", 1_000_000)
    )
    out: list[dict[str, Any]] = []
    for page in ordered[:max_results]:
        url = page.get("fullurl") or ""
        extract = (page.get("extract") or "").strip()
        if not url or not extract:
            continue
        out.append(
            {
                "url": url,
                "title": (page.get("title") or "").strip(),
                "text": extract[:4000],
                "host": "en.wikipedia.org",
            }
        )
    return out


# Public cached wrappers — every external caller of search_arxiv /
# search_exa / search_wikipedia goes through these so the cache + budget
# cap apply uniformly. Signatures preserved for backward compatibility.

def search_arxiv(query: str, *, max_results: int = 3) -> list[dict[str, Any]]:
    cached = _cache_get("arxiv", query)
    if cached is not None:
        return cached[:max_results]
    results = _search_arxiv_uncached(query, max_results=max_results)
    _cache_put("arxiv", query, results)
    return results


_exa_cap_warned = False  # log "cap reached" once per process


def search_exa(
    query: str,
    *,
    max_results: int = 3,
    category: str | None = None,
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    # Domains/category vary the result set, so fold them into the cache key.
    ckey = query
    if include_domains:
        ckey = f"{query}|dom:{','.join(sorted(include_domains))}"
    if category:
        ckey = f"{ckey}|cat:{category}"
    cached = _cache_get("exa", ckey)
    if cached is not None:
        return cached[:max_results]
    if not _exa_under_daily_cap():
        global _exa_cap_warned
        if not _exa_cap_warned:
            logger.warning(
                "exa daily cap (%d) reached — falling back to arXiv-only "
                "until UTC midnight",
                EXA_DAILY_CAP,
            )
            _exa_cap_warned = True
        return []
    results = _search_exa_uncached(
        query,
        max_results=max_results,
        category=category,
        include_domains=include_domains,
    )
    _cache_put("exa", ckey, results)
    return results


def search_wikipedia(query: str, *, max_results: int = 3) -> list[dict[str, Any]]:
    cached = _cache_get("wikipedia", query)
    if cached is not None:
        return cached[:max_results]
    results = _search_wikipedia_uncached(query, max_results=max_results)
    _cache_put("wikipedia", query, results)
    return results


# ---- Bundle assembly + persistence -----------------------------------------


def _hash_excerpt(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _dedup_and_rank(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-dup by URL host+path; preserve insertion order. arXiv first, then
    Exa (so the academic anchor leads the bundle when both fire)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for doc in docs:
        url = doc.get("url", "")
        if not url:
            continue
        parsed = urlparse(url)
        key = parsed.netloc.removeprefix("www.").lower() + parsed.path.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out[:RESEARCH_BUNDLE_SIZE]


def fetch_supporting_docs(
    article: Article,
    entities: list[Entity],
    *,
    exa_category: str | None = None,
    exa_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    queries = expand_queries(article, entities)
    if not queries:
        return []
    docs: list[dict[str, Any]] = []
    # arXiv max_results 3 → 5/query is free (no daily cap, no key required)
    # and pushes embedding-vertical articles into the deeper-bundle regime
    # where F2 reliably produces 220+ word grounded outputs. Exa stays at
    # its module default (3/query) because EXA_DAILY_CAP is the binding cost.
    # Wikipedia (added 2026-05-23) provides keyless, quota-free encyclopedic
    # context — particularly useful for vested (companies/regulators) and
    # for embedding articles when Exa is exhausted.
    for q in queries:
        docs.extend(search_arxiv(q, max_results=5))
        docs.extend(
            search_exa(q, category=exa_category, include_domains=exa_domains)
        )
        docs.extend(search_wikipedia(q))
        if len(_dedup_and_rank(docs)) >= RESEARCH_BUNDLE_SIZE:
            break
    return _dedup_and_rank(docs)


def persist_bundle(article_id: int, docs: list[dict[str, Any]]) -> int:
    """Write ResearchBundle rows + set Article.researched_at."""
    SessionLocal = get_sessionmaker()
    now = datetime.now(timezone.utc)
    written = 0
    with SessionLocal() as session:
        # Wipe prior bundle for this article so re-runs replace cleanly.
        session.query(ResearchBundle).filter(
            ResearchBundle.article_id == article_id
        ).delete()
        for ord_, doc in enumerate(docs):
            excerpt = (doc.get("text") or "")[:4000]
            session.add(
                ResearchBundle(
                    article_id=article_id,
                    source_url=doc["url"],
                    host=doc["host"],
                    fetched_at=now,
                    sha256=_hash_excerpt(excerpt),
                    excerpt=excerpt,
                    ord=ord_,
                )
            )
            written += 1
        article = session.get(Article, article_id)
        if article is not None:
            article.researched_at = now
        session.commit()
    return written


def research_pending(
    vertical: str, *, max_articles: int | None = None
) -> dict[str, int]:
    """Run the researcher over tier=researcher rows whose researched_at IS NULL."""
    install_ssrf_guard()
    cap = max_articles if max_articles is not None else RESEARCH_MAX_PER_TICK
    opts = _load_research_opts(vertical)
    exa_category = opts.get("category") or None
    exa_domains = opts.get("include_domains") or None
    SessionLocal = get_sessionmaker()
    counts = {"considered": 0, "researched": 0, "empty": 0, "failed": 0}
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            return counts
        rows = (
            session.execute(
                select(Article)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    # F1 (2026-05-10) — also fetch supporting docs for top-quality
                    # `standard` tier articles so the orphan rewriter has
                    # research-bundle context for every non-skip article. Was
                    # previously researcher-only (gray zone).
                    Article.curator_tier.in_(("standard", "researcher")),
                    Article.researched_at.is_(None),
                )
                .order_by(Article.fetched_at.asc())
                .limit(cap)
            )
            .scalars()
            .all()
        )
        payloads = []
        for a in rows:
            ents = _entities_for_article(session, a.id)
            payloads.append((a, ents))

    for article, entities in payloads:
        counts["considered"] += 1
        try:
            docs = fetch_supporting_docs(
                article, entities,
                exa_category=exa_category, exa_domains=exa_domains,
            )
        except Exception as exc:
            logger.warning(
                "researcher crashed on %r: %s", article.title[:60], exc
            )
            counts["failed"] += 1
            continue
        if not docs:
            persist_bundle(article.id, [])  # marks researched_at; no rows
            counts["empty"] += 1
            continue
        persist_bundle(article.id, docs)
        counts["researched"] += 1

    logger.info("[%s] researcher: %s", vertical, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.researcher modelwatch [--max 5]``"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch supporting docs for tier=researcher articles"
    )
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=None, dest="max_articles")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    counts = research_pending(args.vertical, max_articles=args.max_articles)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
