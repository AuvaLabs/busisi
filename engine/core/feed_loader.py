"""Multi-vertical feed loader.

Loads ``verticals/<vertical_id>/sources.yaml`` and returns a normalised list
of feed dicts. Validation is permissive — invalid entries are skipped with a
warning rather than raising — because one broken row should never block the
whole pipeline. ThreatWatch's ``modules/feed_loader.py`` pattern.

Per-feed schema::

    - url: https://example.com/feed.xml      # required, str
      type: rss                              # rss|atom|jsonfeed (default: rss)
      region: Global                         # geographic tag (default: Global)
      priority_weight: 0.85                  # 0.0–1.0 (default: 0.7)
      refresh_interval: 600                  # seconds (default: 600)
      category_hints: [model-release]        # taxonomy hint (optional)
      parser_overrides: {strip_query: true}  # optional dict

Sources are loaded per-vertical: the same source URL can appear in multiple
verticals' sources.yaml with different priority/category, and the pipeline
treats each occurrence as independent (per-vertical state).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from engine.core.config import vertical_dir

logger = logging.getLogger(__name__)


_DEFAULTS: dict[str, Any] = {
    "type": "rss",
    "region": "Global",
    "priority_weight": 0.7,
    "refresh_interval": 600,
    "category_hints": [],
    "parser_overrides": {},
}


def _validate(feed: Any, source_path: Path) -> bool:
    if not isinstance(feed, dict):
        logger.warning("Skipping non-dict feed entry in %s: %r", source_path, feed)
        return False
    if not feed.get("url") or not isinstance(feed["url"], str):
        logger.warning("Skipping feed missing 'url' in %s: %r", source_path, feed)
        return False
    pw = feed.get("priority_weight")
    if pw is not None and not (isinstance(pw, (int, float)) and 0.0 <= pw <= 1.0):
        logger.warning(
            "Skipping feed with invalid priority_weight in %s: %r", source_path, feed
        )
        return False
    return True


def _normalise(feed: dict[str, Any], vertical_id: str) -> dict[str, Any]:
    out = {**_DEFAULTS, **feed}
    out["vertical_id"] = vertical_id
    out["url"] = str(out["url"]).strip()
    return out


def load_feeds(vertical_id: str) -> list[dict[str, Any]]:
    """Load and normalise the feed list for a vertical."""
    path = vertical_dir(vertical_id) / "sources.yaml"
    return load_feeds_from_file(path, vertical_id=vertical_id)


def load_feeds_from_file(
    path: Path, *, vertical_id: str = "unknown"
) -> list[dict[str, Any]]:
    """Load and normalise feeds from a specific YAML file."""
    if not path.exists():
        logger.warning("sources.yaml not found at %s", path)
        return []
    try:
        with open(path, encoding="utf-8") as fp:
            raw = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        return []

    if not isinstance(raw, list):
        logger.error("%s does not contain a top-level list", path)
        return []

    return [_normalise(feed, vertical_id) for feed in raw if _validate(feed, path)]


def load_feeds_from_files(
    paths: list[Path], *, vertical_id: str = "unknown"
) -> list[dict[str, Any]]:
    """Load feeds from multiple YAML files (e.g. split-by-tier sources)."""
    out: list[dict[str, Any]] = []
    for p in paths:
        out.extend(load_feeds_from_file(p, vertical_id=vertical_id))
    return out
