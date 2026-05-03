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


class TestSendPendingDigests:
    def _seed_subscribers(
        self,
        test_engine,
        encrypted_addr: str,
        count: int,
        confirmed: bool = True,
        token_prefix: str = "unsub-token",
    ) -> list[int]:
        from sqlalchemy import select as _select

        from engine.core.db import Subscriber, Vertical

        SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
        ids: list[int] = []
        with SM() as s:
            v_id = s.execute(
                _select(Vertical).where(Vertical.name == "modelwatch")
            ).scalar_one().id
            offset = s.execute(
                _select(Subscriber).where(Subscriber.vertical_id == v_id)
            ).scalars().all()
            offset = len(offset)
            for i in range(count):
                idx = offset + i
                sub = Subscriber(
                    vertical_id=v_id,
                    email_hash=f"{token_prefix}-hash-{idx}",
                    email_encrypted=encrypted_addr,
                    confirmed=confirmed,
                    unsubscribe_token=f"{token_prefix}-{idx}",
                )
                s.add(sub)
                s.commit()
                s.refresh(sub)
                ids.append(sub.id)
        return ids

    @pytest.fixture
    def fernet_env(self, monkeypatch: pytest.MonkeyPatch) -> str:
        from cryptography.fernet import Fernet

        import engine.handlers.security as sec

        key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setattr(sec, "SUBSCRIBER_FERNET_KEY", key)
        monkeypatch.setattr(sec, "SUBSCRIBER_EMAIL_PEPPER", "test")
        return key

    @pytest.fixture
    def fake_send(self, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
        sent: list[dict] = []

        def _stub(**kwargs):
            sent.append(kwargs)
            return True

        import engine.handlers.email_sender as mailer

        monkeypatch.setattr(mailer, "send", _stub)
        return sent

    def test_skips_when_no_articles(
        self, seeded, fernet_env, fake_send, test_engine
    ) -> None:
        from engine.handlers.security import encrypt_email

        self._seed_subscribers(test_engine, encrypt_email("a@example.com"), 2)
        counts = ng.send_pending_digests(
            "modelwatch", week_offset=-2, now=seeded
        )  # week_offset=-2 has no seeded articles
        assert counts["sent"] == 0
        assert counts["skipped_no_articles"] == 1
        assert fake_send == []

    def test_sends_to_confirmed_only(
        self, seeded, fernet_env, fake_send, test_engine
    ) -> None:
        from engine.handlers.security import encrypt_email

        self._seed_subscribers(
            test_engine, encrypt_email("ok@example.com"), 2, confirmed=True
        )
        self._seed_subscribers(
            test_engine, encrypt_email("pending@example.com"), 1, confirmed=False
        )
        counts = ng.send_pending_digests("modelwatch", now=seeded)
        assert counts["sent"] == 2
        assert counts["considered"] == 2  # unconfirmed not even queried
        assert all(m["to"] == "ok@example.com" for m in fake_send)

    def test_idempotent_on_second_run(
        self, seeded, fernet_env, fake_send, test_engine
    ) -> None:
        from engine.handlers.security import encrypt_email

        self._seed_subscribers(test_engine, encrypt_email("ok@example.com"), 1)
        first = ng.send_pending_digests("modelwatch", now=seeded)
        second = ng.send_pending_digests("modelwatch", now=seeded)
        assert first["sent"] == 1
        assert second["sent"] == 0
        assert second["already"] == 1
        assert len(fake_send) == 1

    def test_replaces_unsub_token_per_row(
        self, seeded, fernet_env, fake_send, test_engine
    ) -> None:
        from engine.handlers.security import encrypt_email

        self._seed_subscribers(test_engine, encrypt_email("a@example.com"), 2)
        ng.send_pending_digests("modelwatch", now=seeded)
        unsub_links = [
            m["text_body"].split("/unsubscribe?token=")[1].split()[0]
            for m in fake_send
        ]
        assert "__UNSUB_TOKEN__" not in fake_send[0]["html_body"]
        assert "__UNSUB_TOKEN__" not in fake_send[0]["text_body"]
        assert unsub_links == ["unsub-token-0", "unsub-token-1"]


class TestRenderArchive:
    def test_writes_index_html(
        self, seeded, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import engine.core.newsletter_generator as ng_mod

        monkeypatch.setattr(ng_mod, "DATA_DIR", tmp_path)
        path = ng.render_archive("modelwatch", now=seeded)
        assert path.exists()
        body = path.read_text(encoding="utf-8")
        assert body.startswith("<!doctype html>")
        assert "/digest/" in str(path)

    def test_index_lists_existing_archives(
        self, seeded, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import engine.core.newsletter_generator as ng_mod

        monkeypatch.setattr(ng_mod, "DATA_DIR", tmp_path)
        # Render two weeks first so the index has something to list.
        ng.render_archive("modelwatch", week_offset=0, now=seeded)
        ng.render_archive("modelwatch", week_offset=-1, now=seeded)
        idx = ng.render_digest_index("modelwatch")
        body = idx.read_text(encoding="utf-8")
        assert "2026-W19" in body
        assert "2026-W18" in body
        # Newest first.
        assert body.index("2026-W19") < body.index("2026-W18")

    def test_index_when_empty(
        self, seeded, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import engine.core.newsletter_generator as ng_mod

        monkeypatch.setattr(ng_mod, "DATA_DIR", tmp_path)
        idx = ng.render_digest_index("modelwatch")
        body = idx.read_text(encoding="utf-8")
        assert "No digests published yet" in body

    def test_archive_uses_branded_template(
        self, seeded, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The on-site archive must extend base.html (with nav + footer),
        not the email-styled inline-table body."""
        import engine.core.newsletter_generator as ng_mod

        monkeypatch.setattr(ng_mod, "DATA_DIR", tmp_path)
        path = ng.render_archive("modelwatch", now=seeded)
        body = path.read_text(encoding="utf-8")
        # base.html chrome (nav + footer with /privacy link)
        assert 'data-vertical="modelwatch"' in body
        assert "/privacy" in body
        # Branded class names from digest_archive.html
        assert "digest-stories" in body
        # NOT the email's 600px inline-table layout
        assert 'role="presentation"' not in body
