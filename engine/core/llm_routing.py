"""Caller-aware LLM model routing.

R2 — replaces the single global ``LLM_MODEL`` env var with a caller→model map
so the pipeline can route cheap work (curator scoring, entity extraction,
classify) to a small model and reserve premium-tier reasoning models for the
multi-source rewriter's narrative composition pass.

The map is overridable via env vars at three levels of specificity:

  1. Per-vertical, per-caller:  ``LLM_MODEL__<vertical>__<caller>``
  2. Per-caller (any vertical): ``LLM_MODEL__<caller>``
  3. Global default:            ``LLM_MODEL``  (existing config.LLM_MODEL)

The defaults baked into ``_DEFAULT_REGISTRY`` target Featherless Premium tier
($25/mo, 4 concurrency units, 32K context cap):

  - 1u callers: Qwen 2.5 7B Instruct  (curator, classify, entity extract,
    Pass 0 article extract, why-this-matters caption)
  - 2u callers: Qwen 2.5 32B Instruct (Pass 1 cluster fact merge,
    summarize_orphan)
  - 4u callers: DeepSeek V3 / Llama 4 Maverick (Pass 2 narrative compose;
    DeepSeek for analytical/financial copy in Vested, Maverick for general
    byline in Embedding)

Concurrency math: Premium = 4 units total. Pass 2 (4u) serializes against
everything else — this is intentional, the rewriter's terminal step is the
bottleneck. At ~30-50 stories/day per vertical we have ample throughput.

Featherless model IDs follow HuggingFace repo paths
(e.g. ``Qwen/Qwen2.5-7B-Instruct``). All IDs in this registry are
overridable per-deployment without code changes.
"""

from __future__ import annotations

import logging
import os
from typing import Final

from engine.core.config import LLM_MODEL

logger = logging.getLogger(__name__)


# Caller IDs are lowercase, snake_case; stable identifiers used as the
# `caller` argument to llm_client.call_llm and as the dict key here.
Caller = str


_DEFAULT_REGISTRY: Final[dict[Caller, str]] = {
    # ── 1 unit — small workhorse ─────────────────────────────────────────
    "curator_score":        "Qwen/Qwen2.5-7B-Instruct",
    "classify":             "Qwen/Qwen2.5-7B-Instruct",
    "entity_extract":       "Qwen/Qwen2.5-7B-Instruct",
    "pass0_extract":        "Qwen/Qwen2.5-7B-Instruct",
    "why_this_matters":     "Qwen/Qwen2.5-7B-Instruct",
    "summarize":            "Qwen/Qwen2.5-7B-Instruct",   # legacy alias
    # ── 2 units — mid tier ───────────────────────────────────────────────
    "summarize_orphan":     "Qwen/Qwen2.5-32B-Instruct",
    "pass1_merge":          "Qwen/Qwen2.5-32B-Instruct",
    # ── 4 units — Premium-only, byline-grade prose ───────────────────────
    # Default Pass 2 — overridden per-vertical for tone (Vested → DeepSeek
    # for analytical copy; Embedding → Llama 4 Maverick for general byline).
    "pass2_compose":        "deepseek-ai/DeepSeek-V3",
}


# Per-vertical Pass 2 model overrides. The rewriter passes
# ``vertical=<name>`` to ``model_for()`` so we can pick a tone model.
_VERTICAL_OVERRIDES: Final[dict[str, dict[Caller, str]]] = {
    "embedding": {
        # General-tech byline voice. Maverick is a strong open-weights pick;
        # Featherless catalogs it Premium-tier.
        "pass2_compose": "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    },
    "vested": {
        # Analytical/financial-copy voice. DeepSeek V3's reasoning trace
        # produces tighter quantitative prose.
        "pass2_compose": "deepseek-ai/DeepSeek-V3",
    },
}


def _env_override(*keys: str) -> str | None:
    """Return the first non-empty env var value among the supplied keys."""
    for k in keys:
        v = os.getenv(k)
        if v and v.strip():
            return v.strip()
    return None


def model_for(caller: Caller, *, vertical: str | None = None) -> str:
    """Resolve ``caller`` → model id with three-level env override.

    Resolution order:

      1. ``LLM_MODEL__<vertical>__<caller>`` env var
      2. ``LLM_MODEL__<caller>`` env var
      3. ``_VERTICAL_OVERRIDES[vertical][caller]``
      4. ``_DEFAULT_REGISTRY[caller]``
      5. ``LLM_MODEL`` (legacy global default)

    Returns a model id suitable for the OpenAI-compatible
    ``/v1/chat/completions`` ``model`` field.
    """
    vlc = (vertical or "").strip().lower()
    keys: list[str] = []
    if vlc:
        keys.append(f"LLM_MODEL__{vlc}__{caller}")
    keys.append(f"LLM_MODEL__{caller}")
    override = _env_override(*keys)
    if override:
        return override
    if vlc and vlc in _VERTICAL_OVERRIDES and caller in _VERTICAL_OVERRIDES[vlc]:
        return _VERTICAL_OVERRIDES[vlc][caller]
    if caller in _DEFAULT_REGISTRY:
        return _DEFAULT_REGISTRY[caller]
    if LLM_MODEL:
        logger.debug(
            "llm_routing: unknown caller %r — falling back to LLM_MODEL", caller
        )
        return LLM_MODEL
    raise KeyError(
        f"llm_routing: no model registered for caller={caller!r} and "
        "LLM_MODEL is empty. Set LLM_MODEL in env or register the caller."
    )


def known_callers() -> list[Caller]:
    """Return the canonical caller list for documentation / introspection."""
    return sorted(_DEFAULT_REGISTRY)
