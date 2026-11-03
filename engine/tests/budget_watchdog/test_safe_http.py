import socket

import pytest
from urllib3.util import connection as urllib3_connection

from engine.budget_watchdog import safe_http
from engine.budget_watchdog.safe_http import _is_public_ip


def test_public_address_is_allowed() -> None:
    assert _is_public_ip("1.1.1.1") is True


def test_non_public_addresses_are_rejected() -> None:
    addresses = (
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "not-an-ip",
    )

    assert all(_is_public_ip(address) is False for address in addresses)


def test_ssrf_guard_allows_public_dns_and_is_idempotent(monkeypatch) -> None:
    calls = []

    def original(address, *args, **kwargs):
        calls.append((address, args, kwargs))
        return "connected"

    monkeypatch.setattr(safe_http, "_installed", False)
    monkeypatch.setattr(urllib3_connection, "create_connection", original)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port))],
    )

    safe_http.install_ssrf_guard()
    guarded = urllib3_connection.create_connection
    assert guarded(("example.test", 443), timeout=2) == "connected"
    safe_http.install_ssrf_guard()

    assert urllib3_connection.create_connection is guarded
    assert calls == [(("example.test", 443), (), {"timeout": 2})]
    assert safe_http.is_installed() is True


def test_ssrf_guard_rejects_any_non_public_dns_result(monkeypatch) -> None:
    monkeypatch.setattr(safe_http, "_installed", False)
    monkeypatch.setattr(urllib3_connection, "create_connection", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ],
    )
    safe_http.install_ssrf_guard()

    with pytest.raises(ConnectionRefusedError, match="non-public 127.0.0.1"):
        urllib3_connection.create_connection(("mixed.test", 443))


def test_ssrf_guard_preserves_dns_failure_behavior(monkeypatch) -> None:
    calls = []

    def original(address, *_args, **_kwargs):
        calls.append(address)
        return "dns-fallback"

    def fail_dns(_host, _port):
        raise socket.gaierror("not found")

    monkeypatch.setattr(safe_http, "_installed", False)
    monkeypatch.setattr(urllib3_connection, "create_connection", original)
    monkeypatch.setattr(socket, "getaddrinfo", fail_dns)
    safe_http.install_ssrf_guard()

    assert urllib3_connection.create_connection(("missing.test", 443)) == "dns-fallback"
    assert calls == [("missing.test", 443)]
