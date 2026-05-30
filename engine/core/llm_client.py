"""Shared LLM client with multi-key rotation, 429 failover, and circuit breaker.

Ported from ``modules/llm_client.py`` in ThreatWatch (HEAD fffecca) with two
adaptations for grimoire:

1. **Round-robin index lives in Redis** (``llm:key_index:<provider>``) so the
   pipeline container, the renderer container, and any cron-driven batch
   share a single rotation counter. ThreatWatch persists the index in a
   file because it runs as one process; grimoire is multi-process.
2. **Vendor-neutral default** (Groq) — same as ThreatWatch but the base URL
   and model are env-driven so we can swap providers without code changes.

Critical lesson preserved verbatim: **no urllib3 retry layer here**. A 429 or
503 with a long ``Retry-After`` header (Groq load-shedding) makes urllib3's
retry adapter sleep the full duration *per* retry. We rotate keys instead.

The circuit breaker is process-local (3 consecutive failures trip; reset at
pipeline-run start) — it caps the blast radius of a single upstream outage
without becoming a permanent kill switch.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import requests

from engine.core.config import (
    LLM_API_KEY,
    LLM_API_KEYS,
    LLM_BACKOFF_BASE,
    LLM_BACKOFF_CAP,
    LLM_BASE_URL,
    LLM_CIRCUIT_THRESHOLD,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT,
)

logger = logging.getLogger(__name__)

_KEY_INDEX_REDIS_KEY = f"llm:key_index:{LLM_PROVIDER}"

# Process-local circuit breaker.
_consecutive_failures = 0
_circuit_tripped = False


# ---- Circuit breaker ----


def _record_success() -> None:
    global _consecutive_failures, _circuit_tripped
    _consecutive_failures = 0
    _circuit_tripped = False


def _record_failure() -> None:
    global _consecutive_failures, _circuit_tripped
    _consecutive_failures += 1
    if _consecutive_failures >= LLM_CIRCUIT_THRESHOLD:
        _circuit_tripped = True


def _circuit_open() -> bool:
    return _circuit_tripped


def reset_circuit() -> None:
    """Reset the circuit breaker. Call at the start of each pipeline run."""
    global _consecutive_failures, _circuit_tripped
    _consecutive_failures = 0
    _circuit_tripped = False


def _parse_retry_after(resp: "requests.Response") -> float | None:
    """Parse a Retry-After header (integer seconds) into a float.

    Only the integer-seconds form is honored; an HTTP-date form returns None
    and the caller falls back to exponential backoff. The value is *advisory* —
    the caller caps it at LLM_BACKOFF_CAP so a load-shedding provider can't make
    us sleep for minutes (the urllib3 lesson from the module docstring).
    """
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


# ---- Key rotation (Redis-backed, with deterministic fallback) ----


def _redis_client() -> Any | None:
    try:
        from redis import Redis

        from engine.core.config import REDIS_URL

        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for LLM key index: %s", exc)
        return None


def _next_api_key() -> str:
    """Return the next API key using round-robin rotation."""
    # Single-key configs (most common): use the first (and only) key in the
    # list. Falling back to LLM_API_KEY here would return empty when only the
    # plural LLM_API_KEYS env var is set, causing a 401 at the upstream.
    if len(LLM_API_KEYS) == 1:
        return LLM_API_KEYS[0]
    if len(LLM_API_KEYS) == 0:
        return LLM_API_KEY
    client = _redis_client()
    if client is not None:
        try:
            idx = int(client.incr(_KEY_INDEX_REDIS_KEY))
            return LLM_API_KEYS[(idx - 1) % len(LLM_API_KEYS)]
        except Exception as exc:
            logger.warning("Redis key-index incr failed, falling back: %s", exc)
    return LLM_API_KEYS[os.getpid() % len(LLM_API_KEYS)]


def _advance_key() -> None:
    """Bump the rotation index by one (called on rate-limit)."""
    if len(LLM_API_KEYS) <= 1:
        return
    client = _redis_client()
    if client is not None:
        try:
            client.incr(_KEY_INDEX_REDIS_KEY)
        except Exception as exc:
            logger.debug("Redis key-index advance failed: %s", exc)


# ---- HTTP layer (no urllib3 retry) ----


def _get_http_session() -> requests.Session:
    """Return a fresh session with no Retry adapter."""
    return requests.Session()


def _response_format_unsupported(resp: requests.Response) -> bool:
    """Detect a 400 whose body indicates `response_format` isn't supported."""
    if resp.status_code != 400:
        return False
    try:
        body = (resp.text or "").lower()
    except Exception:
        return False
    return "response_format" in body


# ---- Public API ----


