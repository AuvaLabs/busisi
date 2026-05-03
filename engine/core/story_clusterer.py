"""Multi-source story clusterer.

Groups articles whose titles describe the same underlying event so the
front page can show "5 sources covering this" instead of 5 individual
cards. Reuses the word-shingle scaffolding from ``deduplicator``:

  * normalize titles (strip prefixes, punctuation, stop words)
  * compute bigram word shingles
  * pairwise smaller-set overlap (Jaccard-with-min)

Clustering uses a higher-recall threshold than the deduper's exact-dup
guard — different headlines about the same event share roughly 40-60%
of significant tokens, while exact dups share 65%+.

Idempotency: a cluster is persisted only if NONE of its members are
already in an existing Story. Re-running over the same window is a
no-op once the window has been fully clustered.

Phase 11a ships clustering + persistence only. Front-page card
collapsing is Phase 11b.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from engine.core.db import (
    Article,
    Story,
    StoryArticle,
    Vertical,
    get_sessionmaker,
)
from engine.core.deduplicator import (
    _make_word_shingles,
    _word_overlap_ratio,
    normalize_title,
)

logger = logging.getLogger(__name__)


_CLUSTER_THRESHOLD = 0.30
# Above this size, a cluster is almost always shared-boilerplate noise
# (Reddit "Re:" threads, recurring weekly columns) rather than a real
# multi-source event. Better entity extraction will let us raise this.
_MAX_CLUSTER_SIZE = 8
_DEFAULT_DAYS = 7


class _UnionFind:
    """Path-compressed union-find with rank merging."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _candidate_articles(
    session, vertical_id: int, since: datetime
) -> list[Article]:
    return list(
        session.execute(
            select(Article)
            .where(
                Article.vertical_id == vertical_id,
                Article.published_at.is_not(None),
                Article.published_at >= since,
                Article.deleted_at.is_(None),
            )
            .order_by(Article.published_at.asc())
        )
        .scalars()
        .all()
    )


def _already_clustered(session, article_ids: list[int]) -> set[int]:
    if not article_ids:
        return set()
    rows = (
        session.execute(
            select(StoryArticle.article_id).where(
                StoryArticle.article_id.in_(article_ids)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _build_clusters(articles: list[Article]) -> list[list[int]]:
    """Return clusters of indices into ``articles`` (size >= 2 only)."""
    if not articles:
        return []

    shingles: list[frozenset[str]] = [
        _make_word_shingles(normalize_title(a.title)) for a in articles
    ]
    inverted: dict[str, list[int]] = defaultdict(list)
    for idx, sh in enumerate(shingles):
        for token in sh:
            inverted[token].append(idx)

    uf = _UnionFind(len(articles))
    seen_pairs: set[tuple[int, int]] = set()
    for token, idxs in inverted.items():
        if len(idxs) < 2:
            continue
        for i, a in enumerate(idxs):
            for b in idxs[i + 1 :]:
                key = (a, b) if a < b else (b, a)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                if _word_overlap_ratio(shingles[a], shingles[b]) >= _CLUSTER_THRESHOLD:
                    uf.union(a, b)

    grouped: dict[int, list[int]] = defaultdict(list)
    for i in range(len(articles)):
        grouped[uf.find(i)].append(i)
    return [
        members
        for members in grouped.values()
        if 2 <= len(members) <= _MAX_CLUSTER_SIZE
    ]


def cluster_articles(
    vertical_name: str, *, days: int = _DEFAULT_DAYS, now: datetime | None = None
) -> list[list[int]]:
    """Return clusters of article *ids* (size >= 2) inside the window.

    Articles already linked to an existing Story are excluded so re-runs
    only consider fresh candidates.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return []
        articles = _candidate_articles(session, v.id, since)
        if not articles:
            return []
        already = _already_clustered(session, [a.id for a in articles])
        free_articles = [a for a in articles if a.id not in already]
        clusters = _build_clusters(free_articles)
        return [[free_articles[i].id for i in members] for members in clusters]


def _canonical_member(session, article_ids: list[int]) -> Article:
    rows = list(
        session.execute(
            select(Article)
            .where(Article.id.in_(article_ids))
            .order_by(Article.published_at.asc(), Article.id.asc())
        )
        .scalars()
        .all()
    )
    return rows[0]


def persist_clusters(
    vertical_name: str, clusters: list[list[int]]
) -> dict[str, int]:
    """Insert one Story + StoryArticle rows per cluster, skipping any whose
    members are already linked to a Story (idempotent)."""
    counts = {
        "clusters": len(clusters),
        "stories_created": 0,
        "links_created": 0,
        "skipped": 0,
    }
    if not clusters:
        return counts
    SessionLocal = get_sessionmaker()
    with SessionLocal() as session:
        v = session.execute(
            select(Vertical).where(Vertical.name == vertical_name)
        ).scalar_one_or_none()
        if v is None:
            return counts
        for member_ids in clusters:
            already = _already_clustered(session, member_ids)
            if already:
                counts["skipped"] += 1
                continue
            primary = _canonical_member(session, member_ids)
            story = Story(
                vertical_id=v.id,
                canonical_headline=primary.title,
                primary_published_at=primary.published_at or datetime.now(timezone.utc),
                importance=round(math.log(len(member_ids) + 1), 4),
            )
            session.add(story)
            session.flush()
            for aid in member_ids:
                session.add(
                    StoryArticle(
                        story_id=story.id,
                        article_id=aid,
                        is_primary=(aid == primary.id),
                    )
                )
            session.commit()
            counts["stories_created"] += 1
            counts["links_created"] += len(member_ids)
    return counts


def cluster_and_persist(
    vertical_name: str, *, days: int = _DEFAULT_DAYS, now: datetime | None = None
) -> dict[str, int]:
    clusters = cluster_articles(vertical_name, days=days, now=now)
    return persist_clusters(vertical_name, clusters)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m engine.core.story_clusterer modelwatch [--days 7]``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cluster articles into multi-source stories"
    )
    parser.add_argument("vertical", help="Vertical id (e.g. modelwatch)")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS)
    parser.add_argument(
        "--dry-run", action="store_true", help="Cluster but don't persist"
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.dry_run:
        clusters = cluster_articles(args.vertical, days=args.days)
        print(f"clusters: {len(clusters)}")
        for c in clusters:
            preview = ", ".join(str(x) for x in c[:5])
            ellipsis = "..." if len(c) > 5 else ""
            print(f"  - {len(c)} articles: [{preview}{ellipsis}]")
        return 0

    counts: dict[str, Any] = cluster_and_persist(args.vertical, days=args.days)
    print(f"clusters considered: {counts['clusters']}")
    print(f"stories created:     {counts['stories_created']}")
    print(f"article links:       {counts['links_created']}")
    print(f"skipped (already):   {counts['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
