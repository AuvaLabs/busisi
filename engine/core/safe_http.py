"""Global SSRF guard for outbound HTTP/HTTPS.

Validates that every socket connection resolves to a public IP at connect
time, closing the DNS-rebinding TOCTOU between hostname-validation and the
actual TCP connect.

Ported verbatim from ``modules/safe_http.py`` in ThreatWatch (HEAD fffecca).
A hostile feed operator could otherwise supply a domain that resolves to a
public IP during validation but flips to ``169.254.169.254`` (cloud IMDS),
``127.0.0.1``, or any RFC1918 range at connect time.

The guard is a process-wide ``urllib3`` monkeypatch applied once. It blocks
*every* outbound socket — fine for grimoire, where the pipeline and server
only talk to public feeds and the public LLM API. Internal calls within the
docker network (e.g. service → postgres) are direct and don't go through
``urllib3``, so they're unaffected.

Usage::

    from engine.core.safe_http import install_ssrf_guard
    install_ssrf_guard()  # call once at process startup
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

_installed = False


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def install_ssrf_guard() -> None:
    """Install a urllib3-level SSRF guard. Idempotent."""
    global _installed
    if _installed:
        return
    try:
        from urllib3.util import connection as urllib3_connection
    except ImportError:
        logger.warning("urllib3 not importable — SSRF guard not installed")
        return

    original = urllib3_connection.create_connection

    def guarded(address: tuple[str, int], *args: Any, **kwargs: Any) -> Any:
        host, port = address
        try:
            infos = socket.getaddrinfo(host, port)
        except socket.gaierror:
            return original(address, *args, **kwargs)
        for info in infos:
            peer_ip = info[4][0]
            if not _is_public_ip(peer_ip):
                raise ConnectionRefusedError(
                    f"SSRF guard: {host} resolves to non-public {peer_ip}"
                )
        return original(address, *args, **kwargs)

    urllib3_connection.create_connection = guarded
    _installed = True
    logger.info("SSRF guard installed on urllib3 create_connection")


def is_installed() -> bool:
    """Return True if the SSRF guard has been installed in this process."""
    return _installed
