"""Multi-source rewriter — Pass 1 (merge) + Pass 2 (compose).

R4b — the byline-grade replacement for the single-source summarizer when a
Story has been formed by the clusterer. The rewriter takes a cluster of
related articles, each carrying a Pass 0 ``structured_extract``, and produces
a single original news report with inline ``[N]`` citations and a strict
``StorySource`` table mapping each ``[N]`` to its agency.

Pipeline::

    Story.state == 'ready'
        ↓
    pass1_merge(story_id)               ── Qwen 2.5 32B (2u)
        Returns: {canonical_events, contradictions, timeline, headline_seed}
        ↓
    pass2_compose(story_id, pass1, ...) ── DeepSeek V3 / Llama 4 Maverick (4u)
        Returns: {lead, body, why_this_matters}
        ↓
    validate_narrative(...)
        Enforces I1-I4 from docs/REWRITER_BUILD_LOG.md (R0 plan).
        ↓
    Persist Story.narrative + StorySource[] + StoryRevision row.
    Story.state ← 'published'.

Hard invariants (validator rejects narrative if any fail):

  I1. ≥1 cited source has agency_class ∈ {A, B, C, D, E}.
  I2. Every ``[N]`` reference in narrative resolves to a ``citations`` entry.
  I3. No ``citations`` entry has agency_class ∈ {F, G}.
  I4. Every numeric value in narrative appears in ≥1 cited source's body.

Cost — Pass 1 cache key is sorted Pass-0 sha256 list; Pass 2 keys on Pass 1
output sha256 + tone source id. Re-running on the same cluster is free.
"""
# ruff: noqa: PLR2004, PLR0911, PLC0415
# PLR2004: documented numeric thresholds (min cluster size 2, word_count
# bounds 150-600) — kept inline; thresholds explained in docstring.
# PLR0911: validate_narrative has multiple early-return rejection paths by design.
# PLC0415: CLI argparse import lives in main(); pre-existing engine.core pattern.

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from engine.core import llm_cache, llm_client, llm_routing
from engine.core.curator import _load_agency_class_map
from engine.core.db import (
    Article,
    ResearchBundle,
    Story,
    StoryArticle,
    StoryRevision,
    StorySource,
    Vertical,
    get_sessionmaker,
)

logger = logging.getLogger(__name__)


REWRITER_VERSION = 1

_NUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(\s*[kKmMbB])?\s*%?"
)
_CITATION_RE = re.compile(r"\[(\d+)\]")
_BANNED_PHRASES = (
    "game-changer",
    "experts say",
    "could revolutionize",
    "many believe",
    "industry insiders",
    "sources close to",
)


# ---- Pass 1 — cluster fact merge ------------------------------------------


_PASS1_SYSTEM = """You merge multiple per-article fact extracts into a single canonical fact graph.

INPUT: a list of per-source extracts. Each extract has:
  source_idx, source_url, agency_class, lead_claim, key_facts, numerics, entities, quotes

OUTPUT JSON:
{
  "canonical_events": [
    {"claim": "...", "supporting_source_idxs": [0,2], "is_numeric": false}
  ],
  "contradictions": [
    {"claim_a": "...", "source_idxs_a": [0], "claim_b": "...", "source_idxs_b": [1]}
  ],
  "timeline": [
    {"when": "<ISO date or empty>", "what": "...", "source_idxs": [0]}
  ],
  "headline_seed": "<short factual headline derived from the cluster>"
}

RULES:
  1. canonical_events: dedupe across sources. If two sources state the same fact, ONE event with both source_idxs.
  2. Each event must trace back to >=1 source_idx. Do not invent.
  3. contradictions: only when sources disagree on a same-subject claim. Otherwise empty list.
  4. headline_seed: declarative, neutral, factual. No question marks, no hype.
  5. Output strict JSON only. No prose.
"""


def _pass1_user_prompt(extracts: list[dict[str, Any]]) -> str:
    return (
        "Per-source extracts:\n"
        + json.dumps(extracts, indent=2)
        + "\n\nReturn the merged fact graph as JSON of the documented shape."
    )


