"""Tests for engine.core.bot_log_parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import bot_log_parser as blp
from engine.core.db import Base, BotHit, Vertical


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


@pytest.fixture
def seeded_vertical(test_engine) -> int:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)
        return v.id


# ---------------------------------------------------------------------------


class TestClassifyUa:
    @pytest.mark.parametrize(
        "ua,expected",
        [
            ("PerplexityBot/1.0 (+https://perplexity.ai)", "PerplexityBot"),
            ("Perplexity-User/1.0", "Perplexity-User"),
            ("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com)", "GPTBot"),
            ("ChatGPT-User/1.0", "ChatGPT-User"),
            ("Mozilla/5.0 (compatible; ClaudeBot/1.0)", "ClaudeBot"),
            ("Claude-Web/1.0", "Claude-Web"),
            ("Mozilla/5.0 (compatible; Googlebot/2.1)", "Googlebot"),
            ("Google-Extended/1.0", "Google-Extended"),
            ("Mozilla/5.0 (compatible; bingbot/2.0)", "Bingbot"),
            ("CCBot/2.0", "CCBot"),
            ("Bytespider", "Bytespider"),
            ("anthropic-ai/1.0", "anthropic-ai"),
        ],
    )
    def test_known_bots(self, ua: str, expected: str) -> None:
        assert blp.classify_ua(ua) == expected

    def test_browser_returns_none(self) -> None:
        assert blp.classify_ua(
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36"
        ) is None

    def test_empty_returns_none(self) -> None:
        assert blp.classify_ua("") is None


# ---------------------------------------------------------------------------


class TestParseLines:
    def test_extracts_well_formed_perplexity(self) -> None:
        line = json.dumps(
            {
                "ts": 1715000000.0,
                "request": {
                    "uri": "/story/foo/",
                    "headers": {"User-Agent": ["PerplexityBot/1.0"]},
                    "remote_ip": "203.0.113.5",
                },
                "status": 200,
            }
        )
        out = list(blp.parse_lines([line]))
        assert len(out) == 1
        h = out[0]
        assert h["bot_name"] == "PerplexityBot"
        assert h["path"] == "/story/foo/"
        assert h["status"] == 200
        assert h["remote_ip"] == "203.0.113.5"

    def test_prefers_cf_connecting_ip_over_remote_ip(self) -> None:
        """With Cloudflare orange-cloud, request.remote_ip is a CF edge
        address; the real bot IP arrives in CF-Connecting-IP."""
        line = json.dumps(
            {
                "ts": 1715000000.0,
                "request": {
                    "uri": "/llms.txt",
                    "headers": {
                        "User-Agent": ["GPTBot/1.0"],
                        "Cf-Connecting-Ip": ["203.0.113.99"],
                    },
                    "remote_ip": "172.71.130.45",
                },
                "status": 200,
            }
        )
        out = list(blp.parse_lines([line]))
        assert len(out) == 1
        assert out[0]["remote_ip"] == "203.0.113.99"

    def test_falls_back_to_remote_ip_when_cf_header_absent(self) -> None:
        """Direct-origin requests (local dev, edge-IP probes) have no
        CF-Connecting-IP — fall back to the connection's remote_ip."""
        line = json.dumps(
            {
                "ts": 1715000000.0,
                "request": {
                    "uri": "/",
                    "headers": {"User-Agent": ["ClaudeBot/1.0"]},
                    "remote_ip": "192.0.2.42",
                },
                "status": 200,
            }
        )
        out = list(blp.parse_lines([line]))
        assert len(out) == 1
        assert out[0]["remote_ip"] == "192.0.2.42"

    def test_extract_cf_ip_helper_handles_case_variants(self) -> None:
        for header_name in ("Cf-Connecting-Ip", "CF-Connecting-IP", "cf-connecting-ip"):
            assert (
                blp._extract_cf_ip({header_name: ["198.51.100.10"]})
                == "198.51.100.10"
            )
        assert blp._extract_cf_ip({}) == ""
        assert blp._extract_cf_ip(None) == ""

    def test_skips_invalid_json(self) -> None:
        out = list(blp.parse_lines(["not json", "", "{ broken"]))
        assert out == []

    def test_skips_browser_ua(self) -> None:
        line = json.dumps(
            {
                "ts": 1715000000.0,
                "request": {
                    "uri": "/",
                    "headers": {"User-Agent": ["Mozilla/5.0 (real browser)"]},
                    "remote_ip": "203.0.113.6",
                },
                "status": 200,
            }
        )
        assert list(blp.parse_lines([line])) == []

    def test_skips_when_ua_missing(self) -> None:
        line = json.dumps(
            {"ts": 1715000000.0, "request": {"uri": "/"}, "status": 200}
        )
        assert list(blp.parse_lines([line])) == []


# ---------------------------------------------------------------------------


class TestIngest:
    def _write_log(self, tmp_path: Path, entries: list[dict]) -> Path:
        p = tmp_path / "modelwatch.log"
        p.write_text(
            "\n".join(json.dumps(e) for e in entries), encoding="utf-8"
        )
        return p

    def test_inserts_bot_hits(
        self, test_engine, seeded_vertical, tmp_path: Path
    ) -> None:
        log = self._write_log(
            tmp_path,
            [
                {
                    "ts": 1715000000.0,
                    "request": {
                        "uri": "/story/foo/",
                        "headers": {"User-Agent": ["PerplexityBot/1.0"]},
                        "remote_ip": "203.0.113.5",
                    },
                    "status": 200,
                },
                {
                    "ts": 1715000010.0,
                    "request": {
                        "uri": "/llms.txt",
                        "headers": {"User-Agent": ["GPTBot/1.0"]},
                        "remote_ip": "203.0.113.10",
                    },
                    "status": 200,
                },
                {
                    "ts": 1715000020.0,
                    "request": {
                        "uri": "/",
                        "headers": {"User-Agent": ["Mozilla/5.0"]},
                        "remote_ip": "203.0.113.99",
                    },
                    "status": 200,
                },
            ],
        )
        n = blp.ingest("modelwatch", log_path=log)
        assert n == 2

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        with SM() as s:
            rows = s.execute(select(BotHit)).scalars().all()
            assert len(rows) == 2
            names = sorted(r.bot_name for r in rows)
            assert names == ["GPTBot", "PerplexityBot"]
            assert all(len(r.ip_hash) == 64 for r in rows)

    def test_idempotent_on_rerun(
        self, test_engine, seeded_vertical, tmp_path: Path
    ) -> None:
        log = self._write_log(
            tmp_path,
            [
                {
                    "ts": 1715000000.0,
                    "request": {
                        "uri": "/x/",
                        "headers": {"User-Agent": ["PerplexityBot"]},
                        "remote_ip": "1.2.3.4",
                    },
                    "status": 200,
                }
            ],
        )
        assert blp.ingest("modelwatch", log_path=log) == 1
        assert blp.ingest("modelwatch", log_path=log) == 0

    def test_missing_log_returns_zero(
        self, test_engine, seeded_vertical, tmp_path: Path
    ) -> None:
        n = blp.ingest("modelwatch", log_path=tmp_path / "absent.log")
        assert n == 0

    def test_unknown_vertical_raises(
        self, test_engine, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError):
            blp.ingest("ghost", log_path=tmp_path / "absent.log")
