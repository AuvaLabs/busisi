from datetime import UTC, datetime
from types import SimpleNamespace

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


def test_fetcher_rejects_invalid_configuration_and_paths() -> None:
    with pytest.raises(ValueError, match="positive"):
        SourceFetcher(default_source_registry(), max_response_bytes=0)

    fetcher = SourceFetcher(default_source_registry())
    for path in ("relative", "//example.com/path"):
        with pytest.raises(AcquisitionError, match="root-relative"):
            fetcher.fetch("bettergov-budget", path, retrieved_at=RETRIEVED_AT)


def test_fetcher_rejects_naive_timestamp() -> None:
    fetcher = SourceFetcher(default_source_registry())

    with pytest.raises(AcquisitionError, match="timezone-aware"):
        fetcher.fetch("bettergov-budget", "/data", retrieved_at=datetime(2026, 11, 2))


@responses.activate
def test_fetcher_wraps_http_errors_without_leaking_response_details() -> None:
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/failure",
        body="sensitive upstream response",
        status=503,
    )
    fetcher = SourceFetcher(default_source_registry())

    with pytest.raises(
        AcquisitionError, match="source request failed for bettergov-budget"
    ) as error:
        fetcher.fetch("bettergov-budget", "/failure", retrieved_at=RETRIEVED_AT)

    assert "sensitive upstream response" not in str(error.value)
    assert error.value.response_body == b"sensitive upstream response"


@responses.activate
def test_fetcher_bounds_error_response_evidence() -> None:
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/failure",
        body=b"x" * 100_000,
        status=403,
    )
    fetcher = SourceFetcher(default_source_registry())

    with pytest.raises(AcquisitionError) as error:
        fetcher.fetch("bettergov-budget", "/failure", retrieved_at=RETRIEVED_AT)

    assert len(error.value.response_body) == 65_536


@responses.activate
def test_fetcher_retries_transient_requests() -> None:
    url = "https://budget.bettergov.ph/transient"
    responses.add(responses.GET, url, status=503)
    responses.add(responses.GET, url, body=b"stable", status=200)
    sleeps: list[float] = []
    fetcher = SourceFetcher(
        default_source_registry(),
        max_attempts=3,
        sleep=sleeps.append,
    )

    acquisition = fetcher.fetch("bettergov-budget", "/transient", retrieved_at=RETRIEVED_AT)

    assert acquisition.payload == b"stable"
    assert len(responses.calls) == 2
    assert sleeps == [1.0]


@responses.activate
def test_fetcher_preserves_bounded_retry_after_for_rate_limits() -> None:
    responses.add(
        responses.GET,
        "https://budget.bettergov.ph/limited",
        status=429,
        headers={"Retry-After": "120"},
    )
    fetcher = SourceFetcher(default_source_registry())

    with pytest.raises(AcquisitionError) as error:
        fetcher.fetch("bettergov-budget", "/limited", retrieved_at=RETRIEVED_AT)

    assert error.value.http_status == 429
    assert error.value.retry_after_seconds == 120


@responses.activate
def test_fetcher_applies_request_gate_before_network_access() -> None:
    url = "https://budget.bettergov.ph/gated"
    responses.add(responses.GET, url, body=b"ok", status=200)
    observed: list[str] = []
    fetcher = SourceFetcher(
        default_source_registry(),
        request_gate=observed.append,
    )

    fetcher.fetch("bettergov-budget", "/gated", retrieved_at=RETRIEVED_AT)

    assert observed == [url]


def test_fetcher_rejects_cross_origin_and_insecure_final_urls() -> None:
    for url in ("https://example.com/data", "http://budget.bettergov.ph/data"):
        with pytest.raises(AcquisitionError, match="escaped"):
            SourceFetcher._validate_final_url("https://budget.bettergov.ph", url)


@pytest.mark.parametrize(
    ("headers", "chunks", "message"),
    [
        ({"Content-Length": "invalid"}, [b"ok"], "invalid Content-Length"),
        ({"Content-Length": "11"}, [b"ok"], "maximum size"),
        ({}, [b"123456", b"123456"], "maximum size"),
        ({}, [b"", b""], "empty response"),
    ],
)
def test_bounded_reader_rejects_invalid_response_bodies(headers, chunks, message: str) -> None:
    response = SimpleNamespace(headers=headers, iter_content=lambda chunk_size: iter(chunks))
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=10)

    with pytest.raises(AcquisitionError, match=message):
        fetcher._read_bounded(response)


def test_bounded_reader_joins_non_empty_chunks() -> None:
    response = SimpleNamespace(headers={}, iter_content=lambda chunk_size: iter([b"a", b"", b"b"]))
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=10)

    assert fetcher._read_bounded(response) == b"ab"
