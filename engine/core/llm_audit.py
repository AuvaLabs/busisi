"""LLM audit recorder + daily-unit-cap guardrail (C1).

Bridges ``llm_client.call_llm`` to the Postgres ``llm_calls`` table (R2 schema)
so every API call leaves a footprint we can audit and roll up. Also enforces a
per-vertical daily concurrency-unit cap so a buggy validator loop (e.g. the
rewriter retrying a failing pass2_compose) cannot burn through the Featherless
Premium quota.

Two-call pattern from llm_client::

    units = llm_audit.units_for_model(model)
    if llm_audit.cap_exceeded(vertical_id, additional_units=units)[0]:
        raise RuntimeError("daily LLM unit cap exceeded for vertical")

    # ... make the API call ...

    llm_audit.record_call(
        caller=caller, model=model, vertical_id=vertical_id,
        story_id=story_id, article_id=article_id,
        input_tokens=..., output_tokens=..., cost_units=units, error=err
    )

Both calls are best-effort: on DB outage, recording fails silently and the
LLM call still goes through. The cap check returns (False, ...) on outage so
service is preserved (fail-open); the operator should monitor for the warning
line in logs.
"""
# ruff: noqa: PLR2004
# PLR2004: model-size thresholds (7, 15, 24, 34, 70, 72) are deliberate
# concurrency-unit boundaries from Featherless docs; documented in the
# units_for_model dispatch.

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from engine.core.db import LLMCall, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


# Premium-gated MoE/reasoning models — always 4 units regardless of active params.
_PREMIUM_4U_MODELS = (
    "deepseek-v3",
    "deepseek-r1",
    "kimi-k2",
    "llama-4-maverick",
    "glm-4.6",
)

_SIZE_RE = re.compile(r"-(\d+)b\b", re.IGNORECASE)


def units_for_model(model_id: str) -> int:
    """Return the Featherless concurrency-unit cost for ``model_id``.

    Heuristics, in order:

      1. Premium MoE / reasoning models → 4u
      2. Llama 4 Scout (17B active, MoE) → 2u
      3. Parameter-size suffix in the model name:
           - 7-15B → 1u
           - 24-34B → 2u
           - 70-72B → 4u
      4. Fallback: 2u (mid-tier safe default)
    """
    name = model_id.lower()
    if any(p in name for p in _PREMIUM_4U_MODELS):
        return 4
    if "llama-4-scout" in name:
        return 2
    m = _SIZE_RE.search(name)
    if m:
        size = int(m.group(1))
        if size <= 15:
            return 1
        if size <= 34:
            return 2
        return 4
    return 2


def cap_for_vertical(vertical: int | str | None) -> int:
    """Return the per-vertical daily unit cap from env. 0 = no cap."""
    if vertical is None:
        return 0
    name = vertical if isinstance(vertical, str) else _vertical_name(vertical)
    if not name:
        return 0
    raw = os.getenv(f"LLM_DAILY_UNIT_CAP__{name.lower()}")
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _vertical_name(vertical_id: int) -> str | None:
    Session = get_sessionmaker()
    try:
        with Session() as session:
            row = session.get(Vertical, vertical_id)
            return row.name if row else None
    except Exception as exc:
        logger.debug("llm_audit._vertical_name failed: %s", exc)
        return None


def units_used_today(vertical: int | str | None) -> int:
    """Sum of cost_units for today (UTC) for the given vertical."""
    if vertical is None:
        return 0
    Session = get_sessionmaker()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        with Session() as session:
            stmt = select(func.coalesce(func.sum(LLMCall.cost_units), 0)).where(
                LLMCall.created_at >= today_start
            )
            if isinstance(vertical, int):
                stmt = stmt.where(LLMCall.vertical_id == vertical)
            else:
                v = session.execute(
                    select(Vertical).where(Vertical.name == vertical)
                ).scalar_one_or_none()
                if v is None:
                    return 0
                stmt = stmt.where(LLMCall.vertical_id == v.id)
            return int(session.execute(stmt).scalar() or 0)
    except Exception as exc:
        logger.warning("llm_audit.units_used_today failed: %s", exc)
        return 0


def cap_exceeded(
    vertical: int | str | None,
    *,
    additional_units: int = 0,
) -> tuple[bool, int, int]:
    """Return ``(exceeded, used_today, cap)``. Fail-open on DB outage."""
    cap = cap_for_vertical(vertical)
    if cap == 0:
        return False, 0, 0
    used = units_used_today(vertical)
    exceeded = (used + additional_units) > cap
    return exceeded, used, cap


def record_call(
    *,
    caller: str,
    model: str,
    vertical_id: int | None = None,
    story_id: int | None = None,
    article_id: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_units: int | None = None,
    error: str | None = None,
) -> None:
    """Best-effort insert into ``llm_calls``. Swallows DB errors."""
    if cost_units is None:
        cost_units = units_for_model(model)
    Session = get_sessionmaker()
    try:
        with Session() as session:
            session.add(
                LLMCall(
                    caller=caller,
                    model=model,
                    vertical_id=vertical_id,
                    story_id=story_id,
                    article_id=article_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    cost_units=cost_units,
                    error=error,
                )
            )
            session.commit()
    except Exception as exc:
        logger.debug("llm_audit.record_call swallowed: %s", exc)


def extract_token_counts(api_response: dict[str, Any]) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from an OpenAI-compatible response."""
    if not isinstance(api_response, dict):
        return 0, 0
    usage = api_response.get("usage") or {}
    return (
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
    )
