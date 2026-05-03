"""Tests for engine.core.newsletter_generator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import newsletter_generator as ng
from engine.core.db import Article, Base, Vertical


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
    # Repoint Jinja loader at the in-repo templates (default is /srv/grimoire).
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(ng, "_TEMPLATES_DIR", repo_root / "engine" / "shared" / "templates")
    yield eng


@pytest.fixture
def seeded(test_engine):
    """Seed a vertical + a spread of articles inside and outside this week."""
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)  # Wed
    monday = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    last_week = monday - timedelta(days=3)

    with SM() as s:
        v = Vertical(name="modelwatch", display_name="Modelwatch")
        s.add(v)
        s.commit()
        s.refresh(v)
        for i, hours_back in enumerate([1, 24, 48]):
            s.add(
                Article(
                    vertical_id=v.id,
                    hash=f"hash-this-{i}",
                    slug=f"this-week-{i}",
                    title=f"This Week Story {i}",
                    link=f"https://example.com/this/{i}",
                    source="https://example.com/feed",
                    feed_region="US",
                    summary=f"Summary {i} body.",
                    why_this_matters=f"Matters {i}.",
                    summary_source="llm",
                    published_at=now - timedelta(hours=hours_back),
                )
            )
        s.add(
            Article(
                vertical_id=v.id,
                hash="hash-feed",
                slug="feed-only",
                title="Placeholder Story",
                link="https://example.com/feed-only",
                source="https://example.com/feed",
                feed_region="US",
                summary="Feed only.",
                summary_source="feed",
                published_at=now - timedelta(hours=2),
            )
        )
        s.add(
            Article(
                vertical_id=v.id,
                hash="hash-last",
                slug="last-week",
                title="Last Week Story",
                link="https://example.com/last",
                source="https://example.com/feed",
                feed_region="EU",
                summary="Old.",
                summary_source="llm",
                published_at=last_week,
            )
        )
        s.commit()
    return now


class TestWeekWindow:
    def test_anchors_to_monday(self) -> None:
        wed = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
        start, end = ng._week_window(now=wed)
        assert start.isoweekday() == 1
        assert (end - start) == timedelta(days=7)
        assert start <= wed < end

    def test_offset_back_one_week(self) -> None:
        wed = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
        prev_start, prev_end = ng._week_window(week_offset=-1, now=wed)
        cur_start, _ = ng._week_window(now=wed)
        assert prev_end == cur_start


class TestIsoWeekKey:
    def test_format(self) -> None:
        assert ng._iso_week_key(datetime(2026, 5, 4, tzinfo=timezone.utc)) == "2026-W19"


class TestGenerateDigest:
    def test_selects_this_week_llm_only(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", now=seeded)
        titles = [a["title"] for a in digest["articles"]]
        assert "Placeholder Story" not in titles
        assert "Last Week Story" not in titles
        assert len(digest["articles"]) == 3

    def test_newest_first(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", now=seeded)
        titles = [a["title"] for a in digest["articles"]]
        assert titles == [
            "This Week Story 0",
            "This Week Story 1",
            "This Week Story 2",
        ]

    def test_quiet_week_subject(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", week_offset=-2, now=seeded)
        assert digest["articles"] == []
        assert "quiet week" in digest["subject"].lower()

    def test_unknown_vertical_returns_empty(self, seeded) -> None:
        digest = ng.generate_digest("ghost", now=seeded)
        assert digest["articles"] == []
        assert digest["subject"]

    def test_html_contains_titles_and_archive_link(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", now=seeded)
        for a in digest["articles"]:
            assert a["title"] in digest["html"]
        assert f"/digest/{digest['week_key']}/" in digest["html"]

    def test_text_contains_titles(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", now=seeded)
        for a in digest["articles"]:
            assert a["title"] in digest["text"]

    def test_limit_applied(self, seeded) -> None:
        digest = ng.generate_digest("modelwatch", limit=2, now=seeded)
        assert len(digest["articles"]) == 2


class TestRenderArchive:
    def test_writes_index_html(
        self, seeded, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import engine.core.newsletter_generator as ng_mod

        monkeypatch.setattr(ng_mod, "DATA_DIR", tmp_path)
        path = ng.render_archive("modelwatch", now=seeded)
        assert path.exists()
        assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
        assert "/digest/" in str(path)
