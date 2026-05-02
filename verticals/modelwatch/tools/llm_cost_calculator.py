"""LLM cost calculator — estimate API spend at scale.

Pricing reflects published rates as of META["last_verified"]. Refresh
quarterly. Each price is per 1,000 tokens (input/output split).
"""

from __future__ import annotations

from typing import Any

# (input_per_1k_usd, output_per_1k_usd)
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o":              (0.0025, 0.01),
    "gpt-4o-mini":         (0.00015, 0.0006),
    "gpt-4-turbo":         (0.01, 0.03),
    "claude-opus-4":       (0.015, 0.075),
    "claude-sonnet-4-5":   (0.003, 0.015),
    "claude-haiku-4-5":    (0.001, 0.005),
    "gemini-2-5-pro":      (0.00125, 0.005),
    "gemini-2-5-flash":    (0.000075, 0.0003),
    "deepseek-v3":         (0.00027, 0.0011),
    "llama-3-3-70b":       (0.00059, 0.00079),
    "groq-llama-3-3-70b":  (0.00059, 0.00079),
    "mistral-large-2":     (0.002, 0.006),
}


META: dict[str, Any] = {
    "slug": "llm-cost-calculator",
    "title": "LLM cost calculator",
    "description": (
        "Estimate the daily and monthly cost of running a prompt at scale "
        "across the major proprietary and open-source LLM APIs."
    ),
    "category": "compute",
    "last_verified": "2026-05-02",
    "inputs": [
        {
            "name": "model",
            "label": "Model",
            "type": "select",
            "default": "claude-sonnet-4-5",
            "options": list(_PRICING.keys()),
        },
        {
            "name": "input_tokens",
            "label": "Input tokens per request",
            "type": "number",
            "default": 1000,
            "min": 0,
            "step": 100,
        },
        {
            "name": "output_tokens",
            "label": "Output tokens per request",
            "type": "number",
            "default": 500,
            "min": 0,
            "step": 100,
        },
        {
            "name": "requests_per_day",
            "label": "Requests per day",
            "type": "number",
            "default": 1000,
            "min": 0,
            "step": 100,
        },
    ],
    "output_format": "USD",
    "notes": (
        "Cached input tokens (e.g. Anthropic prompt caching, OpenAI cached "
        "input) are not modelled here — applying caching can drop the "
        "input cost by 5-10x depending on hit rate."
    ),
}


def calculate(inputs: dict[str, Any]) -> dict[str, Any]:
    model = str(inputs.get("model", "claude-sonnet-4-5"))
    in_tok = float(inputs.get("input_tokens", 0) or 0)
    out_tok = float(inputs.get("output_tokens", 0) or 0)
    rpd = float(inputs.get("requests_per_day", 0) or 0)

    if model not in _PRICING:
        raise ValueError(f"unknown model: {model}")
    in_rate, out_rate = _PRICING[model]

    per_call_in = (in_tok / 1000.0) * in_rate
    per_call_out = (out_tok / 1000.0) * out_rate
    per_call_total = per_call_in + per_call_out
    daily = per_call_total * rpd
    monthly = daily * 30.0
    annual = daily * 365.0

    return {
        "result": daily,
        "headline": f"${daily:,.2f}/day",
        "breakdown": [
            ("Input cost / call", f"${per_call_in:.6f}"),
            ("Output cost / call", f"${per_call_out:.6f}"),
            ("Total / call", f"${per_call_total:.6f}"),
            ("Daily", f"${daily:,.2f}"),
            ("Monthly (30d)", f"${monthly:,.2f}"),
            ("Annual (365d)", f"${annual:,.2f}"),
        ],
    }
