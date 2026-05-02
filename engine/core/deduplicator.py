"""Word-shingle deduplicator with per-vertical guards.

Algorithm ported verbatim from ``modules/deduplicator.py`` in ThreatWatch
(HEAD fffecca). Two grimoire-specific changes:

1. **Persistence layer is Redis** (sorted sets ``dedup:<vertical>:hashes``
   and ``dedup:<vertical>:titles``, score = unix epoch seconds). Rolling
   7-day window enforced with ``ZREMRANGEBYSCORE … now-604800``.
2. **Generalised dedup-guard** instead of ThreatWatch's hard-coded CVE
   guard. Per-vertical regex list (``non_dedup_keys``) loaded from
   ``verticals/<name>/config.yaml``: when two candidate titles each yield
   matches but the captured sets differ, they are treated as distinct
   stories regardless of shingle similarity.

Performance target (per BUILD-DIRECTIVE Phase 2): dedup 10K articles in
<30s. The inverted-index design hits that comfortably.

See ``docs/architecture-derivation.md`` §5 for the algorithmic write-up.
"""

from __future__ import annotations

import hashlib
import logging
import re
import string
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

from engine.core.config import (
    FUZZY_DEDUP_THRESHOLD,
    MAX_SEEN_HASHES,
    MAX_SEEN_TITLES,
    REDIS_URL,
)

logger = logging.getLogger(__name__)


_STRIP_TABLE = str.maketrans("", "", string.punctuation)
_PREFIXES = (
    "breaking:",
    "update:",
    "exclusive:",
    "just in:",
    "alert:",
    "release:",
    "paper:",
    "report:",
    "filing:",
)
_MIN_FUZZY_WORDS = 3
_ROLLING_WINDOW_SECONDS = 7 * 24 * 3600

_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "has", "have", "had", "that", "this", "it", "its",
        "as", "not", "no",
    }
)


