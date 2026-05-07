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
    # Set by entity_extractor on success. NULL = still pending, so backfill
    # batches don't re-pay LLM cost on rows we already processed.
    entities_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Curator (Phase 22a): editorial-value gate.
    #   tier ∈ {"skip","standard","researcher"}; score ∈ [0,1];
    #   signals is the per-rule contribution dict;
    #   version bumps when rules change so rows can be re-scored.
    curator_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    curator_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    curator_signals: Mapped[Any] = mapped_column(JSON, nullable=True)
    curator_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    # Set after researcher bundle is persisted (Phase 22e+).
    researched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # R3 — Pass 0 per-article structured extract (rewriter input).
    # JSON shape: {lead_claim, key_facts[], numerics[], entities[], quotes[]}.
    # Re-extracted when extract_version < module-level EXTRACT_VERSION.
    structured_extract: Mapped[Any] = mapped_column(JSON, nullable=True)
    extract_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

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
    # R3 — Story lifecycle state machine.
    #   draft       just clustered; awaiting ripeness check
    #   ready       ≥2 A/B/C sources + cooldown elapsed; queued for rewriter
    #   published   narrative committed and rendered
    #   revising    new A/B/C source joined post-publish; queued for rewrite
    #   archived    24h elapsed since last revision; no more rewrites
    state: Mapped[str] = mapped_column(
        String(16), default="draft", server_default="draft", nullable=False
    )
    narrative_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    narrative_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    narrative_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    narrative_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
    # C5 — Wikidata QID (e.g. "Q5", "Q42") for AI-citation entity verification.
    # Operator populates manually or via batch lookup; null until backfilled.
    wikidata_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


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
    # Set after a digest send succeeds. Comparison against the digest's
    # ``week_start`` provides per-row idempotency without a separate send-log
    # table — sufficient for the weekly cadence.
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


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


class ResearchBundle(Base):
    """Web/scholar/news entries fetched by the researcher (Phase 22e).

    Each row is one supporting document for the rewriter to ground on.
    The bundle is article-scoped; a single Article can have multiple
    rows ordered by ``ord``. Snapshot fields (``excerpt``, ``sha256``)
    let us reaudit later even if the source URL mutates.
    """

    __tablename__ = "research_bundles"
    __table_args__ = (
        Index("ix_research_bundle_article", "article_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ord: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ArticleFeedback(Base):
    """Reader-submitted issue reports (Phase 22g).

    Lets readers flag bad calls (missing context, wrong claim, not news)
    so the curator can be tuned. ``reporter_ip_hash`` is sha256-peppered
    to enable rate-limit grouping without retaining the raw IP.
    """

    __tablename__ = "article_feedback"
    __table_args__ = (
        Index("ix_feedback_article_created", "article_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    reporter_ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BotHit(Base):
    """Recorded crawler hit — populated by the Caddy log parser.

    One row per bot request to a public surface. Used to measure who's
    actually citing us (Perplexity, ChatGPT Search, Google AI Overviews,
    etc.) and to feed Publisher-Program / TollBit / Cloudflare-PPC
    applications. ``ip_hash`` is sha256-peppered.
    """

    __tablename__ = "bot_hits"
    __table_args__ = (
        Index("ix_bot_hit_vertical_ts", "vertical_id", "ts"),
        Index("ix_bot_hit_bot_ts", "bot_name", "ts"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bot_name: Mapped[str] = mapped_column(String(64), nullable=False)
    ua: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AffiliateClick(Base):
    """Recorded affiliate-link click — populated by the /r/<partner>/<slug>
    redirect handler. Used to attribute conversions and audit partner
    performance without depending on third-party trackers. ``ip_hash`` is
    sha256-peppered for rate-limit grouping.
    """

    __tablename__ = "affiliate_clicks"
    __table_args__ = (
        Index("ix_affiliate_click_vertical_ts", "vertical_id", "ts"),
        Index("ix_affiliate_click_partner_ts", "partner", "ts"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    vertical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    partner: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class StorySource(Base):
    """One row per cited source per story (R3).

    The rewriter writes one row per `[N]` reference in the narrative.
    `cited_as_n` is the integer that appears inline in the narrative
    (`[1]`, `[2]`, ...). `article_id` is set when the cited source is one
    of the cluster members; `source_url` always populated for downstream
    rendering even when the original Article is later deleted.
    `snapshot_sha256` holds the body hash at citation time (R7+).

    Validator invariants enforced at write time (research_writer.py):
      - agency_class ∈ {A,B,C,D,E}; F is rejected as primary citation;
        G is removed at the source-list level so cannot reach here.
      - UNIQUE(story_id, cited_as_n) — one [N] resolves to one source.
    """

    __tablename__ = "story_sources"
    __table_args__ = (
        UniqueConstraint("story_id", "cited_as_n", name="uq_storysource_n"),
        Index("ix_story_source_story", "story_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    story_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    agency_class: Mapped[str] = mapped_column(String(1), nullable=False)
    cited_as_n: Mapped[int] = mapped_column(Integer, nullable=False)
    article_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StoryRevision(Base):
    """Append-only history of every Story.narrative version (R3).

    A new row is written each time the rewriter commits a narrative
    (initial publish, revision-on-new-source, manual override).
    Provides audit trail and lets the renderer expose a `?v=2` URL
    parameter for diff viewing later.
    """

    __tablename__ = "story_revisions"
    __table_args__ = (
        UniqueConstraint("story_id", "version", name="uq_revision_version"),
        Index("ix_revision_story_created", "story_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    story_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    why_this_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[Any] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # initial | new_source | manual | model_change | retry
    reason: Mapped[str] = mapped_column(
        String(32), default="initial", server_default="initial", nullable=False
    )
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CitationEvent(Base):
    """Rolled-up bot citations of a specific story (R3, fed by R7).

    The Caddy log parser writes raw `bot_hits` rows; an R7 rollup job
    resolves bot_hits whose path matches `/story/<slug>/` to a story_id
    and writes one CitationEvent per (story, bot, day) bucket.
    `attributed_revenue_cents` is populated later by the
    Cloudflare-Pay-Per-Crawl / TollBit / Comet Plus reconciliation.
    """

    __tablename__ = "citation_events"
    __table_args__ = (
        Index("ix_citation_event_story_ts", "story_id", "ts"),
        Index("ix_citation_event_bot_ts", "bot_name", "ts"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    story_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    bot_name: Mapped[str] = mapped_column(String(64), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributed_revenue_cents: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class LLMCall(Base):
    """Append-only audit log for every LLM API call (R2).

    Records caller, resolved model id, token counts, concurrency cost units,
    and the article/story it served. Used by the daily cost guardrail and
    the harness audit to detect rewrite-storms or premium-model leakage.

    Append-only: no UPDATE path. Failed calls also recorded (``error``
    column populated, ``output_tokens`` may be 0).
    """

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_call_vertical_created", "vertical_id", "created_at"),
        Index("ix_llm_call_caller_created", "caller", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    caller: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    vertical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verticals.id", ondelete="SET NULL"), nullable=True
    )
    story_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    article_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Featherless concurrency-unit cost (1u, 2u, or 4u). Distinct from $ cost
    # which is irrelevant on Featherless's reservation-of-capacity plan.
    cost_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


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
