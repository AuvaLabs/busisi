from __future__ import annotations

import pytest

from engine.budget_watchdog.rate_limit import HostRateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.value = 10.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_rate_limiter_spaces_each_host_independently() -> None:
    clock = FakeTime()
    limiter = HostRateLimiter(
        requests_per_second=2,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    limiter.wait_for_url("https://api.dpwh.bettergov.ph/one")
    limiter.wait_for_url("https://api.dpwh.bettergov.ph/two")
    limiter.wait_for_url("https://s3.transparency.dpwh.gov.ph/image.jpg")

    assert clock.sleeps == [0.5]


def test_rate_limiter_rejects_invalid_configuration_and_urls() -> None:
    for value in (0, -1):
        with pytest.raises(ValueError, match="positive"):
            HostRateLimiter(requests_per_second=value)

    limiter = HostRateLimiter(requests_per_second=1)
    for url in ("http://example.com/path", "not-a-url"):
        with pytest.raises(ValueError, match="HTTPS"):
            limiter.wait_for_url(url)
