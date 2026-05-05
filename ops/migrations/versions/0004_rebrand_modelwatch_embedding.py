"""rename vertical: modelwatch → embedding (The Embedding Report)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-05

V1 brand commit. Real domain `embedding.report` registered; old slug
`modelwatch` renamed to `embedding` so file-system, DB, output dir,
Caddy site block, and bot-log path all align on the new slug.

Vested unchanged.

Foreign keys reference verticals.id (BigInt PK), not the name slug, so
the rename is safe — no FK fixup required. The slug is consumed only
where it's read by name (config.yaml lookup, output dir, bot_log_parser
default log path).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE verticals
        SET name = 'embedding',
            display_name = 'The Embedding Report',
            description = 'Grounded coverage of AI/ML — first-party announcements, research, regulation, tooling.'
        WHERE name = 'modelwatch'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE verticals
        SET name = 'modelwatch',
            display_name = 'Modelwatch',
            description = 'Real-time AI/ML knowledge platform — news, reference, research, tools.'
        WHERE name = 'embedding'
        """
    )