def normalize_url(url: str) -> str:
    """Strip query params, fragments, and trailing slashes."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))


def normalize_title(title: str) -> str:
    text = title.lower().strip()
    for prefix in _PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    text = text.translate(_STRIP_TABLE)
    return " ".join(text.split())


def article_hash(title: str, link: str) -> str:
    """SHA256 of (title + normalised URL)."""
    return hashlib.sha256((title + normalize_url(link)).encode()).hexdigest()


def _make_word_shingles(normalized: str) -> frozenset[str]:
    words = [w for w in normalized.split() if w not in _STOP_WORDS]
    if not words:
        return frozenset()
    shingles: set[str] = set(words)
    for i in range(len(words) - 1):
        shingles.add(f"{words[i]} {words[i + 1]}")
    return frozenset(shingles)


def _word_overlap_ratio(set_a: frozenset[str], set_b: frozenset[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    smaller = min(len(set_a), len(set_b))
    return intersection / smaller if smaller > 0 else 0.0


class ShingleIndex:
    """Inverted index using word bigram shingles for fast fuzzy dedup."""

    def __init__(self, guard_patterns: list[re.Pattern[str]] | None = None) -> None:
        self._shingle_to_indices: dict[str, list[int]] = {}
        self._title_shingles: list[frozenset[str]] = []
        self._normalized_titles: list[str] = []
        self._raw_titles: list[str] = []
        self._word_counts: list[int] = []
        self._guard_patterns: list[re.Pattern[str]] = guard_patterns or []

    def __len__(self) -> int:
        return len(self._normalized_titles)

    def add(self, normalized_title: str, raw_title: str | None = None) -> int:
        idx = len(self._normalized_titles)
        shingles = _make_word_shingles(normalized_title)
        word_count = len([w for w in normalized_title.split() if w not in _STOP_WORDS])
        self._title_shingles.append(shingles)
        self._normalized_titles.append(normalized_title)
        self._raw_titles.append(raw_title or normalized_title)
        self._word_counts.append(word_count)
        for s in shingles:
            self._shingle_to_indices.setdefault(s, []).append(idx)
        return idx

    def _incoming_word_count(self, normalized_title: str) -> int:
        return len([w for w in normalized_title.split() if w not in _STOP_WORDS])

    def _guard_captures(self, raw_title: str) -> set[str]:
        captures: set[str] = set()
        for pat in self._guard_patterns:
            for m in pat.findall(raw_title):
                captures.add(m if isinstance(m, str) else "".join(m))
        return {c.upper() for c in captures}

    def is_fuzzy_duplicate(
        self,
        normalized_title: str,
        raw_title: str | None = None,
        threshold: float = FUZZY_DEDUP_THRESHOLD,
    ) -> bool:
        shingles = _make_word_shingles(normalized_title)
        if self._incoming_word_count(normalized_title) < _MIN_FUZZY_WORDS:
            return normalized_title in self._normalized_titles

        incoming_caps = self._guard_captures(raw_title or normalized_title)
        candidate_set: set[int] = set()
        for s in shingles:
            for idx in self._shingle_to_indices.get(s, ()):
                candidate_set.add(idx)

        for idx in candidate_set:
            existing = self._normalized_titles[idx]
            if normalized_title == existing:
                return True
            if self._word_counts[idx] < _MIN_FUZZY_WORDS:
                continue
            existing_caps = self._guard_captures(self._raw_titles[idx])
            if (incoming_caps or existing_caps) and incoming_caps != existing_caps:
                continue
            similarity = _word_overlap_ratio(shingles, self._title_shingles[idx])
            if similarity >= threshold:
                logger.info(
                    "Fuzzy duplicate (%.2f): %r ~ %r", similarity, normalized_title, existing
                )
                return True
        return False

    def find_best_match_index(
        self,
        normalized_title: str,
        start_idx: int,
        raw_title: str | None = None,
        threshold: float = FUZZY_DEDUP_THRESHOLD,
    ) -> int:
        shingles = _make_word_shingles(normalized_title)
        if self._incoming_word_count(normalized_title) < _MIN_FUZZY_WORDS:
            return -1

        incoming_caps = self._guard_captures(raw_title or normalized_title)
        candidate_set: set[int] = set()
        for s in shingles:
            for idx in self._shingle_to_indices.get(s, ()):
                if idx >= start_idx:
                    candidate_set.add(idx)

        best_score = -1.0
        best_idx = -1
        for idx in candidate_set:
            existing = self._normalized_titles[idx]
            if normalized_title == existing:
                return idx - start_idx
            if self._word_counts[idx] < _MIN_FUZZY_WORDS:
                continue
            existing_caps = self._guard_captures(self._raw_titles[idx])
            if (incoming_caps or existing_caps) and incoming_caps != existing_caps:
                continue
            similarity = _word_overlap_ratio(shingles, self._title_shingles[idx])
            if similarity >= threshold and similarity > best_score:
                best_score = similarity
                best_idx = idx
        return best_idx - start_idx if best_idx >= 0 else -1


def _redis() -> Any | None:
    try:
        from redis import Redis

        return Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.debug("Redis unavailable for dedup persistence: %s", exc)
        return None


def _hashes_key(vertical: str) -> str:
    return f"dedup:{vertical}:hashes"


def _titles_key(vertical: str) -> str:
    return f"dedup:{vertical}:titles"


def _load_seen(vertical: str) -> tuple[list[str], set[str], list[str]]:
    client = _redis()
    if client is None:
        return [], set(), []
    cutoff = time.time() - _ROLLING_WINDOW_SECONDS
    try:
        client.zremrangebyscore(_hashes_key(vertical), "-inf", cutoff)
        client.zremrangebyscore(_titles_key(vertical), "-inf", cutoff)
        hashes = list(client.zrange(_hashes_key(vertical), 0, -1))
        titles = list(client.zrange(_titles_key(vertical), 0, -1))
        return hashes, set(hashes), titles
    except Exception as exc:
        logger.warning("dedup persistence load failed: %s", exc)
        return [], set(), []


def _persist_new(vertical: str, new_hashes: list[str], new_titles: list[str]) -> None:
    client = _redis()
    if client is None or (not new_hashes and not new_titles):
        return
    now = time.time()
    try:
        if new_hashes:
            client.zadd(_hashes_key(vertical), {h: now for h in new_hashes})
            current = client.zcard(_hashes_key(vertical))
            excess = current - MAX_SEEN_HASHES
            if excess > 0:
                client.zremrangebyrank(_hashes_key(vertical), 0, excess - 1)
        if new_titles:
            client.zadd(_titles_key(vertical), {t: now for t in new_titles})
            current = client.zcard(_titles_key(vertical))
            excess = current - MAX_SEEN_TITLES
            if excess > 0:
                client.zremrangebyrank(_titles_key(vertical), 0, excess - 1)
    except Exception as exc:
        logger.warning("dedup persistence write failed: %s", exc)


def _add_related(
    unique: list[dict[str, Any]],
    duplicate: dict[str, Any],
    index: ShingleIndex,
    dup_normalized: str,
    dup_raw_title: str,
    batch_start_idx: int,
) -> None:
    match_offset = index.find_best_match_index(
        dup_normalized, batch_start_idx, raw_title=dup_raw_title
    )
    if 0 <= match_offset < len(unique):
        original = unique[match_offset]
        related = list(original.get("related_articles", []))
        related.append(
            {
                "title": duplicate["title"],
                "link": duplicate["link"],
                "source": duplicate.get("source", ""),
            }
        )
        original["related_articles"] = related


def deduplicate_articles(
    articles: list[dict[str, Any]],
    *,
    vertical: str = "default",
    guard_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Deduplicate articles within a batch and against the rolling window."""
    compiled_guards = [re.compile(p, re.IGNORECASE) for p in (guard_patterns or [])]

    _hashes_ordered, seen_hashes, seen_titles = _load_seen(vertical)
    index = ShingleIndex(guard_patterns=compiled_guards)
    for t in seen_titles:
        index.add(normalize_title(t), raw_title=t)

    batch_start_idx = len(index)
    new_hashes: list[str] = []
    new_titles: list[str] = []
    unique: list[dict[str, Any]] = []
    hash_to_idx: dict[str, int] = {}

    for raw_article in articles:
        article = {**raw_article}
        h = article.get("hash") or article_hash(article["title"], article["link"])
        article["hash"] = h

        if h in seen_hashes:
            logger.debug("Hash duplicate skipped: %s", article["link"])
            continue

        raw_title = article["title"]
        normalized = normalize_title(raw_title)

        if index.is_fuzzy_duplicate(normalized, raw_title=raw_title):
            logger.info("Fuzzy duplicate skipped: %s", raw_title)
            _add_related(unique, article, index, normalized, raw_title, batch_start_idx)
            index.add(normalized, raw_title=raw_title)
            seen_hashes.add(h)
            new_hashes.append(h)
            new_titles.append(raw_title)
            continue

        hash_to_idx[h] = len(unique)
        unique.append(article)
        index.add(normalized, raw_title=raw_title)
        seen_hashes.add(h)
        new_hashes.append(h)
        new_titles.append(raw_title)

    _persist_new(vertical, new_hashes, new_titles)
    logger.info(
        "Dedup [%s]: %d input -> %d unique (%d removed)",
        vertical,
        len(articles),
        len(unique),
        len(articles) - len(unique),
    )
    return unique
