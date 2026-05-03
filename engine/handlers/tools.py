"""Tool calculator route.

POST /api/tools/{vertical}/{slug}/calculate
  body: {"inputs": {...}}
  returns: {"ok": true, ...tool_result}

Tool modules + their input schemas live under
``verticals/<vertical>/tools/*.py`` and are resolved via the existing
``engine.core.tools_engine`` runner. No DB writes — pure compute.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from engine.core import tools_engine
from engine.handlers.security import rate_limit_hit

logger = logging.getLogger(__name__)
router = APIRouter()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _coerce_inputs(
    meta_inputs: list[dict[str, Any]], raw: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in meta_inputs:
        name = spec.get("name")
        if not name:
            continue
        kind = spec.get("type", "text")
        value = raw.get(name, spec.get("default"))
        if kind == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422, detail=f"input {name!r} must be a number"
                ) from None
            lo = spec.get("min")
            hi = spec.get("max")
            if lo is not None and value < lo:
                raise HTTPException(
                    status_code=422, detail=f"{name} below min ({lo})"
                )
            if hi is not None and value > hi:
                raise HTTPException(
                    status_code=422, detail=f"{name} above max ({hi})"
                )
        elif kind == "select":
            options = [
                opt.get("value", opt) if isinstance(opt, dict) else opt
                for opt in spec.get("options", [])
            ]
            if value not in options:
                raise HTTPException(
                    status_code=422, detail=f"{name} must be one of {options}"
                )
        elif kind == "bool":
            value = bool(value)
        elif kind == "text":
            value = str(value or "")[:512]
        out[name] = value
    return out


@router.post("/api/tools/{vertical}/{slug}/calculate")
async def calculate(
    request: Request,
    vertical: str,
    slug: str,
) -> JSONResponse:
    ip = _client_ip(request)
    if not rate_limit_hit("tools", ip):
        raise HTTPException(status_code=429, detail="too many requests")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None

    inputs_raw = payload.get("inputs") if isinstance(payload, dict) else None
    if not isinstance(inputs_raw, dict):
        raise HTTPException(status_code=422, detail="inputs must be an object")

    tool = tools_engine.get_tool(vertical, slug)
    if tool is None or tool["calculate"] is None:
        raise HTTPException(status_code=404, detail="tool not found")

    coerced = _coerce_inputs(tool["meta"].get("inputs", []), inputs_raw)
    merged = {**tool["defaults"], **coerced}

    try:
        result = tool["calculate"](merged)
    except Exception as exc:
        logger.exception("tool %s/%s raised: %s", vertical, slug, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from None

    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="tool returned non-dict")
    return JSONResponse({"ok": True, **result})


__all__ = ["router"]
