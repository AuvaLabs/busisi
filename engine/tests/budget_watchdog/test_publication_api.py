from pathlib import Path

from fastapi.testclient import TestClient

from engine.budget_watchdog.publication_api import FixedWindowRateLimiter, create_app
from engine.budget_watchdog.publication_store import build_publication_store

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_TOO_MANY_REQUESTS = 429
FY2024 = 2024
FY2024_RECORDS = 2
CSV_LINE_COUNT = 3


def _client(tmp_path, *, request_limit: int = 100) -> TestClient:
    database = tmp_path / "publication.sqlite3"
    build_publication_store(GOLDEN_PATH, database)
    app = create_app(
        database,
        rate_limiter=FixedWindowRateLimiter(max_requests=request_limit, window_seconds=60),
    )
    return TestClient(app)


def test_projects_endpoint_filters_and_paginates(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/projects", params={"year": FY2024, "limit": 1})

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["meta"]["total"] == FY2024_RECORDS
    assert body["meta"]["next_cursor"]
    assert len(body["data"]) == 1
    assert body["data"][0]["fiscal_year"] == FY2024


def test_project_dossier_and_not_found(tmp_path) -> None:
    with _client(tmp_path) as client:
        found = client.get("/api/v1/projects/corazon-2024-phase-1")
        missing = client.get("/api/v1/projects/not-present")

    assert found.status_code == HTTP_OK
    assert found.json()["data"]["contract_id"] == "24HI0148"
    assert missing.status_code == HTTP_NOT_FOUND
    assert missing.json() == {"detail": "project not found"}


def test_csv_endpoint_generates_filtered_download(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/projects.csv", params={"year": FY2024})

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"] == "attachment; filename=busisi-project-records.csv"
    )
    assert response.text.count("\n") == CSV_LINE_COUNT


def test_api_rate_limit_and_security_headers(tmp_path) -> None:
    with _client(tmp_path, request_limit=1) as client:
        first = client.get("/api/v1/projects")
        limited = client.get("/api/v1/projects")

    assert first.status_code == HTTP_OK
    assert first.headers["x-content-type-options"] == "nosniff"
    assert limited.status_code == HTTP_TOO_MANY_REQUESTS
    assert limited.json() == {"detail": "too many requests"}


def test_api_rejects_invalid_filter_and_cursor(tmp_path) -> None:
    with _client(tmp_path) as client:
        invalid_filter = client.get("/api/v1/projects", params={"status": "accused"})
        invalid_cursor = client.get(
            "/api/v1/projects",
            params={"cursor": "not-a-valid-cursor"},
        )

    assert invalid_filter.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert invalid_cursor.status_code == HTTP_BAD_REQUEST
    assert invalid_cursor.json() == {"detail": "cursor is invalid for this query"}
