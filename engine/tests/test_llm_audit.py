"""Tests for engine.core.llm_audit (C1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import llm_audit
from engine.core.db import Base, LLMCall, Vertical


@pytest.fixture
def test_engine(monkeypatch: pytest.MonkeyPatch):
    eng = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "_engine", eng)
    yield eng


def _seed_vertical(eng, name: str = "embedding") -> int:
    SM = sessionmaker(eng, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name=name, display_name=name.title())
        s.add(v)
        s.commit()
        return v.id


class TestUnitsForModel:
    def test_qwen_7b_is_one_unit(self) -> None:
        assert llm_audit.units_for_model("Qwen/Qwen2.5-7B-Instruct") == 1

    def test_qwen_32b_is_two_units(self) -> None:
        assert llm_audit.units_for_model("Qwen/Qwen2.5-32B-Instruct") == 2

    def test_qwen_72b_is_four_units(self) -> None:
        assert llm_audit.units_for_model("Qwen/Qwen2.5-72B-Instruct") == 4

    def test_deepseek_v3_is_four_units(self) -> None:
        assert llm_audit.units_for_model("deepseek-ai/DeepSeek-V3") == 4

    def test_llama_4_maverick_is_four_units(self) -> None:
        assert (
            llm_audit.units_for_model("meta-llama/Llama-4-Maverick-17B-128E-Instruct")
            == 4
        )

    def test_llama_4_scout_is_two_units(self) -> None:
        assert llm_audit.units_for_model("meta-llama/Llama-4-Scout-17B-16E") == 2

    def test_unknown_falls_back_to_two(self) -> None:
        # No size suffix, no premium marker → conservative mid default.
        assert llm_audit.units_for_model("some/UnknownModel") == 2


class TestCapForVertical:
    def test_unset_env_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLM_DAILY_UNIT_CAP__embedding", raising=False)
        assert llm_audit.cap_for_vertical("embedding") == 0

    def test_env_set_returns_int(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_DAILY_UNIT_CAP__embedding", "750")
        assert llm_audit.cap_for_vertical("embedding") == 750

    def test_invalid_env_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_DAILY_UNIT_CAP__embedding", "not-a-number")
        assert llm_audit.cap_for_vertical("embedding") == 0

    def test_none_vertical_returns_zero(self) -> None:
        assert llm_audit.cap_for_vertical(None) == 0


class TestCapExceeded:
    def test_no_cap_means_no_exceed(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vid = _seed_vertical(test_engine)
        monkeypatch.delenv("LLM_DAILY_UNIT_CAP__embedding", raising=False)
        exceeded, used, cap = llm_audit.cap_exceeded(vid, additional_units=4)
        assert exceeded is False
        assert cap == 0

    def test_under_cap_not_exceeded(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vid = _seed_vertical(test_engine)
        monkeypatch.setenv("LLM_DAILY_UNIT_CAP__embedding", "100")
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            s.add(
                LLMCall(
                    caller="test",
                    model="Qwen/Qwen2.5-72B-Instruct",
                    vertical_id=vid,
                    cost_units=50,
                )
            )
            s.commit()
        exceeded, used, cap = llm_audit.cap_exceeded(vid, additional_units=4)
        assert exceeded is False
        assert used == 50
        assert cap == 100

    def test_over_cap_exceeded(
        self, test_engine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vid = _seed_vertical(test_engine)
        monkeypatch.setenv("LLM_DAILY_UNIT_CAP__embedding", "10")
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            s.add(
                LLMCall(
                    caller="test",
                    model="Qwen/Qwen2.5-7B-Instruct",
                    vertical_id=vid,
                    cost_units=9,
                )
            )
            s.commit()
        exceeded, used, cap = llm_audit.cap_exceeded(vid, additional_units=4)
        assert exceeded is True
        assert used == 9
        assert cap == 10


class TestRecordCall:
    def test_record_call_inserts_row(self, test_engine) -> None:
        vid = _seed_vertical(test_engine)
        llm_audit.record_call(
            caller="pass0_extract",
            model="Qwen/Qwen2.5-7B-Instruct",
            vertical_id=vid,
            article_id=None,
            input_tokens=1500,
            output_tokens=400,
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            row = s.execute(select(LLMCall)).scalar_one()
            assert row.caller == "pass0_extract"
            assert row.model == "Qwen/Qwen2.5-7B-Instruct"
            assert row.input_tokens == 1500
            assert row.output_tokens == 400
            assert row.total_tokens == 1900
            assert row.cost_units == 1
            assert row.error is None

    def test_record_failure_with_error_string(self, test_engine) -> None:
        vid = _seed_vertical(test_engine)
        llm_audit.record_call(
            caller="pass2_compose",
            model="deepseek-ai/DeepSeek-V3",
            vertical_id=vid,
            error="429 from upstream",
        )
        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            row = s.execute(select(LLMCall)).scalar_one()
            assert row.error == "429 from upstream"
            assert row.cost_units == 4

    def test_extract_token_counts_handles_missing(self) -> None:
        assert llm_audit.extract_token_counts({}) == (0, 0)
        assert llm_audit.extract_token_counts({"usage": None}) == (0, 0)
        assert llm_audit.extract_token_counts(
            {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        ) == (100, 50)
