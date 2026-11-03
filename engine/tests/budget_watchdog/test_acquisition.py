from datetime import UTC, datetime

import pytest
import responses

from engine.budget_watchdog.acquisition import AcquisitionError, SourceFetcher
from engine.budget_watchdog.sources import SourceRegistryError, default_source_registry

RETRIEVED_AT = datetime(2026, 11, 2, 14, 0, tzinfo=UTC)


@responses.activate
def test_fetcher_acquires_allowlisted_source_with_bounded_payload() -> None:
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/api/v1/gaa/search?q=Agoncillo",
        body=b'{"data": []}',
        headers={"Content-Type": "application/json; charset=utf-8"},
        status=200,
    )
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=1024)

    acquisition = fetcher.fetch(
        "bettergov-budget",
        "/api/v1/gaa/search",
        params={"q": "Agoncillo"},
        retrieved_at=RETRIEVED_AT,
    )

    assert acquisition.source_url.endswith("q=Agoncillo")
    assert acquisition.media_type == "application/json"
    assert acquisition.payload == b'{"data": []}'
    assert acquisition.retrieved_at == RETRIEVED_AT
    assert responses.calls[0].request.headers["User-Agent"] == "BusisiBudgetWatchdog/1.0"


def test_fetcher_rejects_unknown_sources_and_absolute_paths() -> None:
    fetcher = SourceFetcher(default_source_registry())

    with pytest.raises(SourceRegistryError, match="unknown"):
        fetcher.fetch("unknown", "/data", retrieved_at=RETRIEVED_AT)
    with pytest.raises(AcquisitionError, match="relative"):
        fetcher.fetch(
            "bettergov-budget",
            "https://example.com/private",
            retrieved_at=RETRIEVED_AT,
        )


@responses.activate
def test_fetcher_rejects_oversized_payloads() -> None:
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/large",
        body=b"x" * 11,
        headers={"Content-Type": "application/octet-stream", "Content-Length": "11"},
        status=200,
    )
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=10)

    with pytest.raises(AcquisitionError, match="maximum"):
        fetcher.fetch(
            "bettergov-budget",
            "/large",
            retrieved_at=RETRIEVED_AT,
        )