def _members_with_extracts(session, story_id: int) -> list[dict[str, Any]]:
    """Return cluster member articles with their Pass 0 extracts attached."""
    rows = (
        session.execute(
            select(Article, StoryArticle)
            .join(StoryArticle, StoryArticle.article_id == Article.id)
            .where(StoryArticle.story_id == story_id)
            .order_by(Article.published_at.asc())
        )
        .all()
    )
    members: list[dict[str, Any]] = []
    for article, _link in rows:
        if article.structured_extract is None:
            continue
        # `host` = article link host (used for citation display + StorySource).
        # `feed_host` = feed URL host (used for agency_class lookup, since the
        # agency_class map indexes by feed URL — not article URL — and these
        # often differ, e.g. arxiv.org vs export.arxiv.org).
        link_host = urlparse(article.link).netloc.removeprefix("www.").lower()
        feed_host = (
            urlparse(article.source).netloc.removeprefix("www.").lower()
            if article.source
            else link_host
        )
        members.append(
            {
                "source_idx": len(members),
                "article_id": article.id,
                "source_url": article.link,
                "host": link_host,
                "feed_host": feed_host,
                "agency_class": "?",  # filled by caller
                "title": article.title,
                "body": (article.body or "")[:3000],  # tone reference
                **(article.structured_extract or {}),
            }
        )
    return members


