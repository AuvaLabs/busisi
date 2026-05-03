"""Fixtures for the engine.handlers test suite.

  - ``test_engine``    : in-memory SQLite engine, schema applied, swapped into
                        ``engine.core.db._engine`` so live code uses it.
  - ``seeded_vertical``: yields the Vertical row id for ``modelwatch``.
  - ``fernet_env``     : monkeypatches FERNET key + pepper inside
                        ``engine.handlers.security``.
  - ``fake_email_send``: patches ``email_sender.send`` to a recording stub.
  - ``fake_redis``     : forces rate-limit + cache helpers onto fakeredis.
  - ``client``         : assembled FastAPI TestClient.
"""

from __future__ import annotations

from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
import engine.handlers.security as security_module
from engine.core.db import Base, Vertical


@pytest.fixture
def test_engine(monkeypatch: pytest.MonkeyPatch):
    # StaticPool + check_same_thread=False keeps the in-memory database
    # alive across every checkout. Without this, SQLAlchemy's default pool
    # closes the connection between requests and the next query lands on a
    # fresh, empty :memory: database.
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


@pytest.fixture
def fernet_env(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    pepper = "test-pepper-not-secret"
    monkeypatch.setattr(security_module, "SUBSCRIBER_FERNET_KEY", key)
    monkeypatch.setattr(security_module, "SUBSCRIBER_EMAIL_PEPPER", pepper)
    monkeypatch.setattr(security_module, "HANDLER_RATE_LIMIT_PER_5MIN", 100)
    return key


@pytest.fixture
def fake_email_send(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    import engine.handlers.email_sender as mailer
    import engine.handlers.sponsors as sp_router
    import engine.handlers.subscribers as sub_router

    monkeypatch.setattr(mailer, "send", _stub)
    monkeypatch.setattr(sub_router.email_sender, "send", _stub)
    monkeypatch.setattr(sp_router.email_sender, "send", _stub)
    return sent


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    import fakeredis

    fr = fakeredis.FakeStrictRedis(decode_responses=True)
    import engine.core.llm_cache as cache_module

    monkeypatch.setattr(cache_module, "_redis", lambda: fr)
    # security.py did ``from engine.core.llm_cache import _redis`` at import
    # time, so patching the module attribute alone won't reach it.
    monkeypatch.setattr(security_module, "_redis", lambda: fr)
    return fr


@pytest.fixture
def repo_verticals_dir(monkeypatch: pytest.MonkeyPatch):
    """Point ``VERTICALS_DIR`` at the in-repo ``verticals/`` so tools resolve.

    Defaults to ``/srv/grimoire/verticals`` (server path) which doesn't exist
    in CI.
    """
    from pathlib import Path

    import engine.core.config as cfg

    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(cfg, "VERTICALS_DIR", repo_root / "verticals")


@pytest.fixture
def client(
    test_engine,
    seeded_vertical,
    fernet_env,
    fake_email_send,
    fake_redis,
    repo_verticals_dir,
):
    from fastapi.testclient import TestClient

    from engine.handlers.app import app

    with TestClient(app) as c:
        yield c
