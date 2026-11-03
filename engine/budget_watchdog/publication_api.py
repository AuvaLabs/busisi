"""Isolated read-only API for the reviewed Busisi publication store."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from engine.budget_watchdog.publication_store import (
    MAX_FISCAL_YEAR,
    MAX_QUERY_LIMIT,
    MAX_QUERY_TEXT,
    MIN_FISCAL_YEAR,
    RegisterQuery,
    RegisterQueryError,
    export_register_csv,
    get_project_dossier,
    query_register,
)

MAX_SLUG_LENGTH = 160


class FixedWindowRateLimiter:
    def __init__(self, *, max_requests: int = 120, window_seconds: int = 60) -> None:
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("rate-limit values must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        with self._lock:
            started, count = self._windows.get(key, (now, 0))
            if now - started >= self._window_seconds:
                started, count = now, 0
            if count >= self._max_requests:
                return False
            self._windows[key] = (started, count + 1)
            return True


def _query(
    *,
    q: str,
    year: int | None,
    status: str,
    sort: str,
    limit: int,
    cursor: str | None,
) -> RegisterQuery:
    return RegisterQuery(
        q=q,
        year=year,
        status=status,
        sort=sort,
        limit=limit,
        cursor=cursor,
    )


def _request_query(
    q: str = Query("", max_length=MAX_QUERY_TEXT),
    year: int | None = Query(None, ge=MIN_FISCAL_YEAR, le=MAX_FISCAL_YEAR),
    status: str = Query("all", pattern=r"^(all|reviewed|quarantine)$"),
    sort: str = Query(
        "appropriation_desc",
        pattern=r"^(appropriation_desc|difference_desc|year_desc|title_asc)$",
    ),
    limit: int = Query(25, ge=1, le=MAX_QUERY_LIMIT),
    cursor: str | None = Query(None, max_length=1000),
) -> RegisterQuery:
    return _query(q=q, year=year, status=status, sort=sort, limit=limit, cursor=cursor)


RegisterQueryDependency = Annotated[RegisterQuery, Depends(_request_query)]


def create_app(
    database_path: Path,
    *,
    rate_limiter: FixedWindowRateLimiter | None = None,
) -> FastAPI:
    if not database_path.is_file():
        raise ValueError("database_path must be an existing publication database")
    limiter = rate_limiter or FixedWindowRateLimiter()
    app = FastAPI(
        title="Busisi reviewed records",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def protect(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client = request.client.host if request.client else "unknown"
        response: Response
        if not limiter.allow(client):
            response = JSONResponse({"detail": "too many requests"}, status_code=429)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "public, max-age=60"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(RegisterQueryError)
    async def register_error(_request: Request, exc: RegisterQueryError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "busisi-publication", "read_only": True}

    @app.get("/api/v1/projects")
    def projects(query: RegisterQueryDependency) -> dict[str, object]:
        page = query_register(database_path, query)
        return {
            "meta": {
                "total": page.total,
                "count": len(page.records),
                "limit": query.limit,
                "next_cursor": page.next_cursor,
                "release_scope": "reviewed_golden_set",
            },
            "data": [asdict(record) for record in page.records],
        }

    @app.get("/api/v1/projects.csv")
    def projects_csv(query: RegisterQueryDependency) -> Response:
        document = export_register_csv(database_path, query)
        return Response(
            document,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=busisi-project-records.csv"},
        )

    @app.get("/api/v1/projects/{slug}")
    def project(slug: str) -> dict[str, object]:
        if len(slug) > MAX_SLUG_LENGTH:
            raise HTTPException(status_code=404, detail="project not found")
        dossier = get_project_dossier(database_path, slug)
        if dossier is None:
            raise HTTPException(status_code=404, detail="project not found")
        return {"data": asdict(dossier)}

    return app
