from pathlib import Path

import pytest
from ops.harness.budget_watchdog_research_queue import initial_queue

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


def test_private_queue_accepts_a_bounded_comparison_plan() -> None:
    queue = _queue()
    queue["items"][1]["comparison_plan"] = {
        "article_format": "question-led-v1",
        "reader_value": "Shows whether recorded spending matches a documented public need.",
        "peer_places": ["Indonesia", "Malaysia", "Thailand", "Vietnam"],
        "measures": ["classrooms per 1,000 enrolled learners"],
        "normalization": ["per 1,000 enrolled learners"],
        "same_year_required": True,
        "release_requirements": [
            "Official Philippine need measure",
            "Official or multilateral comparison series",
            "Matching definitions and reference years",
        ],
    }

    validate_private_research_queue(queue)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("reader_value", "", "reader value"),
        ("article_format", "fixed-template-v1", "article format"),
        ("peer_places", [""], "peer places"),
        ("measures", [], "measures"),
        ("normalization", "per person", "normalization"),
        ("same_year_required", "yes", "same-year"),
        ("release_requirements", [], "release requirements"),
    ],
)
def test_private_queue_rejects_an_unbounded_comparison_plan(
    field: str, value: object, message: str
) -> None:
    queue = _queue()
    queue["items"][1]["comparison_plan"] = {
        "article_format": "question-led-v1",
        "reader_value": "Shows whether recorded spending matches a documented public need.",
        "peer_places": ["Indonesia"],
        "measures": ["people exposed to flooding"],
        "normalization": ["pesos per exposed resident"],
        "same_year_required": True,
        "release_requirements": ["Official source files"],
    }
    queue["items"][1]["comparison_plan"][field] = value

    with pytest.raises(ValueError, match=message):
        validate_private_research_queue(queue)


def test_initial_queue_contains_the_approved_needs_and_country_pilots() -> None:
    queue = initial_queue()

    validate_private_research_queue(queue)
    topics = {item["topic_id"]: item for item in queue["items"]}
    expected = {
        "community-projects-versus-local-needs",
        "flood-control-versus-exposure",
        "classroom-gap-asean-comparison",
        "project-trail-country-comparison",
    }

    assert expected <= topics.keys()
    for topic_id in expected:
        topic = topics[topic_id]
        assert topic["status"] == "blocked"
        assert topic["missing_evidence"]
        assert topic["comparison_plan"]["article_format"] == "question-led-v1"
        assert topic["comparison_plan"]["release_requirements"]
        assert topic["downstream_ready"] is False


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
