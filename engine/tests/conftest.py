"""Shared pytest fixtures for grimoire platform tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def fakeredis_client() -> Any:
    """Return a fakeredis client and patch redis.from_url to use it."""
    import fakeredis

    client = fakeredis.FakeStrictRedis(decode_responses=True)

    def _from_url(*_args: Any, **_kwargs: Any) -> Any:
        return client

    with patch("redis.Redis.from_url", side_effect=_from_url):
        yield client


@pytest.fixture
def temp_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect platform.core.config.STATE_DIR to a tmp dir for the test."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr("engine.core.config.STATE_DIR", state)
    monkeypatch.setattr("engine.core.llm_usage.USAGE_FILE", state / "llm_usage.json")
    return state


@pytest.fixture
def sample_articles() -> list[dict[str, Any]]:
    """A synthetic batch of articles in feed_fetcher output shape."""
    return [
        {
            "title": "GPT-5 Released With Major Reasoning Upgrades",
            "link": "https://example.com/gpt5",
            "published": "2026-05-02T10:00:00Z",
            "summary": "OpenAI announces GPT-5.",
            "hash": "",
            "source": "https://example.com/feed",
            "feed_region": "Global",
            "vertical_id": "modelwatch",
        },
        {
            "title": "OpenAI Unveils GPT-5 With Reasoning Improvements",
            "link": "https://example.org/openai-gpt5",
            "published": "2026-05-02T10:05:00Z",
            "summary": "Coverage of the GPT-5 launch.",
            "hash": "",
            "source": "https://example.org/feed",
            "feed_region": "US",
            "vertical_id": "modelwatch",
        },
        {
            "title": "Anthropic Ships Claude Sonnet 5.0",
            "link": "https://example.com/claude5",
            "published": "2026-05-02T11:00:00Z",
            "summary": "New Claude model.",
            "hash": "",
            "source": "https://example.com/feed",
            "feed_region": "Global",
            "vertical_id": "modelwatch",
        },
    ]
