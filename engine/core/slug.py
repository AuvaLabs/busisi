"""URL-safe slug generation for canonical story paths.

Each persisted article becomes a canonical page at ``/story/<slug>/`` on
the vertical's site. Slugs are derived from the title at persist time and
must be unique per vertical (enforced by the
``uq_article_vertical_slug`` constraint in ``engine.core.db.Article``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_SLUG_KEEP = re.compile(r"[^a-z0-9]+")
_RUN_OF_DASHES = re.compile(r"-{2,}")


def make_slug(title: str, *, max_len: int = 80) -> str:
    """Return a URL-safe slug for a title.

    NFKD-normalises Unicode (so "Modèle" -> "modele"), lowercases, replaces
    every non-alphanumeric run with a dash, trims edges, caps at max_len.
    Always returns at least one character (falls back to "article" for
    inputs that produce an empty slug after normalisation).
    """
    if not title:
        return "article"
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    slug = _SLUG_KEEP.sub("-", lowered)
    slug = _RUN_OF_DASHES.sub("-", slug).strip("-")
    if not slug:
        return "article"
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def make_unique_slug(
    session: Any,
    vertical_id: int,
    base_slug: str,
    *,
    article_model: Any | None = None,
) -> str:
    """Resolve slug collisions by appending -2, -3, ... within a vertical."""
    if article_model is None:
        from engine.core.db import Article

        article_model = Article
    from sqlalchemy import select

    candidate = base_slug
    suffix = 1
    while True:
        existing = session.execute(
            select(article_model.id).where(
                article_model.vertical_id == vertical_id,
                article_model.slug == candidate,
            )
        ).first()
        if existing is None:
            return candidate
        suffix += 1
        candidate = f"{base_slug}-{suffix}"
