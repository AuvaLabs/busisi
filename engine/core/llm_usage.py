"""LLM usage tracker — per-key, per-day, per-caller, per-vertical accounting.

Ported from ``modules/groq_usage.py`` in ThreatWatch (HEAD fffecca) with two
adaptations for grimoire:

1. Vendor-neutral name (`llm_usage` instead of `groq_usage`).
2. Adds a ``vertical`` dimension when the caller passes one (so we can split
   spend by Modelwatch vs Vested vs future verticals).

API keys are masked to ``<first-8-chars>…`` so a stolen usage file cannot be
used to reconstruct the real key. 90-day retention enforced on every write.

Storage lives at ``STATE_DIR/llm_usage.json``::

    {
      "daily": {
        "2026-05-02": {
          "total_calls": 1234,
          "total_prompt_tokens": 4000000,
          "total_completion_tokens": 800000,
          "keys": {"gsk_AbCd…": {"calls": 412, "prompt_tokens": 1300000,
                                  "completion_tokens": 260000}},
          "by_caller": {"classify": {"calls": 2200, "tokens": 1500000}},
          "by_vertical": {"modelwatch": {"calls": 800, "tokens": 1100000}}
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from engine.core.config import STATE_DIR

logger = logging.getLogger(__name__)

USAGE_FILE = STATE_DIR / "llm_usage.json"
_lock = threading.Lock()
_MAX_DAYS_RETAINED = 90


def _mask_key(api_key: str | None) -> str:
    if not api_key:
        return "unknown"
    return f"{api_key[:8]}…"


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _empty_day() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "keys": {},
        "by_caller": {},
        "by_vertical": {},
    }


def _load() -> dict[str, Any]:
    if not USAGE_FILE.exists():
        return {"daily": {}}
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"daily": {}}


def _save(data: dict[str, Any]) -> None:
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.debug("llm_usage write failed: %s", exc)


def _trim_old(data: dict[str, Any]) -> None:
    daily = data.get("daily", {})
    if len(daily) <= _MAX_DAYS_RETAINED:
        return
    keep = sorted(daily.keys())[-_MAX_DAYS_RETAINED:]
    data["daily"] = {k: daily[k] for k in keep}


def record_usage(
    api_key: str | None,
    response_data: dict[str, Any],
    *,
    caller: str | None = None,
    vertical: str | None = None,
) -> None:
    """Record token usage from an OpenAI-compatible response body."""
    usage = response_data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    total = int(usage.get("total_tokens", prompt + completion))

    masked = _mask_key(api_key)
    today = _today_key()

    with _lock:
        data = _load()
        day = data.setdefault("daily", {}).setdefault(today, _empty_day())
        day["total_calls"] = int(day.get("total_calls", 0)) + 1
        day["total_prompt_tokens"] = int(day.get("total_prompt_tokens", 0)) + prompt
        day["total_completion_tokens"] = (
            int(day.get("total_completion_tokens", 0)) + completion
        )
        key_entry = day.setdefault("keys", {}).setdefault(
            masked, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        )
        key_entry["calls"] += 1
        key_entry["prompt_tokens"] += prompt
        key_entry["completion_tokens"] += completion
        if caller:
            caller_entry = day.setdefault("by_caller", {}).setdefault(
                caller, {"calls": 0, "tokens": 0}
            )
            caller_entry["calls"] += 1
            caller_entry["tokens"] += total
        if vertical:
            v_entry = day.setdefault("by_vertical", {}).setdefault(
                vertical, {"calls": 0, "tokens": 0}
            )
            v_entry["calls"] += 1
            v_entry["tokens"] += total
        _trim_old(data)
        _save(data)


def get_today() -> dict[str, Any]:
    """Return today's bucket (empty if no calls yet)."""
    return _load().get("daily", {}).get(_today_key(), _empty_day())


def get_total_30d() -> dict[str, int]:
    """Aggregate total tokens / calls across the last 30 days."""
    data = _load().get("daily", {})
    days = sorted(data.keys())[-30:]
    out = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
    for d in days:
        bucket = data[d]
        out["calls"] += int(bucket.get("total_calls", 0))
        out["prompt_tokens"] += int(bucket.get("total_prompt_tokens", 0))
        out["completion_tokens"] += int(bucket.get("total_completion_tokens", 0))
    return out
