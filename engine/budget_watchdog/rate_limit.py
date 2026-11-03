"""Thread-safe per-host request pacing for public-source acquisition."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock
from urllib.parse import urlparse


class HostRateLimiter:
    def __init__(
        self,
        *,
        requests_per_second: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("request rate must be positive")
        self._interval = 1 / requests_per_second
        self._monotonic = monotonic
        self._sleep = sleep
        self._state_lock = Lock()
        self._host_locks: dict[str, Lock] = {}
        self._next_request: dict[str, float] = {}

    def wait_for_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("rate-limited source URL must use HTTPS")
        hostname = parsed.hostname
        with self._state_lock:
            host_lock = self._host_locks.setdefault(hostname, Lock())
        with host_lock:
            now = self._monotonic()
            next_request = self._next_request.get(hostname, now)
            delay = max(0.0, next_request - now)
            if delay:
                self._sleep(delay)
                now = self._monotonic()
            self._next_request[hostname] = max(now, next_request) + self._interval
