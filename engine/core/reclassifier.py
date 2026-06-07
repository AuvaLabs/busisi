"""Re-classify already-stored articles against the current taxonomy.

The keyword taxonomy in ``verticals/<v>/config.yaml`` drifts as patterns are
tuned (e.g. tightening an over-broad ``\\bwill\\b`` that mislabelled general
news as estate-planning). The pipeline only classifies at fetch time, so stored
``Article.labels`` go stale. This backfill re-runs the **keyword** classifier
over existing rows and rewrites ``labels`` where they changed.

LLM escalation is disabled (``escalation_budget=0``) so the pass is free,
fast, and deterministic — exactly what a relabel sweep wants. When a row's
labels change, its ``curator_version`` is reset to 0 so the next curator run
re-scores it against the corrected topic relevance (see curator.py v2 gate).

CLI::

    python -m engine.core.reclassifier vested [--max 100000] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

import yaml
from sqlalchemy import select

from engine.core import classifier
from engine.core.config import vertical_dir
from engine.core.db import Article, Vertical, get_sessionmaker

logger = logging.getLogger(__name__)


def _load_taxonomy(vertical_name: str) -> dict[str, list[str]]:
    """Read ``topics`` from ``verticals/<v>/config.yaml``. {} on miss."""
    path = vertical_dir(vertical_name) / "config.yaml"
    if not path.exists():
        logger.warning("config.yaml missing for %s at %s", vertical_name, path)
        return {}
    with open(path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    topics = data.get("topics", {}) if isinstance(data, dict) else {}
    return topics or {}


def _load_title_anchored(vertical_name: str) -> frozenset[str]:
    """Read ``classifier.title_anchored_topics`` from config. Empty on miss."""
    path = vertical_dir(vertical_name) / "config.yaml"
    if not path.exists():
        return frozenset()
    with open(path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    block = data.get("classifier", {}) if isinstance(data, dict) else {}
    return frozenset((block or {}).get("title_anchored_topics", []) or [])


def _label_key(labels: Any) -> list[tuple[str, int]]:
    """Normalise a labels list to a comparable [(name, confidence)] sorted."""
    out: list[tuple[str, int]] = []
    for item in labels or []:
        if isinstance(item, dict) and item.get("label"):
            try:
                conf = int(item.get("confidence", 0) or 0)
            except (TypeError, ValueError):
                conf = 0
            out.append((str(item["label"]), conf))
        elif isinstance(item, str) and item.strip():
            out.append((item.strip(), 0))
    return sorted(out)


def reclassify_vertical(
    vertical_name: str,
    *,
    max_articles: int = 100_000,
    taxonomy: dict[str, list[str]] | None = None,
    title_anchored: frozenset[str] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Keyword-reclassify a vertical's stored articles. Returns counts.

    Only rows whose labels actually change are written; changed rows have
    ``curator_version`` reset to 0 so the curator re-scores them.
    """
    if taxonomy is None:
        taxonomy = _load_taxonomy(vertical_name)
    if title_anchored is None:
        title_anchored = _load_title_anchored(vertical_name)
    counts = {
        "considered": 0,
        "changed": 0,
        "now_labeled": 0,
        "now_unlabeled": 0,
    }
    if not taxonomy:
        logger.warning("[%s] no taxonomy — nothing to reclassify", vertical_name)
        return counts

    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        ids = (
            session.execute(
                select(Article.id)
                .where(Article.vertical_id == v.id, Article.deleted_at.is_(None))
                .order_by(Article.fetched_at.desc())
                .limit(max_articles)
            )
            .scalars()
            .all()
        )

    for aid in ids:
        with SessionLocal() as session:
            article = session.get(Article, aid)
            if article is None:
                continue
            counts["considered"] += 1
            result = classifier.classify_article(
                title=article.title,
                content=article.summary or None,
                taxonomy=taxonomy,
                vertical=vertical_name,
                always_escalate=[],
                escalation_budget=0,  # keyword-only — free + deterministic
                title_anchored=title_anchored,
            )
            new_labels = result["labels"]
            had = bool(_label_key(article.labels))
            has = bool(_label_key(new_labels))
            if _label_key(article.labels) == _label_key(new_labels):
                continue
            counts["changed"] += 1
            if has and not had:
                counts["now_labeled"] += 1
            elif had and not has:
                counts["now_unlabeled"] += 1
            if not dry_run:
                article.labels = new_labels
                # Force the curator to re-score against the corrected labels.
                article.curator_version = 0
                session.commit()

    logger.info("[%s] reclassify: %s", vertical_name, counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.reclassifier vested [--max N] [--dry-run]``"""
    parser = argparse.ArgumentParser(
        description="Keyword-reclassify stored articles against the current taxonomy"
    )
    parser.add_argument("vertical")
    parser.add_argument("--max", type=int, default=100_000, dest="max_articles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing labels / resetting curator_version",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    counts = reclassify_vertical(
        args.vertical, max_articles=args.max_articles, dry_run=args.dry_run
    )
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
