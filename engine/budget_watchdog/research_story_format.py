"""Validation for the human-edited, question-led research story format."""

from __future__ import annotations

from typing import Any

QUESTION_LED_FORMAT = "question-led-v1"
MAX_FINDING_SECTIONS = 4
EDITORIAL_ROLES = frozenset({"short_answer", "finding", "comparison", "limits"})
GENERIC_BODY_HEADINGS = frozenset(
    {
        "analysis",
        "comparison",
        "findings",
        "how comparable places or countries differ",
        "what communities need",
        "what philippine records show",
        "why it matters",
    }
)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of text values")
    if not allow_empty and not value:
        raise ValueError(f"{label} must not be empty")
    return value


def _validate_method_summary(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("question-led method summary must be an object")
    _text(value.get("question_definition"), "question definition")
    _text_list(value.get("reference_years"), "reference years")
    _text_list(value.get("units"), "units")
    _text_list(value.get("denominators"), "denominators", allow_empty=True)


def _validate_next_checks(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("question-led story must identify at least one next check")
    for position, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"next check {position} must be an object")
        _text(item.get("office"), f"next check {position} office")
        _text(item.get("record"), f"next check {position} record")
        question = _text(item.get("question"), f"next check {position} question")
        if not question.endswith("?"):
            raise ValueError(f"next check {position} question must end with a question mark")


def _validate_sections(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("question-led story must contain sections")

    headings: set[str] = set()
    roles: list[str] = []
    for position, section in enumerate(value, start=1):
        if not isinstance(section, dict):
            raise ValueError(f"question-led section {position} must be an object")
        role = _text(section.get("editorial_role"), f"section {position} editorial role")
        if role not in EDITORIAL_ROLES:
            raise ValueError(f"section {position} has an unsupported editorial role")
        roles.append(role)

        heading = _text(section.get("heading"), f"section {position} heading")
        normalized = heading.casefold()
        if normalized in headings:
            raise ValueError("question-led section headings must be unique")
        headings.add(normalized)
        if role in {"finding", "comparison"} and normalized in GENERIC_BODY_HEADINGS:
            raise ValueError(f"question-led story uses a generic heading: {heading}")

    if roles[0] != "short_answer" or value[0].get("heading") != "The short answer":
        raise ValueError("question-led story must begin with The short answer")
    if roles.count("short_answer") != 1:
        raise ValueError("question-led story requires exactly one short answer")
    finding_count = roles.count("finding")
    if not 1 <= finding_count <= MAX_FINDING_SECTIONS:
        raise ValueError("question-led story requires one to four finding sections")
    if roles.count("comparison") > 1:
        raise ValueError("question-led story allows at most one comparison section")
    if roles.count("limits") != 1 or roles[-1] != "limits":
        raise ValueError("question-led story must end with one limits section")


def validate_question_led_story(story: dict[str, Any]) -> None:
    """Validate the optional format used by new public research articles."""

    editorial_format = story.get("editorial_format")
    if editorial_format is None:
        return
    if editorial_format != QUESTION_LED_FORMAT:
        raise ValueError("editorial story format is unsupported")

    headline = _text(story.get("headline"), "question headline")
    if not headline.endswith("?"):
        raise ValueError("question headline must end with a question mark")
    _validate_method_summary(story.get("method_summary"))
    _validate_next_checks(story.get("next_checks"))
    _validate_sections(story.get("sections"))
