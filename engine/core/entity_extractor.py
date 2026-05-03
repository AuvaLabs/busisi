"""Grounded named-entity extractor.

For each article, ask the LLM to surface 0–8 named entities of types we
care about (lab, model, person, company, product, location). Results are
upserted into ``entities`` (one row per (vertical, type, slug)) and
linked from ``article_entities``.

Idempotency:
  * ``Article.entities_extracted_at`` is set on success — the backfill
    runner skips rows where it's non-null.
  * Per-call Redis cache (``llm_cache``) keyed by article body so a
    re-run on the same content is free.

Phase 14a ships extraction + persistence only. Phase 14b will pipe
entity overlap into the clusterer to cut Reddit-boilerplate noise.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy import select

from engine.core import llm_cache, llm_client
from engine.core.config import MAX_CONTENT_CHARS
from engine.core.db import (
    Article,
    ArticleEntity,
    Entity,
    Vertical,
    get_sessionmaker,
)
from engine.core.slug import make_slug

logger = logging.getLogger(__name__)


_ALLOWED_TYPES: frozenset[str] = frozenset(
    {"lab", "model", "person", "company", "product", "location"}
)


_SYSTEM_PROMPT = """You are a strict named-entity extractor for news articles.

RULES:
1. Extract ONLY entities explicitly named in the source text. Do NOT invent
   or infer organisations / people / models / products that are not stated.
2. Allowed types: lab, model, person, company, product, location.
   - lab: a research organisation (e.g. OpenAI, DeepMind, Anthropic, Meta AI).
   - model: a specific named AI model or system (e.g. GPT-4o, Claude Sonnet,
     Gemini 2.5 Pro). Generic terms like "AI" or "LLM" are NOT entities.
   - person: a specific named individual (e.g. Sam Altman, Lisa Su).
   - company: a non-research company (e.g. Microsoft, Stripe, Vanguard).
   - product: a specific named non-AI product (e.g. iPhone 16, Roth IRA).
   - location: a country, region, state, or city (e.g. Taiwan, California).
3. Return at most 8 entities, ranked by editorial salience (most central
   to the story first).
4. If nothing qualifies, return {"entities": []}.
5. Output strictly valid JSON: {"entities": [{"type": "...", "name": "..."}]}.
"""


def _build_user_prompt(title: str, body: str) -> str:
    return (
        f"HEADLINE: {title}\n\n"
        f"ARTICLE BODY:\n{body[:MAX_CONTENT_CHARS]}\n\n"
        'Return JSON: {"entities": [{"type": "...", "name": "..."}]}'
    )


_RE_NORMALIZE = re.compile(r"\s+")


def _normalize_name(name: str) -> str:
    return _RE_NORMALIZE.sub(" ", name.strip())


def _grounding_source(article: Article) -> str:
    if article.body and len(article.body.strip()) >= 200:
        return article.body
    parts = [article.title or "", article.summary or ""]
    return "\n\n".join(p for p in parts if p)


def extract_entities(article: Article) -> list[dict[str, str]]:
    """Run the LLM on one article. Returns a list of normalized
    ``{type, name, slug}`` dicts (empty if nothing qualifies)."""
    grounding = _grounding_source(article).strip()
    if len(grounding) < 80:
        return []

    cache_key = llm_cache.make_cache_key("entities", grounding)
    cached = llm_cache.get(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("entities"), list):
        return cached["entities"]

    user = _build_user_prompt(article.title, grounding)
    try:
        raw = llm_client.call_llm(
            user_content=user,
            system_prompt=_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            caller="entities",
            max_tokens=400,
        )
    except RuntimeError as exc:
        logger.warning(
            "entity-extractor call failed for %r: %s", article.title[:60], exc
        )
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "entity-extractor returned non-JSON for %r", article.title[:60]
        )
        return []

    raw_entities = parsed.get("entities", [])
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        etype = str(item.get("type", "")).strip().lower()
        name = _normalize_name(str(item.get("name", "")))
        if etype not in _ALLOWED_TYPES or not name:
            continue
        slug = make_slug(name)
        key = (etype, slug)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"type": etype, "name": name, "slug": slug})
        if len(cleaned) >= 8:
            break

    llm_cache.put(cache_key, {"entities": cleaned})
    return cleaned


def _upsert_entity(
    session, vertical_id: int, entity: dict[str, str], now: datetime
) -> Entity:
    row = (
        session.execute(
            select(Entity).where(
                Entity.vertical_id == vertical_id,
                Entity.type == entity["type"],
                Entity.slug == entity["slug"],
            )
        )
        .scalar_one_or_none()
    )
    if row is None:
        row = Entity(
            vertical_id=vertical_id,
            type=entity["type"],
            name=entity["name"],
            slug=entity["slug"],
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(row)
        session.flush()
    else:
        row.last_seen_at = now
        if entity["name"] and row.name != entity["name"]:
            row.name = entity["name"]
    return row


def persist_for_article(
    article_id: int, vertical_id: int, entities: list[dict[str, str]]
) -> int:
    """Upsert entity rows + link to ``article_id``. Returns # links written."""
    SessionLocal = get_sessionmaker()
    now = datetime.now(timezone.utc)
    written = 0
    with SessionLocal() as session:
        for ent in entities:
            row = _upsert_entity(session, vertical_id, ent, now)
            existing = session.execute(
                select(ArticleEntity).where(
                    ArticleEntity.article_id == article_id,
                    ArticleEntity.entity_id == row.id,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    ArticleEntity(article_id=article_id, entity_id=row.id)
                )
                written += 1
        article = session.get(Article, article_id)
        if article is not None:
            article.entities_extracted_at = now
        session.commit()
    return written


def enrich_pending(
    vertical: str,
    *,
    max_articles: int = 20,
    sleep_between: float = 1.0,
) -> dict[str, int]:
    """Backfill entity extraction over rows where ``entities_extracted_at IS NULL``."""
    SessionLocal = get_sessionmaker()
    counts = {
        "considered": 0,
        "extracted": 0,
        "skipped": 0,
        "failed": 0,
        "links": 0,
    }
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
                    Article.entities_extracted_at.is_(None),
                )
                .order_by(Article.fetched_at.asc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )
        v_id = v.id
        article_payloads = [(a.id, a) for a in rows]

    logger.info(
        "[%s] entity extraction: %d pending rows",
        vertical,
        len(article_payloads),
    )
    for aid, article in article_payloads:
        counts["considered"] += 1
        try:
            ents = extract_entities(article)
        except Exception as exc:
            logger.warning(
                "entity-extractor crashed on %r: %s", article.title[:60], exc
            )
            counts["failed"] += 1
            continue
        if not ents:
            persist_for_article(aid, v_id, [])
            counts["skipped"] += 1
        else:
            written = persist_for_article(aid, v_id, ents)
            counts["extracted"] += 1
            counts["links"] += written
        if sleep_between:
            time.sleep(sleep_between)
    logger.info("[%s] entity extraction done: %s", vertical, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.entity_extractor modelwatch [--max 50]``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract named entities per article"
    )
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch)")
    parser.add_argument("--max", type=int, default=20, dest="max_articles")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    counts = enrich_pending(
        args.vertical,
        max_articles=args.max_articles,
        sleep_between=args.sleep,
    )
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
