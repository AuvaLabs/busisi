"""Tests for engine.core.reclassifier — keyword relabel backfill."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import engine.core.db as db_module
from engine.core import reclassifier as rc
from engine.core.db import Article, Base, Vertical


TAXONOMY = {
    "taxes": [r"\bIRS\b", r"\b401\(k\)\b"],
    # tightened estate-planning: no bare \bwill\b
    "estate-planning": [r"\b(last will|living will)\b"],
}


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


def _seed(test_engine, *, title, summary, labels, version=1) -> int:
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        v = s.execute(
            select(Vertical).where(Vertical.name == "vested")
        ).scalar_one_or_none()
        if v is None:
            v = Vertical(name="vested", display_name="Vested")
            s.add(v)
            s.commit()
            s.refresh(v)
        a = Article(
            vertical_id=v.id,
            hash=f"h-{title[:24]}",
            slug=f"s-{title[:24]}".replace(" ", "-").lower(),
            title=title,
            link="https://example.com/x",
            source="https://example.com/feed",
            feed_region="US",
            summary=summary,
            summary_source="feed",
            labels=labels,
            curator_version=version,
            published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id


def _get(test_engine, aid):
    SM = sessionmaker(test_engine, future=True)
    with SM() as s:
        return s.get(Article, aid)


def test_relabels_and_resets_version(test_engine) -> None:
    aid = _seed(
        test_engine,
        title="401(k) limits rise next year",
        summary="The IRS announced higher caps.",
        labels=[{"label": "estate-planning", "confidence": 42}],  # stale/wrong
    )
    counts = rc.reclassify_vertical("vested", taxonomy=TAXONOMY)
    assert counts["changed"] == 1
    a = _get(test_engine, aid)
    names = {l["label"] for l in a.labels}
    assert names == {"taxes"}
    assert a.curator_version == 0  # marked for re-score


def test_offtopic_becomes_unlabeled(test_engine) -> None:
    aid = _seed(
        test_engine,
        title="Energy bills will rise by £200 in July",
        summary="Forecasters say prices will climb.",
        labels=[{"label": "estate-planning", "confidence": 42}],  # bogus \bwill\b match
    )
    counts = rc.reclassify_vertical("vested", taxonomy=TAXONOMY)
    assert counts["changed"] == 1
    assert counts["now_unlabeled"] == 1
    a = _get(test_engine, aid)
    assert a.labels == []
    assert a.curator_version == 0


def test_unchanged_preserves_version(test_engine) -> None:
    aid = _seed(
        test_engine,
        title="401(k) limits rise next year",
        summary="The IRS announced higher caps.",
        labels=[{"label": "estate-planning", "confidence": 42}],
    )
    rc.reclassify_vertical("vested", taxonomy=TAXONOMY)  # first pass relabels -> v0
    # bump version, then re-run; labels already correct -> no change, version kept
    SM = sessionmaker(test_engine, expire_on_commit=False, future=True)
    with SM() as s:
        a = s.get(Article, aid)
        a.curator_version = 5
        s.commit()
    counts = rc.reclassify_vertical("vested", taxonomy=TAXONOMY)
    assert counts["changed"] == 0
    assert _get(test_engine, aid).curator_version == 5


def test_dry_run_does_not_write(test_engine) -> None:
    aid = _seed(
        test_engine,
        title="Energy bills will rise by £200",
        summary="prices will climb",
        labels=[{"label": "estate-planning", "confidence": 42}],
    )
    counts = rc.reclassify_vertical("vested", taxonomy=TAXONOMY, dry_run=True)
    assert counts["changed"] == 1
    a = _get(test_engine, aid)
    assert a.labels == [{"label": "estate-planning", "confidence": 42}]  # untouched
    assert a.curator_version == 1


def test_unknown_vertical_empty(test_engine) -> None:
    assert rc.reclassify_vertical("ghost", taxonomy=TAXONOMY)["considered"] == 0
