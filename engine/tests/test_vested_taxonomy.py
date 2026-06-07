"""Guards the Vested finance taxonomy (verticals/vested/config.yaml `topics`).

The relevance gate skips any article the classifier gives no topic label, so a
taxonomy that misses real finance (macro/markets/fiscal) silently drops good
stories — and one that over-matches admits noise. These tests pin both edges
against the LIVE config, plus the `\\b401\\(k\\)` regex fix (the trailing `\\b`
made it miss the bare "401(k)" token).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from engine.core.classifier import _keyword_classify

_CONFIG = Path(__file__).resolve().parents[2] / "verticals" / "vested" / "config.yaml"
TAXONOMY: dict[str, list[str]] = yaml.safe_load(_CONFIG.read_text())["topics"]


def _labels(title: str, content: str = "") -> set[str]:
    return {d["label"] for d in _keyword_classify(title, content, TAXONOMY)}


class TestMacroMarketsFiscalLanes:
    """Macro/policy/markets finance must earn a label (was scoring zero)."""

    def test_inflation_and_fed_are_macro(self) -> None:
        assert "macro-economy" in _labels("Inflation cooled to 2.3% in May")
        assert "macro-economy" in _labels("The Fed holds interest rates steady")
        assert "macro-economy" in _labels(
            "Risk Sharing in the Federal Reserve's Emergency Lending Facilities"
        )

    def test_indices_and_ipo_are_markets(self) -> None:
        assert "markets" in _labels("Nasdaq slides as the bond market rallies")
        assert "markets" in _labels("Why the SpaceX IPO Will Affect Your 401(k)")

    def test_budget_and_entitlements_are_fiscal(self) -> None:
        assert "fiscal-policy" in _labels("CBO scores the federal deficit impact")
        assert "fiscal-policy" in _labels("Social Security trust fund outlook dims")


class TestNoFalsePositives:
    """Genuinely off-topic items must stay unlabeled → skipped by the gate."""

    def test_lifestyle_and_general_news_unlabeled(self) -> None:
        for title in (
            "Are You Watching? review - unflinching, fury-filled drama",
            "Pass the chakalaka! The best World Cup drinks and snacks",
            "Universal park officially named as government pledges 1.3bn",
            "Federal agency X accounts are getting far more engagement",
        ):
            assert _labels(title) == set(), title


class TestRegexFixes:
    """The 401(k) token must match in plain prose, not only '401(k)s'."""

    def test_401k_plain_token_matches(self) -> None:
        labels = _labels("How to max out your 401(k) plan this year")
        assert {"taxes", "retirement-planning"} & labels
