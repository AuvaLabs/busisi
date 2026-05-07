"""Pass 0 — per-article structured fact extractor (R4a).

Runs at scrape time (or as a backfill batch) and produces a small JSON
document per article. The output becomes the *primary input* to the
multi-source rewriter's Pass 1 (cluster fact merge), letting Pass 1 work
with bounded, structured input rather than raw bodies — critical because
Featherless Premium caps context at 32K, and 5+ raw bodies blow that.

Extract shape (stored in ``Article.structured_extract``)::

    {
      "lead_claim":  "<one-sentence summary of the central event>",
      "key_facts":   ["<short factual claim>", ...],   # 3-6 items
      "numerics":    [{"value": "<text as in body>",
                       "context": "<short context>"}, ...],
      "entities":    [{"name": "...", "type": "lab|person|model|product|org"}, ...],
      "quotes":      [{"text": "...", "speaker": "..."}, ...]   # 0-3 items
    }

Strict grounding: every value must derive from the source body. The
prompt enforces this; the model is instructed to omit fields it can't
ground rather than fabricate. The validator additionally checks that
every numeric value in ``numerics[].value`` parses to a number that
appears in the source body's numeric set.

Cache: Redis-backed via ``llm_cache``, keyed on
``sha256("pass0_extract:" + body[:MAX_CONTENT_CHARS])``. Re-running on
the same body is free.

Idempotency: extracts only rows where ``extract_version < EXTRACT_VERSION``.
Bumping the constant retroactively re-extracts.
"""
# ruff: noqa: PLR2004, PLR0911, PLC0415
# PLR2004: documented numeric thresholds (min body length 200) — kept inline
# for readability; documented in docstring above.
# PLR0911: validator has multiple early-return rejection paths by design.
# PLC0415: CLI argparse import lives in main() to keep module-level imports
# minimal; pre-existing pattern across engine.core.

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from engine.core import llm_cache, llm_client, llm_routing
from engine.core.config import MAX_CONTENT_CHARS
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


# Bump to force re-extraction on rows where Article.extract_version < this.
EXTRACT_VERSION = 1


_SYSTEM_PROMPT = """You are a strict news fact extractor. Your job: read a single article and produce a structured JSON extract.

RULES:
1. Every value MUST derive from the source text. Do not invent.
2. If a category has no grounded content, return an empty list. Do not guess.
3. Output strictly valid JSON with this exact shape:
   {
     "lead_claim": "<one-sentence summary of the central event>",
     "key_facts": ["<short factual claim>", ...],
     "numerics": [{"value": "<text as in body>", "context": "<short context>"}, ...],
     "entities": [{"name": "...", "type": "lab|person|model|product|org|regulator|company"}, ...],
     "quotes": [{"text": "...", "speaker": "..."}, ...]
   }
4. key_facts: 3-6 items, each one short factual claim.
5. numerics: every monetary, count, percent, or year mentioned. Verbatim.
6. quotes: 0-3 direct quotations from named speakers.
7. Do not include prose outside these JSON fields. No explanation.
"""


_NUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(\s*[kKmMbB])?\s*%?"
)


def _build_user_prompt(title: str, body: str) -> str:
    return (
        f"HEADLINE: {title}\n\n"
        f"ARTICLE BODY:\n{body[:MAX_CONTENT_CHARS]}\n\n"
        "Return JSON of the documented shape. Do not invent values."
    )


