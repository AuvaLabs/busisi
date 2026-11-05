from pathlib import Path

import pytest

from engine.budget_watchdog.research_queue import (
    build_private_queue_receipt,
    validate_private_research_queue,
)


def _queue() -> dict:
    return {
        "schema_version": "1.0",
        "updated_at": "2026-11-05",
        "items": [
            {
                "topic_id": "published-story",
                "question": "What changed?",
                "status": "published",
                "priority": 1,
                "evidence_sources": ["https://busisi.org/sources/"],
                "missing_evidence": [],
                "target_slug": "published-story",
                "published_package_url": "https://busisi.org/data/research/published-story/v1/editorial-package.json",
                "downstream_ready": True,
            },
            {
                "topic_id": "later-stage-trail",
                "question": "Did a proposal survive later stages?",
                "status": "blocked",
                "priority": 2,
                "evidence_sources": [],
                "missing_evidence": ["Senate and bicameral documents"],
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
        ],
    }


def test_private_queue_validates_and_emits_a_content_free_receipt() -> None:
    queue = _queue()
    validate_private_research_queue(queue)

    receipt = build_private_queue_receipt(queue, Path("private/queue.json"))

    assert receipt["total"] == 2
    assert receipt["counts"] == {"blocked": 1, "published": 1}
    assert receipt["downstream_ready"] == 1
    assert "question" not in str(receipt)
    assert "Senate" not in str(receipt)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicate"),
        ("public", "private"),
        ("priority", "priority"),
        ("blocked_without_gap", "missing evidence"),
        ("published_without_package", "package"),
        ("ready_without_publication", "downstream"),
    ],
)
def test_private_queue_fails_closed(mutation: str, message: str) -> None:
    queue = _queue()
    item = queue["items"][1]
    if mutation == "duplicate":
        queue["items"].append({**item})
    elif mutation == "public":
        queue["public"] = True
    elif mutation == "priority":
        item["priority"] = 0
    elif mutation == "blocked_without_gap":
        item["missing_evidence"] = []
    elif mutation == "published_without_package":
        queue["items"][0]["published_package_url"] = None
    else:
        item["downstream_ready"] = True

    with pytest.raises(ValueError, match=message):
        validate_private_research_queue(queue)
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("schema", "schema"),
        ("date", "ISO date"),
        ("items", "items"),
        ("item", "object"),
        ("topic", "topic_id"),
        ("question", "question"),
        ("status", "status"),
        ("boolean_priority", "priority"),
        ("sources", "evidence sources"),
        ("readiness", "readiness"),
    ],
)
def test_private_queue_rejects_malformed_boundaries(mutation: str, message: str) -> None:
    queue = _queue()
    item = queue["items"][1]
    if mutation == "schema":
        queue["schema_version"] = "2.0"
    elif mutation == "date":
        queue["updated_at"] = "not-a-date"
    elif mutation == "items":
        queue["items"] = {}
    elif mutation == "item":
        queue["items"] = ["draft"]
    elif mutation == "topic":
        item["topic_id"] = ""
    elif mutation == "question":
        item["question"] = None
    elif mutation == "status":
        item["status"] = "approved"
    elif mutation == "boolean_priority":
        item["priority"] = True
    elif mutation == "sources":
        item["evidence_sources"] = [""]
    else:
        item["downstream_ready"] = "no"

    with pytest.raises(ValueError, match=message):
        validate_private_research_queue(queue)
