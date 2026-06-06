"""Tests for engine.core.llm_routing (R2)."""

from __future__ import annotations

import pytest

from engine.core import llm_routing as r


class TestModelForDefaults:
    def test_known_caller_returns_registry_default(self) -> None:
        # Llama-3.1-8B-Turbo (DeepInfra) is the default for cheap callers.
        assert r.model_for("classify").startswith("meta-llama/")

    def test_pass2_default_is_deepseek(self) -> None:
        assert r.model_for("pass2_compose") == "deepseek-ai/DeepSeek-V4-Pro"

    def test_known_callers_returns_sorted(self) -> None:
        callers = r.known_callers()
        assert callers == sorted(callers)
        assert "pass1_merge" in callers
        assert "pass2_compose" in callers


class TestVerticalOverrides:
    def test_embedding_pass2_uses_maverick(self) -> None:
        assert r.model_for("pass2_compose", vertical="embedding").startswith(
            "meta-llama/"
        )

    def test_vested_pass2_uses_deepseek(self) -> None:
        assert r.model_for("pass2_compose", vertical="vested") == (
            "deepseek-ai/DeepSeek-V4-Pro"
        )

    def test_unknown_vertical_falls_back_to_default(self) -> None:
        # 'fictional' has no override → default DeepSeek V4-Pro.
        assert r.model_for("pass2_compose", vertical="fictional") == (
            "deepseek-ai/DeepSeek-V4-Pro"
        )


class TestEnvOverrides:
    def test_per_caller_env_var_wins_over_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL__classify", "TestOrg/TinyJSON-1B")
        assert r.model_for("classify") == "TestOrg/TinyJSON-1B"

    def test_per_vertical_caller_env_var_most_specific(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL__pass2_compose", "Generic/M")
        monkeypatch.setenv("LLM_MODEL__vested__pass2_compose", "Specific/V")
        # Per-vertical wins.
        assert r.model_for("pass2_compose", vertical="vested") == "Specific/V"
        # Generic still returned for verticals without their own override.
        assert r.model_for("pass2_compose", vertical="other") == "Generic/M"

    def test_blank_env_var_does_not_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL__classify", "   ")
        # Blank env should fall through to default, not return empty string.
        assert r.model_for("classify").startswith("meta-llama/")


class TestUnknownCaller:
    def test_unknown_caller_uses_legacy_global(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch the module-level constant cached at import time.
        monkeypatch.setattr(r, "LLM_MODEL", "Legacy/Global")
        assert r.model_for("never_seen_caller") == "Legacy/Global"

    def test_unknown_caller_with_empty_legacy_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(r, "LLM_MODEL", "")
        with pytest.raises(KeyError):
            r.model_for("never_seen_caller")
