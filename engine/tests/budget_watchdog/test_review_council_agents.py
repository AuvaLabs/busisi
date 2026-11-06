import pytest

from engine.budget_watchdog.review_council_agents import extract_json, token_usage


def test_extracts_structured_verdict_from_plain_and_wrapped_output() -> None:
    payload = '{"schema_version":1,"decision":"confirm"}'
    assert extract_json(payload)["decision"] == "confirm"
    wrapped = '{"type":"result","result":"{\\"decision\\":\\"unclear\\"}"}'
    assert extract_json(wrapped)["decision"] == "unclear"
    fenced = 'Result:\n```json\n{"decision":"reject","note":"a } brace"}\n```'
    assert extract_json(fenced)["decision"] == "reject"
    nested = '• ```json\n{"decision":"confirm","finding":{"decision":"reject"}}\n```'
    assert extract_json(nested)["decision"] == "confirm"


def test_rejects_output_without_a_json_object() -> None:
    with pytest.raises(ValueError, match="does not contain"):
        extract_json("no structured verdict")


def test_reads_available_token_usage_without_inventing_missing_values() -> None:
    usage = token_usage(
        {
            "usage": {
                "input_tokens": 1200,
                "cache_read_input_tokens": 800,
                "output_tokens": 300,
            }
        }
    )
    assert usage == {
        "input_tokens": 1200,
        "cached_input_tokens": 800,
        "cache_write_input_tokens": None,
        "output_tokens": 300,
        "reasoning_tokens": None,
    }
    assert token_usage({}) == {
        "input_tokens": None,
        "cached_input_tokens": None,
        "cache_write_input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
    }
    assert token_usage(
        {
            "usage": {
                "cached_input_tokens": 4,
                "cache_creation_input_tokens": 9,
                "input_tokens": True,
                "output_tokens_details": {"thinking_tokens": 3},
            }
        }
    ) == {
        "input_tokens": None,
        "cached_input_tokens": 4,
        "cache_write_input_tokens": 9,
        "output_tokens": None,
        "reasoning_tokens": 3,
    }
