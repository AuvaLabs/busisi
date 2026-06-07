"""Hybrid classifier: keyword-first, LLM escalation on low confidence.

Ported from ``modules/hybrid_classifier.py`` + ``modules/keyword_classifier.py``
in ThreatWatch (HEAD fffecca) with two grimoire-specific changes:

1. **Multi-label** — every article can carry several `(label, confidence)`
   pairs from a per-vertical taxonomy. ThreatWatch returns a single category.
2. **Per-vertical taxonomy** loaded from ``verticals/<name>/config.yaml``
   instead of hard-coded cybersecurity buckets. Each topic has an associated
   list of regex patterns (case-insensitive) that score keyword matches.

Escalation gate (preserved from TW): the LLM is only invoked when the
keyword classifier returns confidence < 70 OR matches an
``always_escalate`` topic. Per-run escalation budget caps token spend so a
noisy day cannot blow through the LLM free tier in a single pipeline tick.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

from engine.core import llm_cache, llm_client
from engine.core.config import MAX_CONTENT_CHARS

logger = logging.getLogger(__name__)


_AI_ESCALATION_CONFIDENCE = 70
_DEFAULT_ESCALATION_BUDGET = 20

_escalation_count_lock = threading.Lock()
_escalation_counts: dict[str, int] = {}


def reset_escalation_budget(vertical: str) -> None:
    """Reset the per-vertical escalation counter at the start of each run."""
    with _escalation_count_lock:
        _escalation_counts[vertical] = 0


def _bump_escalation(vertical: str, max_budget: int) -> bool:
    """Atomically check-and-increment the per-vertical escalation counter."""
    with _escalation_count_lock:
        current = _escalation_counts.get(vertical, 0)
        if current >= max_budget:
            return False
        _escalation_counts[vertical] = current + 1
        return True


def _keyword_classify(
    title: str,
    content: str | None,
    taxonomy: dict[str, list[str]],
    title_anchored: frozenset[str] | set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Score each topic by counting regex hits in title (3x) + content.

    ``title_anchored`` names broad/dual-use lanes (e.g. macro-economy) for which
    a body-only mention is NOT enough: a finance term appearing once in the body
    of an off-topic article (a social-media story that mentions "inflation")
    must not tag it macro. For those lanes the article's subject — its title —
    has to carry the term, or the label is dropped.
    """
    title_l = title.lower()
    weighted_text = " ".join([title_l] * 3)
    if content:
        weighted_text += " " + content.lower()[:MAX_CONTENT_CHARS]

    out: list[dict[str, Any]] = []
    for topic, patterns in taxonomy.items():
        hits = 0
        title_hit = False
        anchored = topic in title_anchored
        for pat in patterns:
            try:
                hits += len(re.findall(pat, weighted_text, flags=re.IGNORECASE))
                if anchored and not title_hit and re.search(
                    pat, title_l, flags=re.IGNORECASE
                ):
                    title_hit = True
            except re.error as exc:
                logger.debug("Invalid regex for topic %s: %s", topic, exc)
        if hits == 0:
            continue
        if anchored and not title_hit:
            continue  # body-only mention of a broad lane → not the subject
        confidence = min(90, 30 + hits * 12)
        out.append({"label": topic, "confidence": confidence})

    out.sort(key=lambda d: d["confidence"], reverse=True)
    return out


_LLM_SYSTEM_PROMPT = (
    "You are a strict content classifier. Read the headline and (if given) the "
    "article excerpt. Return JSON with shape "
    '{"labels": [{"label": <topic>, "confidence": 0-100}]}. '
    "Use ONLY topics from the provided taxonomy. Confidence reflects how "
    "directly the article is about that topic. Multi-label is allowed but "
    "each label requires at least 60 confidence. Never invent topics."
)


def _llm_escalate(
    title: str,
    content: str | None,
    taxonomy: dict[str, list[str]],
    *,
    vertical: str,
    caller: str,
) -> list[dict[str, Any]] | None:
    user = (
        f"Taxonomy (allowed topics): {sorted(taxonomy.keys())}\n\n"
        f"Headline: {title}\n"
    )
    if content:
        user += f"\nExcerpt:\n{content[:MAX_CONTENT_CHARS]}"

    cache_key = llm_cache.make_cache_key("classify", user)
    cached = llm_cache.get(cache_key)
    if cached is not None:
        return list(cached.get("labels", []))

    try:
        raw = llm_client.call_llm(
            user_content=user,
            system_prompt=_LLM_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            caller=caller,
            max_tokens=400,
        )
    except RuntimeError as exc:
        logger.warning("LLM escalation failed for %r: %s", title[:60], exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON for %r", title[:60])
        return None

    labels = parsed.get("labels") or []
    valid_topics = set(taxonomy.keys())
    cleaned = [
        {"label": item["label"], "confidence": int(item.get("confidence", 0))}
        for item in labels
        if isinstance(item, dict)
        and item.get("label") in valid_topics
        and int(item.get("confidence", 0)) >= 60
    ]
    llm_cache.put(cache_key, {"labels": cleaned})
    logger.info(
        "LLM-classified %r -> %d labels (vertical=%s)", title[:60], len(cleaned), vertical
    )
    return cleaned


def classify_article(
    title: str,
    content: str | None,
    taxonomy: dict[str, list[str]],
    *,
    vertical: str = "default",
    always_escalate: list[str] | None = None,
    escalation_budget: int = _DEFAULT_ESCALATION_BUDGET,
    title_anchored: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any]:
    """Classify an article using keyword-first, LLM-escalation hybrid."""
    keyword_labels = _keyword_classify(title, content, taxonomy, title_anchored)
    top_conf = max((label["confidence"] for label in keyword_labels), default=0)
    keyword_topics = {label["label"] for label in keyword_labels}

    must_escalate = bool(set(always_escalate or []).intersection(keyword_topics))
    should_escalate = (
        llm_client.is_available()
        and (top_conf < _AI_ESCALATION_CONFIDENCE or must_escalate)
        and _bump_escalation(vertical, escalation_budget)
    )

    if should_escalate:
        escalated = _llm_escalate(
            title, content, taxonomy, vertical=vertical, caller="classify"
        )
        if escalated is not None:
            return {
                "labels": escalated,
                "is_classified": bool(escalated),
                "_ai_enhanced": True,
                "_cached": False,
                "_keyword_labels": keyword_labels,
            }

    return {
        "labels": keyword_labels,
        "is_classified": bool(keyword_labels),
        "_ai_enhanced": False,
        "_cached": False,
    }
