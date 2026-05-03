"""Tests for /api/tools/{vertical}/{slug}/calculate."""

from __future__ import annotations


class TestToolsCalc:
    def test_happy_path(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={
                "inputs": {
                    "model": "claude-sonnet-4-5",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "requests_per_day": 1000,
                }
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "result" in body
        assert "headline" in body
        assert "breakdown" in body

    def test_unknown_tool_404(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/no-such-tool/calculate",
            json={"inputs": {}},
        )
        assert r.status_code == 404

    def test_unknown_vertical_404(self, client) -> None:
        r = client.post(
            "/api/tools/ghost/llm-cost-calculator/calculate",
            json={"inputs": {}},
        )
        assert r.status_code == 404

    def test_invalid_select_value(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={"inputs": {"model": "fake-model"}},
        )
        assert r.status_code == 422

    def test_below_min(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={"inputs": {"input_tokens": -5}},
        )
        assert r.status_code == 422

    def test_non_numeric_for_number_field(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={"inputs": {"input_tokens": "lots"}},
        )
        assert r.status_code == 422

    def test_non_dict_inputs(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={"inputs": [1, 2, 3]},
        )
        assert r.status_code == 422

    def test_invalid_json(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400

    def test_defaults_fill_missing_inputs(self, client) -> None:
        r = client.post(
            "/api/tools/modelwatch/llm-cost-calculator/calculate",
            json={"inputs": {}},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
