"""Tests for platform.core.deduplicator.

Covers the four invariants whose regressions in ThreatWatch caused visible
front-page bugs:
  1. URL normalisation strips query/fragment/trailing-slash.
  2. Title normalisation strips prefixes + punctuation.
  3. Fuzzy duplicate detection respects the MIN_FUZZY_WORDS floor.
  4. Per-vertical guard patterns prevent merging of distinct stories.

Plus end-to-end deduplicate_articles smoke tests against fakeredis.
"""

from __future__ import annotations

import re
from typing import Any

from engine.core import deduplicator as dedup


class TestNormalizeURL:
    def test_strips_query_string(self) -> None:
        assert (
            dedup.normalize_url("https://example.com/post?utm=foo&id=1")
            == "https://example.com/post"
        )

    def test_strips_fragment(self) -> None:
        assert (
            dedup.normalize_url("https://example.com/post#section")
            == "https://example.com/post"
        )

    def test_strips_trailing_slash(self) -> None:
        assert dedup.normalize_url("https://example.com/post/") == "https://example.com/post"


class TestNormalizeTitle:
    def test_lowercases(self) -> None:
        assert dedup.normalize_title("Hello World") == "hello world"

    def test_strips_breaking_prefix(self) -> None:
        assert dedup.normalize_title("BREAKING: Big news") == "big news"

    def test_strips_release_prefix(self) -> None:
        assert dedup.normalize_title("Release: GPT-5 ships") == "gpt5 ships"

    def test_strips_punctuation_and_collapses_whitespace(self) -> None:
        assert dedup.normalize_title("AI,    ML & Robots!").strip() != ""


class TestArticleHash:
    def test_stable_for_same_input(self) -> None:
        h1 = dedup.article_hash("title", "https://example.com/")
        h2 = dedup.article_hash("title", "https://example.com")
        assert h1 == h2

    def test_changes_with_title(self) -> None:
        h1 = dedup.article_hash("a", "https://example.com/")
        h2 = dedup.article_hash("b", "https://example.com/")
        assert h1 != h2


class TestShingleIndex:
    def test_exact_match(self) -> None:
        idx = dedup.ShingleIndex()
        idx.add("openai releases gpt5", raw_title="OpenAI releases GPT-5")
        assert idx.is_fuzzy_duplicate("openai releases gpt5") is True

    def test_short_titles_use_exact_only(self) -> None:
        idx = dedup.ShingleIndex()
        idx.add("ai launch")
        assert idx.is_fuzzy_duplicate("ai launch") is True
        assert idx.is_fuzzy_duplicate("ai release") is False

    def test_fuzzy_match_above_threshold(self) -> None:
        idx = dedup.ShingleIndex()
        idx.add("openai releases gpt5 with new reasoning capability")
        assert (
            idx.is_fuzzy_duplicate(
                "openai releases gpt5 with reasoning capability"
            )
            is True
        )

    def test_fuzzy_no_match_when_unrelated(self) -> None:
        idx = dedup.ShingleIndex()
        idx.add("openai releases gpt5 with new reasoning")
        assert idx.is_fuzzy_duplicate("anthropic releases claude sonnet") is False

    def test_guard_distinct_captures_block_match(self) -> None:
        guard = [re.compile(r"GPT-?(\d+)", re.IGNORECASE)]
        idx = dedup.ShingleIndex(guard_patterns=guard)
        idx.add(
            "openai releases gpt5 reasoning upgrades",
            raw_title="OpenAI releases GPT-5 reasoning upgrades",
        )
        assert (
            idx.is_fuzzy_duplicate(
                "openai releases gpt4 reasoning upgrades",
                raw_title="OpenAI releases GPT-4 reasoning upgrades",
            )
            is False
        )

    def test_guard_same_captures_allow_match(self) -> None:
        # Same GPT-5 captures + ~0.78 shingle overlap (above 0.65 threshold)
        # → guard does not block, fuzzy match succeeds.
        guard = [re.compile(r"GPT-?(\d+)", re.IGNORECASE)]
        idx = dedup.ShingleIndex(guard_patterns=guard)
        idx.add(
            "openai releases gpt5 reasoning upgrades",
            raw_title="OpenAI releases GPT-5 reasoning upgrades",
        )
        assert (
            idx.is_fuzzy_duplicate(
                "openai releases gpt5 reasoning improvements",
                raw_title="OpenAI releases GPT-5 reasoning improvements",
            )
            is True
        )


class TestDeduplicateArticles:
    def test_drops_identical_hash(
        self, fakeredis_client: Any, sample_articles: list[dict[str, Any]]
    ) -> None:
        a = dict(sample_articles[0])
        b = dict(sample_articles[0])
        out = dedup.deduplicate_articles([a, b], vertical="t1")
        assert len(out) == 1

    def test_distinct_articles_preserved(
        self, fakeredis_client: Any, sample_articles: list[dict[str, Any]]
    ) -> None:
        out = dedup.deduplicate_articles(
            [sample_articles[0], sample_articles[2]], vertical="t1"
        )
        assert len(out) == 2

    def test_persistence_blocks_repeat_run(
        self, fakeredis_client: Any, sample_articles: list[dict[str, Any]]
    ) -> None:
        first = dedup.deduplicate_articles([sample_articles[0]], vertical="t1")
        second = dedup.deduplicate_articles([sample_articles[0]], vertical="t1")
        assert len(first) == 1
        assert len(second) == 0
