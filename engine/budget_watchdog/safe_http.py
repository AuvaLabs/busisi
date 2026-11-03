"""Process-wide SSRF protection for Busisi source acquisition."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any

from urllib3.util import connection as urllib3_connection

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
    """Install an idempotent urllib3 connection guard."""
    global _installed  # noqa: PLW0603
    if _installed:
        return

    original = urllib3_connection.create_connection

    def guarded(address: tuple[str, int], *args: Any, **kwargs: Any) -> Any:
        host, port = address
        try:
            address_info = socket.getaddrinfo(host, port)
        except socket.gaierror:
            return original(address, *args, **kwargs)

        for info in address_info:
            peer_ip = str(info[4][0])
            if not _is_public_ip(peer_ip):
                raise ConnectionRefusedError(
                    f"SSRF guard: {host} resolves to non-public {peer_ip}"
                )
        return original(address, *args, **kwargs)

    urllib3_connection.create_connection = guarded
    _installed = True
    logger.info("SSRF guard installed on urllib3 create_connection")


def is_installed() -> bool:
    """Return whether the process-wide guard is active."""
    return _installed
