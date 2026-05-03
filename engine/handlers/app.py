"""FastAPI app composition for the grimoire handler service.

uvicorn entry: ``uvicorn engine.handlers.app:app --host 127.0.0.1 --port 8001``

Caddy reverse-proxies ``/api/*``, ``/confirm``, ``/unsubscribe`` to this
loopback listener. CORS allow-origin is configured per-vertical via
``SITE_ORIGINS``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.core.config import LOG_LEVEL, site_origins
from engine.handlers import sponsors, subscribers, tools

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="grimoire-handler",
    description="Public mutating surface for grimoire (subscribe/sponsor/tools).",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_origins = list(site_origins().values())
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
        allow_credentials=False,
        max_age=600,
    )


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "grimoire-handler"})


app.include_router(subscribers.router)
app.include_router(sponsors.router)
app.include_router(tools.router)
