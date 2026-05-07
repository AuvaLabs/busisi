"""rewriter schema — Story state, sources, revisions, extracts, llm_calls

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06

R3 of the multi-source rewriter rollout. Schema deltas:

ARTICLES
  + structured_extract  JSON     NULL    Pass 0 per-article extract.
  + extract_version     INTEGER  NOT NULL DEFAULT 0
  + extracted_at        TIMESTAMPTZ NULL

STORIES
  + state               VARCHAR(16) NOT NULL DEFAULT 'draft'
                                        draft|ready|published|revising|archived
  + narrative_version   INTEGER  NOT NULL DEFAULT 0
  + narrative_updated_at TIMESTAMPTZ NULL
  + narrative_model     VARCHAR(128) NULL
  + narrative_word_count INTEGER NULL

NEW TABLES
  story_sources       — one row per cited source per story (citation graph)
  story_revisions     — append-only history of every Story.narrative version
  citation_events     — rolled-up bot citations of a story (fed by R7)
  llm_calls           — append-only audit log for every LLM API call (R2)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- ARTICLES — Pass 0 extract columns ----
    op.add_column(
        "articles",
        sa.Column("structured_extract", sa.JSON(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column(
            "extract_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "articles",
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- STORIES — lifecycle state machine + narrative metadata ----
    op.add_column(
        "stories",
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "narrative_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "narrative_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "stories",
        sa.Column("narrative_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("narrative_word_count", sa.Integer(), nullable=True),
    )

    # ---- NEW TABLES ----
    op.create_table(
        "story_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "story_id",
            sa.BigInteger(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=256), nullable=False),
        sa.Column("agency_class", sa.String(length=1), nullable=False),
        sa.Column("cited_as_n", sa.Integer(), nullable=False),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("story_id", "cited_as_n", name="uq_storysource_n"),
    )
    op.create_index("ix_story_source_story", "story_sources", ["story_id"])

    op.create_table(
        "story_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "story_id",
            sa.BigInteger(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("why_this_matters", sa.Text(), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column("cost_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "reason",
            sa.String(length=32),
            nullable=False,
            server_default="initial",
        ),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("story_id", "version", name="uq_revision_version"),
    )
    op.create_index(
        "ix_revision_story_created",
        "story_revisions",
        ["story_id", "created_at"],
    )

    op.create_table(
        "citation_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "story_id",
            sa.BigInteger(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bot_name", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column(
            "attributed_revenue_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_citation_event_story_ts", "citation_events", ["story_id", "ts"]
    )
    op.create_index(
        "ix_citation_event_bot_ts", "citation_events", ["bot_name", "ts"]
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("caller", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "vertical_id",
            sa.BigInteger(),
            sa.ForeignKey("verticals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "story_id",
            sa.BigInteger(),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_llm_call_vertical_created", "llm_calls", ["vertical_id", "created_at"]
    )
    op.create_index(
        "ix_llm_call_caller_created", "llm_calls", ["caller", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_llm_call_caller_created", table_name="llm_calls")
    op.drop_index("ix_llm_call_vertical_created", table_name="llm_calls")
    op.drop_table("llm_calls")

    op.drop_index("ix_citation_event_bot_ts", table_name="citation_events")
    op.drop_index("ix_citation_event_story_ts", table_name="citation_events")
    op.drop_table("citation_events")

    op.drop_index("ix_revision_story_created", table_name="story_revisions")
    op.drop_table("story_revisions")

    op.drop_index("ix_story_source_story", table_name="story_sources")
    op.drop_table("story_sources")

    op.drop_column("stories", "narrative_word_count")
    op.drop_column("stories", "narrative_model")
    op.drop_column("stories", "narrative_updated_at")
    op.drop_column("stories", "narrative_version")
    op.drop_column("stories", "state")

    op.drop_column("articles", "extracted_at")
    op.drop_column("articles", "extract_version")
    op.drop_column("articles", "structured_extract")
