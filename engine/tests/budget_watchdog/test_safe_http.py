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