def _numeric_values(text: str) -> set[float]:
    out: set[float] = set()
    for raw, _suffix in _NUM_TOKEN_RE.findall(text):
        try:
            out.add(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _validate_extract(parsed: dict[str, Any], source_text: str) -> tuple[bool, str]:
    """Lightweight grounding check on the structured extract."""
    if not isinstance(parsed, dict):
        return False, "extract is not a JSON object"
    for key in ("lead_claim", "key_facts", "numerics", "entities", "quotes"):
        if key not in parsed:
            return False, f"missing required key: {key}"
    if not isinstance(parsed["lead_claim"], str) or not parsed["lead_claim"].strip():
        return False, "lead_claim must be a non-empty string"
    for list_key in ("key_facts", "numerics", "entities", "quotes"):
        if not isinstance(parsed[list_key], list):
            return False, f"{list_key} must be a list"

    source_values = _numeric_values(source_text)
    for item in parsed["numerics"]:
        if not isinstance(item, dict):
            return False, "numerics entry not an object"
        value_text = str(item.get("value", ""))
        # Pick out the numeric subtoken, ignore unit chars.
        for raw, _ in _NUM_TOKEN_RE.findall(value_text):
            try:
                v = float(raw.replace(",", ""))
            except ValueError:
                continue
            if not any(
                abs(v - s) <= max(0.01 * max(abs(v), abs(s)), 0.5)
                for s in source_values
            ):
                return False, f"ungrounded numeric: {value_text!r}"
    return True, ""


def extract_one(article: Article, *, vertical: str) -> dict[str, Any] | None:
    """Run Pass 0 on one article. Returns the extract dict or None on failure."""
    body = (article.body or "").strip()
    if len(body) < 200:
        # Too short for the rewriter to gain anything from a structured extract.
        return None

    cache_key = llm_cache.make_cache_key("pass0_extract", body)
    cached = llm_cache.get(cache_key)
    if cached is not None and isinstance(cached, dict):
        return {**cached, "_cached": True}

    user = _build_user_prompt(article.title, body)
    routed_model = llm_routing.model_for("pass0_extract", vertical=vertical)
    try:
        raw = llm_client.call_llm(
            user_content=user,
            system_prompt=_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            caller="pass0_extract",
            model=routed_model,
            max_tokens=1200,
            vertical_id=article.vertical_id,
            article_id=article.id,
        )
    except RuntimeError as exc:
        logger.warning("pass0_extract call failed for %r: %s", article.title[:60], exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("pass0_extract returned non-JSON for %r", article.title[:60])
        return None

    ok, reason = _validate_extract(parsed, body)
    if not ok:
        logger.warning(
            "pass0_extract grounding failed for %r: %s", article.title[:60], reason
        )
        return None

    llm_cache.put(cache_key, parsed)
    return {**parsed, "_cached": False}


def extract_pending(
    vertical: str,
    *,
    max_articles: int = 20,
    sleep_between: float = 0.5,
) -> dict[str, int]:
    """Find articles whose extract_version < EXTRACT_VERSION and run Pass 0."""
    Session = get_sessionmaker()
    counts = {"considered": 0, "updated": 0, "skipped": 0, "failed": 0, "cached": 0}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            logger.warning("vertical not found: %s", vertical)
            return counts

        rows = (
            session.execute(
                select(Article)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    Article.body.is_not(None),
                    Article.extract_version < EXTRACT_VERSION,
                )
                .order_by(Article.fetched_at.asc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )
        counts["considered"] = len(rows)
        logger.info("[%s] pass0_extract: %d candidates", vertical, len(rows))

        for article in rows:
            result = extract_one(article, vertical=vertical)
            if result is None:
                body_len = len((article.body or "").strip())
                counts["skipped" if body_len < 200 else "failed"] += 1
                continue
            cached = bool(result.pop("_cached", False))
            article.structured_extract = result
            article.extract_version = EXTRACT_VERSION
            article.extracted_at = datetime.now(UTC)
            session.commit()
            counts["updated"] += 1
            if cached:
                counts["cached"] += 1
            elif sleep_between:
                time.sleep(sleep_between)

    logger.info("[%s] pass0_extract done: %s", vertical, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.extractor <vertical> [--max 50] [--sleep 0.5]``"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Pass 0 structured extractor on pending articles"
    )
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(levelname)s %(name)s: %(message)s"
    )
    counts = extract_pending(args.vertical, max_articles=args.max, sleep_between=args.sleep)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
