"""curator schema + research_bundles + article_feedback

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04

Adds five columns to ``articles`` for the editorial curator (Phase 22a)
and creates two new tables that ride alongside it for later phases:

  articles.curator_score      FLOAT NULL
  articles.curator_tier       VARCHAR(16) NULL
  articles.curator_signals    JSONB NULL
  articles.curator_version    INT NOT NULL DEFAULT 0
  articles.researched_at      TIMESTAMPTZ NULL

  research_bundles            (Phase 22e — researcher output)
  article_feedback            (Phase 22g — reader-submitted issues)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles", sa.Column("curator_score", sa.Float(), nullable=True)
    )
    op.add_column(
        "articles",
        sa.Column("curator_tier", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "articles", sa.Column("curator_signals", sa.JSON(), nullable=True)
    )
    op.add_column(
        "articles",
        sa.Column(
            "curator_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "articles",
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "research_bundles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=256), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("ord", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_research_bundle_article", "research_bundles", ["article_id"]
    )

    op.create_table(
        "article_feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reporter_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("issue_kind", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_feedback_article_created",
        "article_feedback",
        ["article_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_article_created", table_name="article_feedback")
    op.drop_table("article_feedback")
    op.drop_index("ix_research_bundle_article", table_name="research_bundles")
    op.drop_table("research_bundles")
    op.drop_column("articles", "researched_at")
    op.drop_column("articles", "curator_version")
    op.drop_column("articles", "curator_signals")
    op.drop_column("articles", "curator_tier")
    op.drop_column("articles", "curator_score")
