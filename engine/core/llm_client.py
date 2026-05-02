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
from typing import Any

import requests

from engine.core.config import (
    LLM_API_KEY,
    LLM_API_KEYS,
    LLM_BASE_URL,
    LLM_CIRCUIT_THRESHOLD,
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
    if len(LLM_API_KEYS) <= 1:
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
) -> str:
    """Call the LLM API with key failover."""
    if _circuit_open():
        raise RuntimeError(
            f"LLM circuit breaker open: >= {LLM_CIRCUIT_THRESHOLD} consecutive failures"
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
                resp = session.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)

                if resp.status_code == 429:
                    logger.warning("Key %d rate-limited (429), trying next.", attempt + 1)
                    _advance_key()
                    last_error = f"429 on key {attempt + 1}"
                    break
                if resp.status_code in (500, 502, 503, 504):
                    logger.warning(
                        "Key %d got %d from upstream, trying next.",
                        attempt + 1,
                        resp.status_code,
                    )
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

                content = data["choices"][0]["message"]["content"]
                return str(content).strip()

            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    logger.warning("Key %d rate-limited, trying next.", attempt + 1)
                    _advance_key()
                    last_error = str(exc)
                    break
                raise
            except requests.exceptions.Timeout as exc:
                logger.warning(
                    "Key %d timed out after %ss, trying next.", attempt + 1, LLM_TIMEOUT
                )
                last_error = f"timeout on key {attempt + 1}: {exc}"
                break
            except requests.exceptions.ConnectionError as exc:
                logger.warning("Key %d connection error: %s", attempt + 1, exc)
                last_error = f"connection error on key {attempt + 1}: {exc}"
                break

    _record_failure()
    raise RuntimeError(f"All {attempts} API keys exhausted: {last_error}")


def is_available() -> bool:
    """Check if any LLM API key is configured."""
    return bool(LLM_API_KEY) or bool(LLM_API_KEYS)
