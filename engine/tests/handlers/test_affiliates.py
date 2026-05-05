"""Tests for engine.handlers.affiliates — /r/<partner>/<slug> redirect surface."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from engine.core.db import AffiliateClick


@pytest.fixture
def partner_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point VERTICALS_DIR at a tmp tree with a synthetic partners.yaml.

    Reuses the modelwatch slug already seeded by the `client` fixture so
    the AffiliateClick row's vertical_id resolves correctly.
    """
    import engine.core.config as cfg
    from engine.handlers import affiliates

    vroot = tmp_path / "verticals"
    (vroot / "modelwatch").mkdir(parents=True)
    (vroot / "modelwatch" / "partners.yaml").write_text(
        """
partners:
  anthropic:
    url: https://www.anthropic.com/?ref=auvalabs
    name: Anthropic
  cursor:
    url: https://cursor.com
    name: Cursor
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "VERTICALS_DIR", vroot)
    affiliates.reload_partners()
    yield
    affiliates.reload_partners()


def test_redirect_with_known_partner_is_302(client, partner_registry) -> None:
    r = client.get(
        "/r/anthropic/claude-models",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://www.anthropic.com/")
    assert "utm_source=modelwatch" in loc
    assert "utm_medium=affiliate" in loc
    assert "utm_campaign=claude-models" in loc


def test_redirect_appends_utm_when_url_has_no_query(
    client, partner_registry
) -> None:
    r = client.get(
        "/r/cursor/editor",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    # cursor.com had no query string → "?utm_*" not "&utm_*"
    assert loc.startswith("https://cursor.com?utm_source=modelwatch")


def test_unknown_partner_404(client, partner_registry) -> None:
    r = client.get(
        "/r/ghost-partner/x",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    assert r.status_code == 404


def test_default_slug_works(client, partner_registry) -> None:
    """/r/<partner> (no slug) defaults to '_'."""
    r = client.get(
        "/r/anthropic",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "utm_campaign=_" in r.headers["location"]


def test_slug_sanitised(client, partner_registry) -> None:
    r = client.get(
        "/r/anthropic/abc-123",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "utm_campaign=abc-123" in r.headers["location"]


def test_click_row_inserted(
    client, partner_registry, test_engine
) -> None:
    client.get(
        "/r/anthropic/abc",
        headers={"host": "modelwatch.local"},
        follow_redirects=False,
    )
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        rows = s.execute(select(AffiliateClick)).scalars().all()
        assert len(rows) == 1
        assert rows[0].partner == "anthropic"
        assert rows[0].slug == "abc"
        assert len(rows[0].ip_hash) == 64


def test_unknown_vertical_host_returns_404(client, partner_registry) -> None:
    """Host whose label has no partners.yaml → empty registry → 404 partner."""
    r = client.get(
        "/r/anthropic/x",
        headers={"host": "ghost.local"},
        follow_redirects=False,
    )
    assert r.status_code == 404
