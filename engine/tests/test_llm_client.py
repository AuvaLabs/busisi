"""Tests for the LLM client's bounded retry-with-backoff.

Regression coverage for the single-key 429 failure mode: with one API key,
key-rotation has nothing to rotate to, so a transient 429 / 5xx / timeout used
to become an instant hard failure. The client now retries the whole key set
with capped exponential backoff before giving up.

All HTTP is mocked; ``time.sleep`` is stubbed so the suite stays fast.
"""
from __future__ import annotations

import pytest
import requests

from engine.core import llm_client as c


class _FakeResp:
    def __init__(self, status: int, content: str = "ok", headers=None) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._content = content

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


class _FakeSession:
    """Returns queued responses; repeats the last one once the queue drains."""

    def __init__(self, responses: list[_FakeResp]) -> None:
        self._responses = list(responses)
        self._last = responses[-1]
        self.calls = 0

    def post(self, *args, **kwargs) -> _FakeResp:
        self.calls += 1
        if self._responses:
            self._last = self._responses.pop(0)
        return self._last


@pytest.fixture
def single_key(monkeypatch: pytest.MonkeyPatch):
    """Configure a single-key client with fast, deterministic backoff."""
    monkeypatch.setattr(c, "LLM_API_KEYS", ["k1"])
    monkeypatch.setattr(c, "LLM_MAX_RETRIES", 2)
    monkeypatch.setattr(c, "LLM_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(c, "LLM_BACKOFF_CAP", 0.0)
    sleeps: list[float] = []
    monkeypatch.setattr(c.time, "sleep", lambda s: sleeps.append(s))
    c.reset_circuit()
    return sleeps


def _call() -> str:
    return c.call_llm(user_content="u", system_prompt="s")


class TestParseRetryAfter:
    def test_integer_seconds(self) -> None:
        resp = _FakeResp(429, headers={"Retry-After": "5"})
        assert c._parse_retry_after(resp) == 5.0

    def test_http_date_returns_none(self) -> None:
        resp = _FakeResp(429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
        assert c._parse_retry_after(resp) is None

    def test_absent_returns_none(self) -> None:
        assert c._parse_retry_after(_FakeResp(200)) is None


class TestSingleKeyRetry:
    def test_429_then_success_recovers(
        self, single_key, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps = single_key
        sess = _FakeSession([_FakeResp(429), _FakeResp(200, "hello")])
        monkeypatch.setattr(c, "_get_http_session", lambda: sess)

        out = _call()
        assert out == "hello"
        assert sess.calls == 2  # one 429, one success
        assert len(sleeps) == 1  # backed off once between attempts

    def test_504_then_success_recovers(
        self, single_key, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = _FakeSession([_FakeResp(504), _FakeResp(200, "ok2")])
        monkeypatch.setattr(c, "_get_http_session", lambda: sess)
        assert _call() == "ok2"

    def test_exhausts_after_max_retries(
        self, single_key, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps = single_key
        sess = _FakeSession([_FakeResp(429)])  # always 429
        monkeypatch.setattr(c, "_get_http_session", lambda: sess)

        with pytest.raises(RuntimeError, match="exhausted"):
            _call()
        # LLM_MAX_RETRIES=2 -> 3 total attempts, 2 backoff sleeps between them.
        assert len(sleeps) == 2
        assert sess.calls == 3

    def test_non_retryable_http_error_not_retried(
        self, single_key, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps = single_key
        sess = _FakeSession([_FakeResp(400)])
        monkeypatch.setattr(c, "_get_http_session", lambda: sess)

        with pytest.raises(requests.exceptions.HTTPError):
            _call()
        assert sess.calls == 1  # no rotation, no retry
        assert len(sleeps) == 0

    def test_retry_after_header_caps_at_backoff_cap(
        self, single_key, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Provider asks for 999s; cap is 0.0 here, so we must NOT sleep 999s.
        sleeps = single_key
        sess = _FakeSession(
            [_FakeResp(429, headers={"Retry-After": "999"}), _FakeResp(200, "z")]
        )
        monkeypatch.setattr(c, "_get_http_session", lambda: sess)

        assert _call() == "z"
        assert all(s <= 0.0 for s in sleeps)  # Retry-After clamped by cap
