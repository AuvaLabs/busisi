"""Bounded, allowlisted acquisition for registered public sources."""

from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import requests

from engine.budget_watchdog.archive import Acquisition
from engine.budget_watchdog.safe_http import install_ssrf_guard
from engine.budget_watchdog.sources import SourceRegistry

DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = (5, 30)
DOWNLOAD_CHUNK_BYTES = 64 * 1024


class AcquisitionError(RuntimeError):
    """Raised when a source response violates the acquisition contract."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class SourceFetcher:
    def __init__(
        self,
        registry: SourceRegistry,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        session: requests.Session | None = None,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        install_ssrf_guard()
        self._registry = registry
        self._max_response_bytes = max_response_bytes
        self._session = session or requests.Session()
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

        try:
            with self._session.get(
                url,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                stream=True,
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                self._validate_final_url(source.base_url, response.url)
                payload = self._read_bounded(response)
                media_type = response.headers.get("Content-Type", "application/octet-stream").split(
                    ";", maxsplit=1
                )[0]
                return Acquisition(
                    source_id=source_id,
                    source_url=response.url,
                    retrieved_at=timestamp,
                    media_type=media_type.strip(),
                    payload=payload,
                )
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            raise AcquisitionError(
                f"source request failed for {source_id}", http_status=status
            ) from exc

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
