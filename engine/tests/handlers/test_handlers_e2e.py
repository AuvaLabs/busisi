"""End-to-end FastAPI tests over the assembled handler app."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from engine.core.db import SponsorInquiry, Subscriber


def _session(engine):
    return sessionmaker(engine, expire_on_commit=False, future=True)()


# ---- /healthz ---------------------------------------------------------------


def test_healthz(client) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "service": "grimoire-handler"}


# ---- /api/subscribe + /confirm + /unsubscribe -------------------------------


class TestSubscribeFlow:
    def test_first_subscribe_sends_confirmation(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        r = client.post(
            "/api/subscribe",
            data={"email": "alice@example.com", "vertical": "modelwatch", "hp": ""},
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "status": "confirmation_sent"}
        assert len(fake_email_send) == 1
        msg = fake_email_send[0]
        assert msg["to"] == "alice@example.com"
        assert "/confirm?token=" in msg["text_body"]

        with _session(test_engine) as s:
            sub = s.execute(select(Subscriber)).scalar_one()
            assert sub.confirmed is False
            assert sub.unsubscribed_at is None
            assert sub.email_encrypted != "alice@example.com"

    def test_repeat_unconfirmed_resends(
        self, client, fake_email_send: list[dict[str, Any]]
    ) -> None:
        client.post(
            "/api/subscribe",
            data={"email": "bob@example.com", "vertical": "modelwatch", "hp": ""},
        )
        r2 = client.post(
            "/api/subscribe",
            data={"email": "bob@example.com", "vertical": "modelwatch", "hp": ""},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "confirmation_sent"
        assert len(fake_email_send) == 2

    def test_already_confirmed_short_circuits(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        client.post(
            "/api/subscribe",
            data={"email": "carol@example.com", "vertical": "modelwatch", "hp": ""},
        )
        with _session(test_engine) as s:
            sub = s.execute(select(Subscriber)).scalar_one()
            sub.confirmed = True
            s.commit()
        sent_before = len(fake_email_send)
        r = client.post(
            "/api/subscribe",
            data={"email": "carol@example.com", "vertical": "modelwatch", "hp": ""},
        )
        assert r.json()["status"] == "already_confirmed"
        assert len(fake_email_send) == sent_before

    def test_invalid_email_rejected(self, client) -> None:
        r = client.post(
            "/api/subscribe",
            data={"email": "not-an-email", "vertical": "modelwatch", "hp": ""},
        )
        assert r.status_code == 422

    def test_unknown_vertical_404(self, client) -> None:
        r = client.post(
            "/api/subscribe",
            data={"email": "alice@example.com", "vertical": "ghost", "hp": ""},
        )
        assert r.status_code == 404

    def test_honeypot_silently_succeeds(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        r = client.post(
            "/api/subscribe",
            data={
                "email": "bot@example.com",
                "vertical": "modelwatch",
                "hp": "trapped",
            },
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "status": "queued"}
        with _session(test_engine) as s:
            assert s.execute(select(Subscriber)).first() is None
        assert fake_email_send == []

    def test_confirm_then_unsubscribe(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        client.post(
            "/api/subscribe",
            data={"email": "dan@example.com", "vertical": "modelwatch", "hp": ""},
        )
        confirm_url = next(
            line.strip()
            for line in fake_email_send[0]["text_body"].splitlines()
            if "/confirm?token=" in line
        )
        token = confirm_url.split("token=", 1)[1]

        rc = client.get(f"/confirm?token={token}", follow_redirects=False)
        assert rc.status_code == 200
        assert "confirmed" in rc.text.lower()

        with _session(test_engine) as s:
            sub = s.execute(select(Subscriber)).scalar_one()
            assert sub.confirmed is True
            unsub_token = sub.unsubscribe_token

        ru = client.get(f"/unsubscribe?token={unsub_token}", follow_redirects=False)
        assert ru.status_code == 200
        assert "unsubscribed" in ru.text.lower()

        with _session(test_engine) as s:
            sub = s.execute(select(Subscriber)).scalar_one()
            assert sub.unsubscribed_at is not None

    def test_confirm_invalid_token(self, client) -> None:
        r = client.get("/confirm?token=garbage", follow_redirects=False)
        assert r.status_code == 400

    def test_unsubscribe_unknown_token(self, client) -> None:
        r = client.get(
            "/unsubscribe?token=does-not-exist", follow_redirects=False
        )
        assert r.status_code == 404


# ---- /api/sponsor -----------------------------------------------------------


class TestSponsorFlow:
    def test_happy_path(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        r = client.post(
            "/api/sponsor",
            data={
                "name": "Acme Corp",
                "email": "biz@example.com",
                "vertical": "modelwatch",
                "company": "Acme",
                "budget_band": "5k_25k",
                "message": "Interested in newsletter sponsorship.",
                "hp": "",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "received"
        assert isinstance(body["id"], int)

        with _session(test_engine) as s:
            inquiry = s.execute(select(SponsorInquiry)).scalar_one()
            assert inquiry.name == "Acme Corp"
            assert inquiry.budget_band == "5k_25k"
            assert inquiry.email == "biz@example.com"

        assert len(fake_email_send) == 1
        notify = fake_email_send[0]
        assert notify["reply_to"] == "biz@example.com"
        assert "Acme Corp" in notify["subject"]

    def test_missing_name_rejected(self, client) -> None:
        r = client.post(
            "/api/sponsor",
            data={
                "name": "   ",
                "email": "biz@example.com",
                "vertical": "modelwatch",
            },
        )
        assert r.status_code == 422

    def test_invalid_email_rejected(self, client) -> None:
        r = client.post(
            "/api/sponsor",
            data={
                "name": "Acme",
                "email": "not-an-email",
                "vertical": "modelwatch",
            },
        )
        assert r.status_code == 422

    def test_unknown_budget_normalised(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        r = client.post(
            "/api/sponsor",
            data={
                "name": "Acme",
                "email": "biz@example.com",
                "vertical": "modelwatch",
                "budget_band": "wat",
            },
        )
        assert r.status_code == 200
        with _session(test_engine) as s:
            inquiry = s.execute(select(SponsorInquiry)).scalar_one()
            assert inquiry.budget_band == "custom"

    def test_honeypot(
        self, client, fake_email_send: list[dict[str, Any]], test_engine
    ) -> None:
        r = client.post(
            "/api/sponsor",
            data={
                "name": "BotCo",
                "email": "bot@example.com",
                "vertical": "modelwatch",
                "hp": "trapped",
            },
        )
        assert r.status_code == 200
        with _session(test_engine) as s:
            assert s.execute(select(SponsorInquiry)).first() is None
        assert fake_email_send == []
