"""baseline — full schema as defined by engine.core.db.Base

Revision ID: 0001
Revises:
Create Date: 2026-05-04

This is the alembic head as of grimoire's V1 launch. The schema was
historically built via ``Base.metadata.create_all()`` plus two manual
ALTER TABLE statements:

  * subscribers.last_digest_sent_at  (Phase 10b)
  * articles.entities_extracted_at   (Phase 14a)

Both are now part of the model definitions, so a fresh deploy that
runs ``alembic upgrade head`` lands at the same shape that production
has today. ``upgrade()`` calls ``Base.metadata.create_all`` directly:

  * idempotent — existing tables are skipped (CREATE TABLE IF NOT EXISTS
    semantics via SQLAlchemy's ``checkfirst=True`` default);
  * matches reality — production was stamped to ``head`` after this
    revision landed, so re-running it is a no-op there.

Future schema changes use ``alembic revision --autogenerate -m "…"``
which diffs the live DB against the model metadata.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from engine.core.db import Base

    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from engine.core.db import Base

    Base.metadata.drop_all(op.get_bind())