def call_llm(
    user_content: str,
    system_prompt: str,
    *,
    max_tokens: int = 2000,
    response_format: dict[str, Any] | None = None,
    caller: str | None = None,
    model: str | None = None,
    vertical_id: int | None = None,
    story_id: int | None = None,
    article_id: int | None = None,
) -> str:
    """Call the LLM API with key failover.

    C1 — when ``vertical_id`` is supplied, the daily concurrency-unit cap
    (env: ``LLM_DAILY_UNIT_CAP__<vertical>``) is enforced and every call
    leaves an LLMCall audit row. Existing callers that omit ``vertical_id``
    bypass the audit (backward-compatible).
    """
    if _circuit_open():
        raise RuntimeError(
            f"LLM circuit breaker open: >= {LLM_CIRCUIT_THRESHOLD} consecutive failures"
        )

    resolved_model = model or LLM_MODEL
    if vertical_id is not None:
        from engine.core import llm_audit

        units = llm_audit.units_for_model(resolved_model)
        exceeded, used, cap = llm_audit.cap_exceeded(
            vertical_id, additional_units=units
        )
        if exceeded:
            raise RuntimeError(
                f"daily LLM unit cap exceeded for vertical_id={vertical_id}: "
                f"used={used}, cap={cap}, this_call={units}"
            )

    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    base_payload: dict[str, Any] = {
        "model": model or LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if response_format is not None:
        base_payload["response_format"] = response_format

    attempts = min(len(LLM_API_KEYS), 3) if len(LLM_API_KEYS) > 1 else 1
    last_error: str | None = None

    # Outer bounded-retry loop. The inner loop rotates across keys; when EVERY
    # key is exhausted on a retryable status (429 / 5xx / timeout / connection)
    # we sleep with capped exponential backoff and try the whole set again.
    # With a single key, key-rotation has nothing to rotate to, so a transient
    # 429 used to become an instant hard failure — this is what recovers it.
    # A non-429 HTTPError still propagates immediately (not retried).
    for retry in range(LLM_MAX_RETRIES + 1):
        retry_after_hint: float | None = None

        for attempt in range(attempts):
            api_key = _next_api_key()
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = dict(base_payload)
            allow_response_format_fallback = response_format is not None

            while True:
                try:
                    session = _get_http_session()
                    resp = session.post(
                        url, json=payload, headers=headers, timeout=LLM_TIMEOUT
                    )

                    if resp.status_code == 429:
                        logger.warning(
                            "Key %d rate-limited (429), trying next.", attempt + 1
                        )
                        retry_after_hint = _parse_retry_after(resp) or retry_after_hint
                        _advance_key()
                        last_error = f"429 on key {attempt + 1}"
                        break
                    if resp.status_code in (500, 502, 503, 504):
                        logger.warning(
                            "Key %d got %d from upstream, trying next.",
                            attempt + 1,
                            resp.status_code,
                        )
                        retry_after_hint = _parse_retry_after(resp) or retry_after_hint
                        last_error = f"{resp.status_code} on key {attempt + 1}"
                        break
                    if allow_response_format_fallback and _response_format_unsupported(resp):
                        logger.warning(
                            "LLM provider rejected response_format on key %d; retrying without.",
                            attempt + 1,
                        )
                        payload = {k: v for k, v in payload.items() if k != "response_format"}
                        allow_response_format_fallback = False
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    _record_success()

                    try:
                        from engine.core.llm_usage import record_usage

                        record_usage(api_key, data, caller=caller)
                    except Exception as exc:
                        logger.debug("llm_usage record failed: %s", exc)

                    # C1 — Postgres audit row for cost rollups + daily cap.
                    if vertical_id is not None:
                        try:
                            from engine.core import llm_audit

                            in_tok, out_tok = llm_audit.extract_token_counts(data)
                            llm_audit.record_call(
                                caller=caller or "unknown",
                                model=resolved_model,
                                vertical_id=vertical_id,
                                story_id=story_id,
                                article_id=article_id,
                                input_tokens=in_tok,
                                output_tokens=out_tok,
                            )
                        except Exception as exc:
                            logger.debug("llm_audit.record_call failed: %s", exc)

                    content = data["choices"][0]["message"]["content"]
                    return str(content).strip()

                except requests.exceptions.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 429:
                        logger.warning("Key %d rate-limited, trying next.", attempt + 1)
                        retry_after_hint = (
                            _parse_retry_after(exc.response) or retry_after_hint
                        )
                        _advance_key()
                        last_error = str(exc)
                        break
                    raise
                except requests.exceptions.Timeout as exc:
                    logger.warning(
                        "Key %d timed out after %ss, trying next.",
                        attempt + 1,
                        LLM_TIMEOUT,
                    )
                    last_error = f"timeout on key {attempt + 1}: {exc}"
                    break
                except requests.exceptions.ConnectionError as exc:
                    logger.warning("Key %d connection error: %s", attempt + 1, exc)
                    last_error = f"connection error on key {attempt + 1}: {exc}"
                    break

        # All keys exhausted this round on a retryable status. Back off and
        # retry the whole key set unless the retry budget is spent. Retry-After
        # is honored but capped at LLM_BACKOFF_CAP (never sleep for minutes).
        if retry < LLM_MAX_RETRIES:
            backoff = min(LLM_BACKOFF_CAP, LLM_BACKOFF_BASE * (2 ** retry))
            if retry_after_hint is not None:
                backoff = min(LLM_BACKOFF_CAP, max(backoff, retry_after_hint))
            backoff += random.uniform(0, backoff * 0.1)  # jitter, avoid thundering herd
            logger.warning(
                "All %d key(s) exhausted (%s); backoff %.1fs then retry %d/%d.",
                attempts,
                last_error,
                backoff,
                retry + 1,
                LLM_MAX_RETRIES,
            )
            time.sleep(backoff)

    _record_failure()
    if vertical_id is not None:
        try:
            from engine.core import llm_audit

            llm_audit.record_call(
                caller=caller or "unknown",
                model=resolved_model,
                vertical_id=vertical_id,
                story_id=story_id,
                article_id=article_id,
                error=str(last_error)[:500] if last_error else "exhausted",
            )
        except Exception as exc:
            logger.debug("llm_audit.record_call (failure path) failed: %s", exc)
    raise RuntimeError(
        f"All {attempts} API key(s) exhausted after {LLM_MAX_RETRIES + 1} "
        f"attempt(s): {last_error}"
    )


def is_available() -> bool:
    """Check if any LLM API key is configured."""
    return bool(LLM_API_KEY) or bool(LLM_API_KEYS)
