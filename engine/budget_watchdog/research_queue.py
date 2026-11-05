"""Private research queue validation without publishing draft content."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

QUEUE_STATES = frozenset({"candidate", "evidence_ready", "blocked", "published", "retired"})
MIN_PRIORITY = 1
MAX_PRIORITY = 5


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of text values")
    return value


def _public_package_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "busisi.org"
        and parsed.path.startswith("/data/research/")
        and parsed.path.endswith("/editorial-package.json")
    )


def _validate_queue_item(item: object, identifiers: set[str]) -> None:
    if not isinstance(item, dict):
        raise ValueError("queue item must be an object")
    identifier = _text(item.get("topic_id"), "topic_id")
    if identifier in identifiers:
        raise ValueError(f"duplicate queue topic: {identifier}")
    identifiers.add(identifier)
    _text(item.get("question"), f"{identifier} question")
    status = item.get("status")
    if status not in QUEUE_STATES:
        raise ValueError(f"{identifier} has an unsupported status")
    priority = item.get("priority")
    if (
        not isinstance(priority, int)
        or isinstance(priority, bool)
        or not MIN_PRIORITY <= priority <= MAX_PRIORITY
    ):
        raise ValueError(f"{identifier} priority must be between 1 and 5")
    _text_list(item.get("evidence_sources"), f"{identifier} evidence sources")
    missing = _text_list(item.get("missing_evidence"), f"{identifier} missing evidence")
    if status == "blocked" and not missing:
        raise ValueError(f"{identifier} blocked topic must identify missing evidence")
    package = item.get("published_package_url")
    if status == "published" and not _public_package_url(package):
        raise ValueError(f"{identifier} published topic requires a Busisi package")
    downstream_ready = item.get("downstream_ready")
    if not isinstance(downstream_ready, bool):
        raise ValueError(f"{identifier} downstream readiness must be boolean")
    if downstream_ready and status != "published":
        raise ValueError(f"{identifier} downstream readiness requires publication")
    if downstream_ready and not _public_package_url(package):
        raise ValueError(f"{identifier} downstream package is invalid")


def validate_private_research_queue(queue: dict[str, Any]) -> None:
    """Fail closed when a private topic queue can leak or bypass publication."""

    if queue.get("schema_version") != "1.0":
        raise ValueError("private queue schema version is unsupported")
    if queue.get("public") is True:
        raise ValueError("research queue must remain private")
    try:
        date.fromisoformat(_text(queue.get("updated_at"), "queue updated_at"))
    except ValueError as exc:
        raise ValueError("queue updated_at must be an ISO date") from exc
    items = queue.get("items")
    if not isinstance(items, list):
        raise ValueError("queue items must be a list")
    identifiers: set[str] = set()
    for item in items:
        _validate_queue_item(item, identifiers)


def build_private_queue_receipt(queue: dict[str, Any], source_path: Path) -> dict[str, Any]:
    """Return operational counts without copying private topics or sources."""

    validate_private_research_queue(queue)
    counts = Counter(item["status"] for item in queue["items"])
    return {
        "schema_version": "1.0",
        "updated_at": queue["updated_at"],
        "source": str(source_path),
        "private": True,
        "total": len(queue["items"]),
        "counts": dict(sorted(counts.items())),
        "downstream_ready": sum(item["downstream_ready"] for item in queue["items"]),
    }
