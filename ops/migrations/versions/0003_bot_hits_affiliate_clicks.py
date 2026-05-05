"""bot_hits + affiliate_clicks

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-05

Adds two telemetry tables:

  bot_hits          (Phase P1B2 — Caddy log parser; AI-citation telemetry)
  affiliate_clicks  (Phase P1 affiliate infra — /r/<partner>/<slug> redirect)

Both retain only sha256-peppered IP hashes; no PII.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_hits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "vertical_id",
            sa.BigInteger(),
            sa.ForeignKey("verticals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bot_name", sa.String(length=64), nullable=False),
        sa.Column("ua", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_bot_hit_vertical_ts", "bot_hits", ["vertical_id", "ts"]
    )
    op.create_index("ix_bot_hit_bot_ts", "bot_hits", ["bot_name", "ts"])

    op.create_table(
        "affiliate_clicks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "vertical_id",
            sa.BigInteger(),
            sa.ForeignKey("verticals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("partner", sa.String(length=64), nullable=False),
        sa.Column(
            "slug",
            sa.String(length=256),
            nullable=False,
            server_default="",
        ),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_affiliate_click_vertical_ts",
        "affiliate_clicks",
        ["vertical_id", "ts"],
    )
    op.create_index(
        "ix_affiliate_click_partner_ts",
        "affiliate_clicks",
        ["partner", "ts"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_affiliate_click_partner_ts", table_name="affiliate_clicks"
    )
    op.drop_index(
        "ix_affiliate_click_vertical_ts", table_name="affiliate_clicks"
    )
    op.drop_table("affiliate_clicks")
    op.drop_index("ix_bot_hit_bot_ts", table_name="bot_hits")
    op.drop_index("ix_bot_hit_vertical_ts", table_name="bot_hits")
    op.drop_table("bot_hits")