def pass1_merge(
    members: list[dict[str, Any]],
    *,
    vertical: str,
    vertical_id: int | None = None,
    story_id: int | None = None,
) -> dict[str, Any] | None:
    """Merge per-source extracts into a canonical fact graph."""
    if len(members) < 2:
        return None

    payload = [
        {
            "source_idx": m["source_idx"],
            "source_url": m["source_url"],
            "agency_class": m.get("agency_class", "?"),
            "lead_claim": m.get("lead_claim", ""),
            "key_facts": m.get("key_facts", []),
            "numerics": m.get("numerics", []),
            "entities": m.get("entities", []),
            "quotes": m.get("quotes", []),
        }
        for m in members
    ]
    cache_key = llm_cache.make_cache_key(
        "pass1_merge", json.dumps(payload, sort_keys=True)
    )
    cached = llm_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    try:
        raw = llm_client.call_llm(
            user_content=_pass1_user_prompt(payload),
            system_prompt=_PASS1_SYSTEM,
            response_format={"type": "json_object"},
            caller="pass1_merge",
            model=llm_routing.model_for("pass1_merge", vertical=vertical),
            max_tokens=2500,
            vertical_id=vertical_id,
            story_id=story_id,
        )
    except RuntimeError as exc:
        logger.warning("pass1_merge failed: %s", exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("pass1_merge returned non-JSON")
        return None
    if not isinstance(parsed, dict) or "canonical_events" not in parsed:
        return None
    llm_cache.put(cache_key, parsed)
    return parsed


# ---- Pass 2 — narrative composition ---------------------------------------


_PASS2_SYSTEM = """You are a senior wire-service editor. Compose an original news report from a structured fact graph and a tone reference.

INPUT JSON:
  pass1: canonical fact graph
  sources: list of {n, host, agency_class, source_url}  -- n is the [N] you use inline
  tone_excerpt: a representative source body for stylistic anchoring

OUTPUT JSON:
{
  "lead": "<inverted-pyramid first paragraph, 30-50 words>",
  "body": "<remaining paragraphs, total 200-450 words including lead, with inline [N] citations>",
  "why_this_matters": "<1-2 sentence editorial caption>"
}

RULES:
  1. NEVER invent facts. Every claim must trace to pass1.canonical_events
     and at least one of those events' supporting_source_idxs.
  2. Every numeric / quote / quote-attribution must have an inline [N] citation
     pointing to a source where that fact appears.
  3. When sources disagree, attribute explicitly: "Reuters[1] reported X, while
     Bloomberg[2] said Y."
  4. NEVER use these phrases: "game-changer", "experts say", "could revolutionize",
     "many believe", "industry insiders", "sources close to".
  5. Tone: declarative, neutral, byline-grade. Short sentences. No hype.
  6. Use only [N] tokens that resolve to entries in `sources`.
  7. Output strict JSON only. No commentary outside the three fields.
"""


def _pass2_user_prompt(
    pass1: dict[str, Any],
    sources: list[dict[str, Any]],
    tone_excerpt: str,
) -> str:
    return (
        "pass1:\n"
        + json.dumps(pass1, indent=2)
        + "\n\nsources:\n"
        + json.dumps(sources, indent=2)
        + "\n\ntone_excerpt:\n"
        + tone_excerpt[:6000]
        + "\n\nReturn the composed narrative as JSON."
    )


def pass2_compose(
    pass1: dict[str, Any],
    sources: list[dict[str, Any]],
    tone_excerpt: str,
    *,
    vertical: str,
    vertical_id: int | None = None,
    story_id: int | None = None,
) -> dict[str, Any] | None:
    """Compose the byline-grade narrative."""
    cache_seed = json.dumps({"pass1": pass1, "sources": sources}, sort_keys=True)
    cache_key = llm_cache.make_cache_key("pass2_compose", cache_seed)
    cached = llm_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    try:
        raw = llm_client.call_llm(
            user_content=_pass2_user_prompt(pass1, sources, tone_excerpt),
            system_prompt=_PASS2_SYSTEM,
            response_format={"type": "json_object"},
            caller="pass2_compose",
            model=llm_routing.model_for("pass2_compose", vertical=vertical),
            max_tokens=1500,
            vertical_id=vertical_id,
            story_id=story_id,
        )
    except RuntimeError as exc:
        logger.warning("pass2_compose failed: %s", exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("pass2_compose returned non-JSON")
        return None
    if not isinstance(parsed, dict):
        return None
    for key in ("lead", "body", "why_this_matters"):
        if key not in parsed or not isinstance(parsed[key], str):
            logger.warning("pass2_compose missing field: %s", key)
            return None
    llm_cache.put(cache_key, parsed)
    return parsed


# ---- Validator ------------------------------------------------------------


def _numeric_values(text: str) -> set[float]:
    out: set[float] = set()
    for raw, _suffix in _NUM_TOKEN_RE.findall(text):
        try:
            out.add(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def validate_narrative(
    narrative: dict[str, Any],
    sources: list[dict[str, Any]],
    bodies: list[str],
) -> tuple[bool, str]:
    """Enforce I1-I4 invariants. Returns (ok, reason)."""
    full_text = (narrative["lead"] + "\n\n" + narrative["body"]).strip()
    word_count = len(full_text.split())
    if word_count < 150 or word_count > 600:
        return False, f"word_count out of range: {word_count}"

    lower = full_text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False, f"banned phrase: {phrase!r}"

    cited_ns = {int(m) for m in _CITATION_RE.findall(full_text)}
    source_ns = {int(s["n"]) for s in sources}
    missing = cited_ns - source_ns
    if missing:
        return False, f"unresolved [N] citations: {sorted(missing)}"

    primary_eligible = {"A", "B", "C", "D", "E"}
    if not any(s["agency_class"] in primary_eligible for s in sources):
        return False, "no primary-eligible (A-E) source in citation list"
    for s in sources:
        if s["agency_class"] in {"F", "G"}:
            return False, f"Class {s['agency_class']} cannot be primary citation"

    body_pool = "\n".join(bodies)
    source_values = _numeric_values(body_pool)
    # Strip [N] citation markers before numeric extraction so attribution
    # tokens don't get counted as ungrounded factual claims.
    narr_for_numerics = _CITATION_RE.sub("", full_text)
    narr_values = _numeric_values(narr_for_numerics)
    leaked = sorted(
        v
        for v in narr_values
        if not any(
            abs(v - s) <= max(0.01 * max(abs(v), abs(s)), 0.5) for s in source_values
        )
    )
    if leaked:
        return False, f"narrative cites numbers not in source bodies: {leaked[:3]}"

    return True, ""


# ---- Persistence ----------------------------------------------------------


def _persist_rewrite(
    session,
    story: Story,
    narrative: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    model_used: str,
    cost_units: int,
    reason: str = "initial",
) -> int:
    """Atomic update of Story + insert StorySource[] + StoryRevision row."""
    next_version = (story.narrative_version or 0) + 1
    full_text = narrative["lead"] + "\n\n" + narrative["body"]
    word_count = len(full_text.split())

    story.narrative = full_text
    story.why_this_matters = narrative.get("why_this_matters")
    story.narrative_version = next_version
    story.narrative_updated_at = datetime.now(UTC)
    story.narrative_model = model_used
    story.narrative_word_count = word_count
    story.state = "published"

    # Replace the StorySource rows for this story (if any) with the new set.
    session.query(StorySource).filter(StorySource.story_id == story.id).delete()
    for s in sources:
        session.add(
            StorySource(
                story_id=story.id,
                source_url=s["source_url"],
                host=s["host"],
                agency_class=s["agency_class"],
                cited_as_n=int(s["n"]),
                article_id=s.get("article_id"),
            )
        )

    session.add(
        StoryRevision(
            story_id=story.id,
            version=next_version,
            narrative=full_text,
            why_this_matters=narrative.get("why_this_matters"),
            sources_json=sources,
            model_used=model_used,
            cost_units=cost_units,
            reason=reason,
            word_count=word_count,
        )
    )
    return next_version


# ---- Orchestration --------------------------------------------------------


def rewrite_story(
    story_id: int, *, vertical: str
) -> dict[str, Any] | None:
    """Run Pass 1 → Pass 2 → validate → persist for one Story."""
    Session = get_sessionmaker()
    agency_map = _load_agency_class_map(vertical)
    with Session() as session:
        story = session.get(Story, story_id)
        if story is None:
            return None

        members = _members_with_extracts(session, story_id)
        if len(members) < 2:
            logger.info(
                "story %d skipped: <2 members with structured_extract", story_id
            )
            return None

        for m in members:
            # Try feed_host first (canonical source-list match), fall back to
            # article-link host. This covers feeds whose feed URL host differs
            # from the article URL host (arxiv.org vs export.arxiv.org).
            m["agency_class"] = (
                agency_map.get(m.get("feed_host", ""), None)
                or agency_map.get(m["host"], "?")
            )

        primary_count = sum(
            1 for m in members if m["agency_class"] in {"A", "B", "C", "D", "E"}
        )
        if primary_count == 0:
            logger.info(
                "story %d skipped: no Class A-E members (got: %s)",
                story_id,
                [m["agency_class"] for m in members],
            )
            return None

        pass1 = pass1_merge(
            members,
            vertical=vertical,
            vertical_id=story.vertical_id,
            story_id=story.id,
        )
        if pass1 is None:
            return None

        sources = []
        for i, m in enumerate(members, start=1):
            sources.append(
                {
                    "n": i,
                    "host": m["host"],
                    "agency_class": m["agency_class"],
                    "source_url": m["source_url"],
                    "article_id": m["article_id"],
                }
            )
        tone_member = max(
            (m for m in members if m["agency_class"] in {"A", "B", "C"}),
            default=members[0],
            key=lambda m: len(m.get("body", "")),
        )

        narrative = pass2_compose(
            pass1,
            sources,
            tone_member.get("body", ""),
            vertical=vertical,
            vertical_id=story.vertical_id,
            story_id=story.id,
        )
        if narrative is None:
            return None

        bodies = [m.get("body", "") for m in members]
        ok, reason = validate_narrative(narrative, sources, bodies)
        if not ok:
            logger.warning(
                "story %d rewrite failed validation: %s", story_id, reason
            )
            return None

        model_used = llm_routing.model_for("pass2_compose", vertical=vertical)
        next_version = _persist_rewrite(
            session,
            story,
            narrative,
            sources,
            model_used=model_used,
            cost_units=6,  # pass1 (2u) + pass2 (4u)
            reason="initial" if (story.narrative_version or 0) == 0 else "new_source",
        )
        session.commit()
        return {
            "story_id": story_id,
            "version": next_version,
            "word_count": story.narrative_word_count,
            "n_sources": len(sources),
        }


def rewrite_pending(
    vertical: str, *, max_stories: int = 10
) -> dict[str, int]:
    """Find Stories needing a rewrite; rewrite each."""
    Session = get_sessionmaker()
    counts = {"considered": 0, "written": 0, "skipped": 0, "failed": 0}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            return counts
        ids = (
            session.execute(
                select(Story.id)
                .where(
                    Story.vertical_id == v.id,
                    Story.state.in_(("draft", "ready", "revising")),
                )
                .order_by(Story.primary_published_at.desc())
                .limit(max_stories)
            )
            .scalars()
            .all()
        )
    counts["considered"] = len(ids)
    for sid in ids:
        result = rewrite_story(sid, vertical=vertical)
        if result is None:
            counts["skipped"] += 1
        else:
            counts["written"] += 1
    logger.info("[%s] rewrite_pending: %s", vertical, counts)
    return counts


# ---- F2 (2026-05-10) — Orphan rewriter (single-source enriched rewrite) ----
#
# For the 84% of articles that aren't part of a multi-source cluster, compose
# a 200-450 word researched narrative using:
#   - the primary article body + Pass 0 structured_extract  (cited as [1])
#   - the article's research_bundle entries from Exa/ArXiv   (cited as [2..N])
#
# Every numeric/quote claim must trace to either the primary or a bundle
# excerpt. Class F primaries (commentary) are rejected upstream by the tier
# filter (curator routes them to skip), but the validator double-checks.
# Articles in a published cluster (Story.narrative IS NOT NULL) are skipped —
# the cluster-level rewrite is canonical.


_PASS_ORPHAN_SYSTEM = """You are a senior wire-service editor. Compose an original news report enriched with research-bundle context.

INPUT JSON:
  primary: the article's structured fact extract (lead_claim, key_facts, numerics, entities, quotes)
  primary_body: the original article body (use for tone + grounding)
  research_bundle: list of supporting docs from web/scholar search [{n, url, host, excerpt}]
  sources: list of {n, host, agency_class, source_url, kind} where kind is "primary" or "research"

OUTPUT JSON (one of two shapes):

  Shape A — full narrative:
  {
    "lead": "<inverted-pyramid first paragraph>",
    "body": "<remaining paragraphs with inline [N] citations>",
    "why_this_matters": "<1-2 sentence editorial caption>"
  }

  Shape B — insufficient material (use when primary + bundles cannot honestly sustain 220+ grounded words):
  {"insufficient": true, "reason": "<short explanation>"}

RULES:
  1. LENGTH IS A HARD REQUIREMENT. The combined lead + body MUST total 220-500 words.
     Counts under 220 will be rejected. The honest path to length is the
     research_bundle: weave at least 3 distinct bundle excerpts into the body to
     add context (history, regulation, comparable cases, expert commentary) the
     primary doesn't carry on its own. NEVER pad the primary's claims with
     filler — extend with grounded bundle material or return Shape B.
  2. The lead is the first paragraph, 30-50 words, inverted-pyramid.
  3. NEVER invent facts. Every claim must trace to either the primary body or a research_bundle excerpt.
  4. The PRIMARY source is [1] — every factual claim from the primary cites [1].
  5. Research-bundle entries are [2..N] — use them to (a) confirm primary facts independently
     OR (b) add context the primary doesn't include (history, regulation, alternative angles).
  6. Every numeric / quote / quote-attribution must have an inline [N] citation pointing
     to the source where that fact appears. Quote numerics verbatim from the source —
     do NOT paraphrase ("six months" when the source says "180 days", or "20 percent" when
     the source says "one-fifth"). If unsure of the exact form, omit the number.
  7. NEVER use these phrases: "game-changer", "experts say", "could revolutionize",
     "many believe", "industry insiders", "sources close to".
  8. Tone: declarative, neutral, byline-grade. Short sentences. No hype.
  9. Use only [N] tokens that resolve to entries in `sources`.
  10. Output strict JSON only. No commentary outside the schema.
"""


def _pass_orphan_user_prompt(
    primary_extract: dict[str, Any],
    primary_body: str,
    bundles: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    return (
        "primary:\n"
        + json.dumps(primary_extract, indent=2)
        + "\n\nresearch_bundle:\n"
        + json.dumps(bundles, indent=2)
        + "\n\nsources:\n"
        + json.dumps(sources, indent=2)
        + "\n\nprimary_body:\n"
        + primary_body[:6000]
        + "\n\nReturn the composed narrative as JSON."
    )


def pass_orphan_compose(
    primary_extract: dict[str, Any],
    primary_body: str,
    bundles: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    *,
    vertical: str,
    vertical_id: int | None = None,
    article_id: int | None = None,
) -> dict[str, Any] | None:
    """Compose the byline-grade single-source narrative."""
    cache_seed = json.dumps(
        {"primary": primary_extract, "bundles": bundles, "sources": sources},
        sort_keys=True,
    )
    # Cache-key version is bumped when the prompt contract changes so old
    # cached narratives (composed under a prior prompt) are not served back.
    # v3 (2026-05-21) — explicit "weave 3+ bundle excerpts" mandate;
    # deepened bundle inputs (12 × 2500 chars) and max_tokens 3000.
    cache_key = llm_cache.make_cache_key("rewrite_single_v3", cache_seed)
    cached = llm_cache.get(cache_key)
    if isinstance(cached, dict):
        # Honor the insufficient escape on cache hits too — otherwise a
        # cached Shape-B response gets returned as a narrative and crashes
        # the validator on narrative["lead"].
        if cached.get("insufficient") is True:
            return None
        # Reject malformed cached entries (defense in depth — should never
        # happen given the put-time check, but a corrupt cache entry would
        # otherwise crash the validator).
        if all(
            isinstance(cached.get(k), str)
            for k in ("lead", "body", "why_this_matters")
        ):
            return cached
    try:
        raw = llm_client.call_llm(
            user_content=_pass_orphan_user_prompt(
                primary_extract, primary_body, bundles, sources
            ),
            system_prompt=_PASS_ORPHAN_SYSTEM,
            response_format={"type": "json_object"},
            caller="rewrite_single",
            model=llm_routing.model_for("rewrite_single", vertical=vertical),
            max_tokens=3000,
            vertical_id=vertical_id,
            article_id=article_id,
        )
    except RuntimeError as exc:
        logger.warning("rewrite_single failed: %s", exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("rewrite_single returned non-JSON")
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("insufficient") is True:
        logger.info(
            "rewrite_single declined as insufficient: %s",
            parsed.get("reason", "<no reason>"),
        )
        llm_cache.put(cache_key, parsed)
        return None
    for key in ("lead", "body", "why_this_matters"):
        if key not in parsed or not isinstance(parsed[key], str):
            logger.warning("rewrite_single missing field: %s", key)
            return None
    llm_cache.put(cache_key, parsed)
    return parsed


def validate_orphan_narrative(
    narrative: dict[str, Any],
    sources: list[dict[str, Any]],
    bodies: list[str],
) -> tuple[bool, str]:
    """Validator for orphan rewrites.

    Differs from ``validate_narrative`` (cluster path) in two ways:
      1. Sources include a single primary [1] (must be Class A-E) plus
         research-bundle entries [2..N] which carry no agency_class
         requirement (Exa results are diverse).
      2. The "≥1 primary-eligible (A-E) source" rule applies only to the
         primary source [1]; bundle entries are accepted as supporting cites.
    """
    full_text = (narrative["lead"] + "\n\n" + narrative["body"]).strip()
    word_count = len(full_text.split())
    if word_count < 150 or word_count > 600:
        return False, f"word_count out of range: {word_count}"

    lower = full_text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False, f"banned phrase: {phrase!r}"

    cited_ns = {int(m) for m in _CITATION_RE.findall(full_text)}
    source_ns = {int(s["n"]) for s in sources}
    missing = cited_ns - source_ns
    if missing:
        return False, f"unresolved [N] citations: {sorted(missing)}"

    primary = next((s for s in sources if s.get("kind") == "primary"), None)
    if primary is None:
        return False, "no primary source in sources list"
    if primary.get("agency_class") in {"F", "G"}:
        return False, f"primary is Class {primary['agency_class']} — not eligible"
    if primary.get("agency_class") not in {"A", "B", "C", "D", "E"}:
        return False, f"primary agency_class={primary.get('agency_class')!r} not A-E"

    body_pool = "\n".join(bodies)
    source_values = _numeric_values(body_pool)
    narr_for_numerics = _CITATION_RE.sub("", full_text)
    narr_values = _numeric_values(narr_for_numerics)
    leaked = sorted(
        v for v in narr_values
        if not any(
            abs(v - s) <= max(0.01 * max(abs(v), abs(s)), 0.5) for s in source_values
        )
    )
    if leaked:
        return False, f"narrative cites numbers not in source bodies: {leaked[:3]}"

    return True, ""


def _persist_orphan_rewrite(
    session,
    article: Article,
    narrative: dict[str, Any],
    *,
    model_used: str,
) -> None:
    """Overwrite Article.summary with the orphan rewrite. Cluster-wins
    elsewhere — this only fires for orphan articles."""
    full_text = narrative["lead"] + "\n\n" + narrative["body"]
    article.summary = full_text
    article.summary_source = "rewrite_single"
    article.why_this_matters = narrative.get("why_this_matters")


def rewrite_orphan(
    article_id: int, *, vertical: str
) -> dict[str, Any] | None:
    """Run the orphan rewriter for one article.

    Skips when:
      - Article is in a published cluster (cluster-wins precedence)
      - Article has no structured_extract (Pass 0 not yet run)
      - Article body too thin (< 200 chars)
      - Primary source agency_class is F/G (not eligible — caught by tier
        gate too, double-checked here)
      - Validator rejects the composed narrative
    """
    Session = get_sessionmaker()
    agency_map = _load_agency_class_map(vertical)
    with Session() as session:
        article = session.get(Article, article_id)
        if article is None:
            return None
        if article.curator_tier not in ("standard", "researcher"):
            return None
        if not article.structured_extract:
            return None
        body = (article.body or "").strip()
        if len(body) < 200:
            return None
        # Cluster-wins precedence: skip if part of a published Story.
        link = session.execute(
            select(StoryArticle).where(StoryArticle.article_id == article.id)
        ).scalar_one_or_none()
        if link is not None:
            parent = session.get(Story, link.story_id)
            if parent is not None and parent.narrative:
                logger.info(
                    "orphan rewrite skipped art %d: in published Story %d",
                    article.id,
                    parent.id,
                )
                return None
        # Resolve agency class from feed_host (matches cluster-rewriter logic).
        feed_host = (
            urlparse(article.source).netloc.removeprefix("www.").lower()
            if article.source
            else urlparse(article.link).netloc.removeprefix("www.").lower()
        )
        link_host = urlparse(article.link).netloc.removeprefix("www.").lower()
        primary_class = agency_map.get(feed_host) or agency_map.get(link_host) or "?"
        if primary_class in {"F", "?", "G"}:
            logger.info(
                "orphan rewrite skipped art %d: primary class=%s not eligible",
                article.id,
                primary_class,
            )
            return None

        # Pull research-bundle context. Honest expansion lever: more grounded
        # source material → model produces proportionally longer narrative.
        # 12 bundles × 2500 chars ≈ 30k chars of context; well within the
        # premium-tier context budget after primary_body[:6000].
        bundle_rows = (
            session.execute(
                select(ResearchBundle)
                .where(ResearchBundle.article_id == article.id)
                .order_by(ResearchBundle.ord.asc())
                .limit(12)
            )
            .scalars()
            .all()
        )
        # Hard gate (2026-05-21) — articles with 0 bundles can't honestly
        # produce a "based on research" rewrite — only the primary body to
        # draw on, which would invite padding. Skipping at 0 saves the call.
        # 1-bundle articles still get attempted: validator (150-600w +
        # numeric grounding) enforces quality from there.
        if len(bundle_rows) < 1:
            logger.info(
                "orphan rewrite skipped art %d: no research bundles — nothing to extend from",
                article.id,
            )
            return None
        bundles = [
            {
                "n": i + 2,  # primary is [1]; bundles start at [2]
                "url": b.source_url,
                "host": b.host,
                "excerpt": (b.excerpt or "")[:2500],
            }
            for i, b in enumerate(bundle_rows)
        ]

        sources = [
            {
                "n": 1,
                "host": link_host,
                "agency_class": primary_class,
                "source_url": article.link,
                "kind": "primary",
            }
        ] + [
            {
                "n": b["n"],
                "host": b["host"],
                "agency_class": "?",
                "source_url": b["url"],
                "kind": "research",
            }
            for b in bundles
        ]

        narrative = pass_orphan_compose(
            primary_extract=article.structured_extract,
            primary_body=body,
            bundles=bundles,
            sources=sources,
            vertical=vertical,
            vertical_id=article.vertical_id,
            article_id=article.id,
        )
        if narrative is None:
            return None

        # Validator — primary body + bundle excerpts make up the grounding pool.
        bodies_for_validator = [body] + [b["excerpt"] for b in bundles]
        ok, reason = validate_orphan_narrative(narrative, sources, bodies_for_validator)
        if not ok:
            logger.warning(
                "orphan rewrite art %d failed validation: %s", article.id, reason
            )
            return None

        model_used = llm_routing.model_for("rewrite_single", vertical=vertical)
        _persist_orphan_rewrite(session, article, narrative, model_used=model_used)
        session.commit()
        return {
            "article_id": article.id,
            "word_count": len(article.summary.split()),
            "n_sources": len(sources),
            "model": model_used,
        }


def rewrite_orphan_pending(
    vertical: str,
    *,
    max_articles: int = 20,
    sleep_between: float = 0.5,
) -> dict[str, int]:
    """Find orphan articles needing enriched-rewrite; rewrite each.

    Selection criteria (oldest-extracted first):
      - curator_tier IN ('standard', 'researcher')
      - structured_extract present
      - summary_source != 'rewrite_single' (idempotent — already rewritten)
      - body length >= 200 chars
    """
    import time

    Session = get_sessionmaker()
    counts = {"considered": 0, "written": 0, "skipped": 0, "failed": 0, "cached": 0}
    with Session() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical)
        ).scalar_one_or_none()
        if v is None:
            return counts
        ids = (
            session.execute(
                select(Article.id)
                .where(
                    Article.vertical_id == v.id,
                    Article.deleted_at.is_(None),
                    Article.curator_tier.in_(("standard", "researcher")),
                    Article.structured_extract.is_not(None),
                    Article.summary_source != "rewrite_single",
                    Article.body.is_not(None),
                )
                .order_by(Article.extracted_at.asc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )
        counts["considered"] = len(ids)

    for aid in ids:
        result = rewrite_orphan(aid, vertical=vertical)
        if result is None:
            counts["skipped"] += 1
        else:
            counts["written"] += 1
            if sleep_between:
                time.sleep(sleep_between)
    logger.info("[%s] rewrite_orphan_pending: %s", vertical, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.research_writer <vertical> [--max 10]``"""
    import argparse

    parser = argparse.ArgumentParser(description="Run the multi-source rewriter")
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=10, dest="max_stories")
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="Run the F2 orphan (single-source enriched) rewriter instead",
    )
    parser.add_argument(
        "--orphan-max",
        type=int,
        default=20,
        dest="orphan_max",
        help="Cap on orphan articles rewritten per call",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.orphans:
        counts = rewrite_orphan_pending(args.vertical, max_articles=args.orphan_max)
    else:
        counts = rewrite_pending(args.vertical, max_stories=args.max_stories)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
