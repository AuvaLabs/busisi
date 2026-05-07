"""entity.wikidata_id — sameAs link target for AI-citation entity verification

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-07

C5 of the carry-forward. Adds a single nullable column ``wikidata_id`` to the
``entities`` table so the entity-page renderer can emit ``sameAs`` JSON-LD
pointing at the Wikidata QID. AI surfaces (Perplexity, ChatGPT Search,
Google AI Mode) use Wikidata-linked entities to verify claims and to
disambiguate names.

Operator backfill: run a Wikidata lookup over the existing entity slugs
post-migration; the column stays NULL for entities the operator has not
yet curated.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("wikidata_id", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entities", "wikidata_id")
