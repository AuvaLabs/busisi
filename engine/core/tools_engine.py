"""Tools engine — loads + runs per-vertical Python-defined tools.

Each tool is a Python module under ``verticals/<vertical>/tools/<slug>.py``
exposing two top-level objects:

  META = {
      "slug": "llm-cost-calculator",
      "title": "LLM cost calculator",
      "description": "Estimate the cost of running a prompt at scale.",
      "category": "compute",
      "inputs": [
          {"name": "model", "type": "select", "options": [...], "default": ...},
          {"name": "input_tokens", "type": "number", "default": 1000, "min": 0},
          ...
      ],
      "output_format": "USD",
  }

  def calculate(inputs: dict) -> dict:
      ...
      return {"result": cost, "breakdown": [("input cost", in_cost), ...]}

Tools are pure Python (no formula-eval'd YAML) so they are statically
type-checkable, testable, and unit-tested via pytest.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from engine.core.config import vertical_dir

logger = logging.getLogger(__name__)


def _tools_dir(vertical_id: str) -> Path:
    return vertical_dir(vertical_id) / "tools"


def list_tools(vertical_id: str) -> list[dict[str, Any]]:
    """Return META dicts for every tool in the vertical, alphabetised by slug."""
    out: list[dict[str, Any]] = []
    tdir = _tools_dir(vertical_id)
    if not tdir.exists():
        return out
    for path in sorted(tdir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        meta = _load_tool_meta(vertical_id, path)
        if meta is not None:
            out.append(meta)
    return out


def _load_tool_meta(vertical_id: str, path: Path) -> dict[str, Any] | None:
    mod = _load_tool_module(vertical_id, path)
    if mod is None:
        return None
    meta = getattr(mod, "META", None)
    if not isinstance(meta, dict) or "slug" not in meta:
        logger.warning("tool %s has no valid META", path)
        return None
    return dict(meta)


def _load_tool_module(vertical_id: str, path: Path) -> Any | None:
    name = f"verticals.{vertical_id}.tools.{path.stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        logger.warning("could not load tool spec at %s", path)
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        logger.error("error executing tool %s: %s", path, exc)
        sys.modules.pop(name, None)
        return None
    return mod


def get_tool(vertical_id: str, slug: str) -> dict[str, Any] | None:
    """Return a tool by slug: ``{meta, calculate, defaults}``."""
    tdir = _tools_dir(vertical_id)
    if not tdir.exists():
        return None
    for path in tdir.glob("*.py"):
        if path.name.startswith("_"):
            continue
        meta = _load_tool_meta(vertical_id, path)
        if meta is None or meta.get("slug") != slug:
            continue
        mod = _load_tool_module(vertical_id, path)
        if mod is None:
            return None
        defaults = {
            inp["name"]: inp.get("default")
            for inp in meta.get("inputs", [])
            if "default" in inp
        }
        return {
            "meta": meta,
            "calculate": getattr(mod, "calculate", None),
            "defaults": defaults,
        }
    return None


def run_tool(vertical_id: str, slug: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute the tool with the given inputs. Returns ``{result, breakdown}``."""
    tool = get_tool(vertical_id, slug)
    if tool is None or tool["calculate"] is None:
        raise LookupError(f"tool not found: {vertical_id}/{slug}")
    merged = {**tool["defaults"], **inputs}
    return tool["calculate"](merged)
