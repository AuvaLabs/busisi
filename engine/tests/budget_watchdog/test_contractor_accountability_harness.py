from __future__ import annotations

import pytest
from ops.harness.budget_watchdog_accountability import discover_latest_cpes_report


def test_discovers_highest_official_cpes_release() -> None:
    payload = b"""
    <html><body>
      <a href="/wp-content/uploads/2025/report-40.pdf">CPES Report 40th Release</a>
      <a href="https://www.gppb.gov.ph/wp-content/uploads/2026/report-41.pdf">
        CPES Report 41st Release
      </a>
    </body></html>
    """

    release, path = discover_latest_cpes_report(payload)

    assert release == "41st Release"
    assert path == "/wp-content/uploads/2026/report-41.pdf"


def test_rejects_cross_origin_or_missing_cpes_links() -> None:
    with pytest.raises(ValueError, match="no official CPES report"):
        discover_latest_cpes_report(
            b'<a href="https://example.com/report.pdf">CPES Report 42nd Release</a>'
        )
