"""Postgres schema (SQLAlchemy 2.0 ORM) — multi-tenant content store.

Per BUILD-DIRECTIVE Phase 1 ("Schema multi-tenant: vertical_id column on all
content tables") and architecture-derivation §4 (Postgres replaces TW's
SQLite + JSON state because grimoire needs join-style queries for
cross-source clustering and engagement attribution).

All `*_at` columns are timezone-aware UTC. Migrations live under
``ops/migrations/`` (Alembic) and are owned by the operator workflow.

Tables (Phase 2/3 minimum-viable set):

  verticals          — tenant registry
  articles           — fetched + cleaned items (vertical_id-scoped)
  stories            — clusters of articles representing a single event
  story_articles     — many-to-many; an article belongs to one story
  entities           — typed registry (lab, model, person, ...)
  article_entities   — many-to-many

Phase 4 will add:

  subscribers        — newsletter signups
  pro_users          — Stripe-backed paid tier
  engagement_events  — channel-by-channel metrics
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from engine.core.config import DATABASE_URL


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base."""


class Vertical(Base):
    __tablename__ = "verticals"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    accent_light: Mapped[str | None] = mapped_column(String(16), nullable=True)
    accent_dark: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="vertical")


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("vertical_id", "hash", name="uq_article_vertical_hash"),
        UniqueConstraint("vertical_id", "slug", name="uq_article_vertical_slug"),
        Index("ix_article_vertical_published", "vertical_id", "published_at"),
        Index("ix_article_vertical_fetched", "vertical_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    feed_region: Mapped[str] = mapped_column(String(32), default="Global", nullable=False)
    # Holds the auto-generated/grounded summary that becomes the body of OUR
    # canonical /story/<slug>/ page. Falls back to feed-provided summary
    # (summary_source="feed") until the LLM enrichment stage runs.
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # `body` is the trafilatura-cleaned scrape, kept as the grounding source
    # for the LLM summariser; not rendered directly to readers.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 1-2-sentence analysis caption (LLM-generated, marked as analysis on the
    # rendered page). Nullable until LLM tier runs.
    why_this_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tracks how `summary` was produced so the rendered page can banner
    # appropriately. Values: "feed" | "llm" | "manual".
    summary_source: Mapped[str] = mapped_column(
        String(16), default="feed", nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    labels: Mapped[Any] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vertical: Mapped[Vertical] = relationship(back_populates="articles")


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_story_vertical_primary", "vertical_id", "primary_published_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    canonical_headline: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_this_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    importance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StoryArticle(Base):
    __tablename__ = "story_articles"
    story_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("vertical_id", "type", "slug", name="uq_entity_slug"),
        Index("ix_entity_vertical_type", "vertical_id", "type"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ArticleEntity(Base):
    __tablename__ = "article_entities"
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )


# ---- Phase 4 monetization tables ----


class Subscriber(Base):
    """Newsletter subscriber. Email is pseudonymised via SHA256 hash (lookup) +
    Fernet-encrypted blob (delivery). Plaintext never sits at rest."""

    __tablename__ = "subscribers"
    __table_args__ = (
        UniqueConstraint("vertical_id", "email_hash", name="uq_subscriber_email_hash"),
        Index("ix_subscriber_vertical_confirmed", "vertical_id", "confirmed"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    email_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProUser(Base):
    """Stripe-backed Pro tier subscriber. Magic-link auth (single-use 15-min tokens)."""

    __tablename__ = "pro_users"
    __table_args__ = (
        UniqueConstraint("vertical_id", "email", name="uq_pro_user_email"),
        Index("ix_pro_user_stripe_customer", "stripe_customer_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="incomplete", nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SponsorInquiry(Base):
    """Inbound sponsorship inquiry from /sponsorship form."""

    __tablename__ = "sponsor_inquiries"
    __table_args__ = (
        Index("ix_sponsor_inquiry_vertical_created", "vertical_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    company: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    budget_band: Mapped[str] = mapped_column(String(16), default="custom", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False, future=True)


def create_all() -> None:
    """Create the schema (Phase-2 dev convenience; Phase 6 uses Alembic)."""
    Base.metadata.create_all(get_engine())
