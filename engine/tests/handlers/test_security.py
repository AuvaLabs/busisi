"""Unit tests for engine.handlers.security."""

from __future__ import annotations

import time

import pytest
from cryptography.fernet import InvalidToken

from engine.handlers import security


class TestEmailHashing:
    def test_hash_deterministic(self, fernet_env: str) -> None:
        a = security.hash_email("alice@example.com")
        b = security.hash_email("alice@example.com")
        assert a == b
        assert len(a) == 64

    def test_hash_case_insensitive(self, fernet_env: str) -> None:
        assert security.hash_email("Alice@Example.com") == security.hash_email(
            "alice@example.com"
        )

    def test_hash_strips_whitespace(self, fernet_env: str) -> None:
        assert security.hash_email("  alice@example.com  ") == security.hash_email(
            "alice@example.com"
        )

    def test_hash_pepper_changes_output(
        self, fernet_env: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = security.hash_email("alice@example.com")
        monkeypatch.setattr(security, "SUBSCRIBER_EMAIL_PEPPER", "different-pepper")
        assert security.hash_email("alice@example.com") != baseline


class TestEmailEncryption:
    def test_roundtrip(self, fernet_env: str) -> None:
        token = security.encrypt_email("alice@example.com")
        assert security.decrypt_email(token) == "alice@example.com"

    def test_encrypt_normalises_case(self, fernet_env: str) -> None:
        token = security.encrypt_email("Alice@Example.COM")
        assert security.decrypt_email(token) == "alice@example.com"

    def test_decrypt_rejects_tampered(self, fernet_env: str) -> None:
        token = security.encrypt_email("alice@example.com")
        # Flip a character in the middle (base64url padding can eat a trailing
        # byte without raising, so mutate where it matters).
        mid = len(token) // 2
        flipped = "A" if token[mid] != "A" else "B"
        bad = token[:mid] + flipped + token[mid + 1 :]
        with pytest.raises(InvalidToken):
            security.decrypt_email(bad)

    def test_encrypt_without_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(security, "SUBSCRIBER_FERNET_KEY", "")
        with pytest.raises(security.CryptoUnavailable):
            security.encrypt_email("alice@example.com")


class TestSignedTokens:
    def test_roundtrip(self, fernet_env: str) -> None:
        tok = security.sign_token("c|42")
        assert security.verify_token(tok) == "c|42"

    def test_tampered_signature_fails(self, fernet_env: str) -> None:
        tok = security.sign_token("c|42")
        body, sig = tok.split(".", 1)
        bad = body + "." + ("A" * len(sig))
        assert security.verify_token(bad) is None

    def test_expired_token_fails(
        self, fernet_env: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tok = security.sign_token("c|42", expires_in=60)
        original = time.time
        monkeypatch.setattr(time, "time", lambda: original() + 3600)
        assert security.verify_token(tok) is None

    def test_garbage_input_returns_none(self, fernet_env: str) -> None:
        assert security.verify_token("not-a-token") is None
        assert security.verify_token("") is None

    def test_no_key_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(security, "SUBSCRIBER_FERNET_KEY", "")
        assert security.verify_token("anything.here") is None


class TestRandomToken:
    def test_default_length_is_urlsafe(self) -> None:
        tok = security.random_token()
        assert len(tok) >= 32
        assert all(c.isalnum() or c in "-_" for c in tok)

    def test_unique_per_call(self) -> None:
        assert security.random_token() != security.random_token()


class TestRateLimit:
    def test_under_limit_allows(self, fernet_env: str, fake_redis) -> None:
        for _ in range(5):
            assert security.rate_limit_hit("test", "1.2.3.4") is True

    def test_over_limit_blocks(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis
    ) -> None:
        monkeypatch.setattr(security, "HANDLER_RATE_LIMIT_PER_5MIN", 3)
        results = [security.rate_limit_hit("test", "9.9.9.9") for _ in range(5)]
        assert results == [True, True, True, False, False]

    def test_per_ip_isolated(
        self, monkeypatch: pytest.MonkeyPatch, fake_redis
    ) -> None:
        monkeypatch.setattr(security, "HANDLER_RATE_LIMIT_PER_5MIN", 2)
        assert security.rate_limit_hit("test", "1.1.1.1") is True
        assert security.rate_limit_hit("test", "1.1.1.1") is True
        assert security.rate_limit_hit("test", "1.1.1.1") is False
        assert security.rate_limit_hit("test", "2.2.2.2") is True

    def test_empty_ip_allows(self, fake_redis) -> None:
        assert security.rate_limit_hit("test", "") is True
