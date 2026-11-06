"""Parse structured council output without assuming a provider response shape."""

from __future__ import annotations

import json
from typing import Any

TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_tokens",
)


def _parse_json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_json(value: str) -> dict[str, Any]:
    """Return a verdict object from plain, fenced, or provider-wrapped output."""
    parsed = _parse_json_object(value.strip())
    if parsed is not None:
        wrapped = parsed.get("result")
        if isinstance(wrapped, str):
            nested = _parse_json_object(wrapped.strip())
            if nested is not None:
                return nested
        return parsed
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index in reversed(
        [position for position, character in enumerate(value) if character == "{"]
    ):
        try:
            candidate, end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            candidates.append((end, candidate))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    raise ValueError("model output does not contain a JSON object")


def _integer_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def token_usage(response: dict[str, Any]) -> dict[str, int | None]:
    """Normalize known token counters and leave unavailable counters unknown."""
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    result = {key: _integer_or_none(usage.get(key)) for key in TOKEN_KEYS}
    if result["cached_input_tokens"] is None:
        result["cached_input_tokens"] = _integer_or_none(usage.get("cache_read_input_tokens"))
    if result["cache_write_input_tokens"] is None:
        result["cache_write_input_tokens"] = _integer_or_none(
            usage.get("cache_creation_input_tokens")
        )
    output_details = usage.get("output_tokens_details")
    if result["reasoning_tokens"] is None and isinstance(output_details, dict):
        result["reasoning_tokens"] = _integer_or_none(output_details.get("thinking_tokens"))
    return result
