"""Bounded, allowlisted acquisition for registered public sources."""

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import requests

from engine.budget_watchdog.archive import Acquisition
from engine.budget_watchdog.safe_http import install_ssrf_guard
from engine.budget_watchdog.sources import SourceRegistry

DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = (5, 30)
DOWNLOAD_CHUNK_BYTES = 64 * 1024
MAX_ERROR_RESPONSE_BYTES = 64 * 1024
HTTP_TOO_MANY_REQUESTS = 429
HTTP_CLIENT_ERROR_MIN = 400
HTTP_SERVER_ERROR_MIN = 500


class AcquisitionError(RuntimeError):
    """Raised when a source response violates the acquisition contract."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        response_body: bytes = b"",
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.response_body = response_body


class SourceFetcher:
    def __init__(
        self,
        registry: SourceRegistry,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        session: requests.Session | None = None,
        request_gate: Callable[[str], None] | None = None,
        max_attempts: int = 1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        install_ssrf_guard()
        self._registry = registry
        self._max_response_bytes = max_response_bytes
        self._session = session or requests.Session()
        self._request_gate = request_gate
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._session.headers.update(
            {
                "Accept": "application/json, application/octet-stream, */*",
                "User-Agent": "BusisiBudgetWatchdog/1.0",
            }
        )

    def fetch(
        self,
        source_id: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        retrieved_at: datetime | None = None,
    ) -> Acquisition:
        source = self._registry.get(source_id)
        url = self._build_url(source.base_url, path)
        timestamp = retrieved_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise AcquisitionError("retrieved_at must be timezone-aware")

        for attempt in range(self._max_attempts):
            try:
                return self._fetch_once(
                    source_id,
                    source.base_url,
                    url,
                    params=params,
                    retrieved_at=timestamp,
                )
            except AcquisitionError as exc:
                if attempt >= self._max_attempts - 1 or not self._retryable(exc):
                    raise
                delay = exc.retry_after_seconds or float(2**attempt)
                self._sleep(min(float(delay), 30.0))
        raise AssertionError("bounded acquisition retry loop did not return")

    def _fetch_once(
        self,
        source_id: str,
        base_url: str,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        retrieved_at: datetime,
    ) -> Acquisition:
        try:
            if self._request_gate is not None:
                self._request_gate(url)
            with self._session.get(
                url,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                stream=True,
                allow_redirects=False,
            ) as response:
                self._validate_final_url(base_url, response.url)
                if response.status_code >= HTTP_CLIENT_ERROR_MIN:
                    response_body = self._read_error_bounded(response)
                    raise AcquisitionError(
                        f"source request failed for {source_id}",
                        http_status=response.status_code,
                        retry_after_seconds=self._retry_after(response),
                        response_body=response_body,
                    )
                payload = self._read_bounded(response)
                media_type = response.headers.get("Content-Type", "application/octet-stream").split(
                    ";", maxsplit=1
                )[0]
                return Acquisition(
                    source_id=source_id,
                    source_url=response.url,
                    retrieved_at=retrieved_at,
                    media_type=media_type.strip(),
                    payload=payload,
                )
        except requests.RequestException as exc:
            error_response = exc.response
            status = error_response.status_code if error_response is not None else None
            retry_after = self._retry_after(error_response)
            raise AcquisitionError(
                f"source request failed for {source_id}",
                http_status=status,
                retry_after_seconds=retry_after,
            ) from exc

    @staticmethod
    def _read_error_bounded(response: requests.Response) -> bytes:
        chunks: list[bytes] = []
        received = 0
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if not chunk:
                continue
            remaining = MAX_ERROR_RESPONSE_BYTES - received
            if remaining <= 0:
                break
            chunks.append(chunk[:remaining])
            received += min(len(chunk), remaining)
            if received >= MAX_ERROR_RESPONSE_BYTES:
                break
        return b"".join(chunks)

    @staticmethod
    def _retryable(error: AcquisitionError) -> bool:
        status = error.http_status
        if status is not None:
            return status == HTTP_TOO_MANY_REQUESTS or status >= HTTP_SERVER_ERROR_MIN
        return isinstance(error.__cause__, requests.RequestException)

    @staticmethod
    def _retry_after(response: requests.Response | None) -> int | None:
        if response is None:
            return None
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = int(value)
        except ValueError:
            return None
        return min(seconds, 86_400) if seconds > 0 else None

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        parsed = urlparse(path)
        if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc:
            raise AcquisitionError("source path must be a root-relative path")
        return urljoin(f"{base_url.rstrip('/')}/", path.removeprefix("/"))

    @staticmethod
    def _validate_final_url(base_url: str, final_url: str) -> None:
        expected = urlparse(base_url)
        actual = urlparse(final_url)
        if actual.scheme != "https" or actual.netloc != expected.netloc:
            raise AcquisitionError("source response escaped the registered origin")

    def _read_bounded(self, response: requests.Response) -> bytes:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise AcquisitionError("source returned an invalid Content-Length") from exc
            if declared_size > self._max_response_bytes:
                raise AcquisitionError("source response exceeds the maximum size")

        chunks: list[bytes] = []
        received = 0
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if not chunk:
                continue
            received += len(chunk)
            if received > self._max_response_bytes:
                raise AcquisitionError("source response exceeds the maximum size")
            chunks.append(chunk)
        if received == 0:
            raise AcquisitionError("source returned an empty response")
        return b"".join(chunks)
