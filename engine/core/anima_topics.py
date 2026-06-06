"""Anima topic builder — cluster sourced stories into topic candidates.

In the Vested ⇄ Anima ecosystem, Vested's job is to supply FACTS + SOURCES;
the creative selection + scripting is Anima's. So this builder is deterministic
(no LLM): it groups recent §3-contract stories (from anima_enricher) by shared
entity within the finance lanes into evidence-backed topic candidates. Each
candidate carries a *fact pack* — every claim tied to its ``key_stat`` and
``primary_source_url`` — so Anima can fact-gate and storyboard it directly.

A "topic" here = a cluster of recent stories sharing a dominant entity, with a
title (the strongest member's headline), a lane, an aggregate momentum (demand)
score, and the sourced fact pack. Ranked by momentum.
"""

from __future__ import annotations

import re
from typing import Any


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or "topic"


def _topic_score(stories: list[dict[str, Any]]) -> float:
    """Aggregate demand: strongest member's momentum + small corroboration bonus."""
    if not stories:
        return 0.0
    mx = max(float(s.get("momentum") or 0.0) for s in stories)
    bonus = min(0.15, 0.05 * (len(stories) - 1))
    return round(min(1.0, mx + bonus), 3)


def _fact(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": s.get("headline", ""),
        "key_stat": s.get("key_stat"),
        "source_url": s.get("primary_source_url"),
        "story_url": s.get("url"),
        "lane": s.get("lane"),
    }


def _assemble(
    members: list[dict[str, Any]], *, theme_entity: str | None
) -> dict[str, Any]:
    lead = max(members, key=lambda s: float(s.get("momentum") or 0.0))
    lanes = [m.get("lane") for m in members if m.get("lane")]
    lane = max(set(lanes), key=lanes.count) if lanes else None

    entities: list[str] = []
    eseen: set[str] = set()
    for m in members:
        for e in m.get("entities") or []:
            if e not in eseen:
                eseen.add(e)
                entities.append(e)

    sources: list[str] = []
    sseen: set[str] = set()
    for m in members:
        u = m.get("primary_source_url")
        if u and u not in sseen:
            sseen.add(u)
            sources.append(u)

    published = [m.get("published_at") for m in members if m.get("published_at")]
    tid = "topic-" + (
        _slug(theme_entity) if theme_entity else f"story-{lead.get('id')}"
    )
    return {
        "id": tid,
        "title": lead.get("headline", ""),
        "hook": (lead.get("summary") or "")[:240],
        "lane": lane,
        "theme_entity": theme_entity,
        "evergreen": any(bool(m.get("evergreen")) for m in members),
        "momentum": _topic_score(members),
        "n_stories": len(members),
        "entities": entities,
        "facts": [_fact(m) for m in members],
        "sources": sources,
        "story_ids": [str(m.get("id")) for m in members],
        "updated_at": max(published) if published else None,
    }


def build_topics(
    stories: list[dict[str, Any]],
    *,
    min_cluster: int = 2,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Cluster §3 story contracts into ranked topic candidates.

    Greedy entity clustering: the entity shared by the most (unclaimed) stories
    forms a topic when it has ``>= min_cluster`` members; those stories are
    claimed; repeat on the remainder. Leftover stories that still carry a
    ``key_stat`` or ``primary_source_url`` become single-story topics so no
    sourced item is lost. Topics are ranked by aggregate momentum.
    """
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for s in stories:
        for e in s.get("entities") or []:
            by_entity.setdefault(e, []).append(s)

    used: set[str] = set()
    topics: list[dict[str, Any]] = []

    # Multi-story themed topics, largest cluster first (ties broken by name).
    for entity in sorted(by_entity, key=lambda e: (-len(by_entity[e]), e)):
        members = [s for s in by_entity[entity] if str(s.get("id")) not in used]
        if len(members) < min_cluster:
            continue
        for s in members:
            used.add(str(s.get("id")))
        topics.append(_assemble(members, theme_entity=entity))

    # Leftover singles that still have something sourced to anchor a video on.
    for s in stories:
        if str(s.get("id")) in used:
            continue
        if not s.get("key_stat") and not s.get("primary_source_url"):
            continue
        used.add(str(s.get("id")))
        topics.append(_assemble([s], theme_entity=None))

    topics.sort(key=lambda t: t["momentum"], reverse=True)
    return topics[:limit]
