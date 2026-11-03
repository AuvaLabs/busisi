import sqlite3
from pathlib import Path

from engine.budget_watchdog.contract_evidence_bundle import build_contract_evidence_bundle


def test_builds_verified_contract_evidence_bundle(tmp_path: Path) -> None:
    result = build_contract_evidence_bundle(
        Path("ops/harness/fixtures/contract_evidence_catalog.json"),
        tmp_path / "bundle",
    )

    assert result.contract_count == 3
    assert result.item_count == 27
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            Path("cloudflare/busisi/migrations/0015_contract_evidence.sql").read_text()
        )
        connection.executescript((result.output_dir / "contract-evidence.sql").read_text())
        row = connection.execute(
            "SELECT status, reported_date, date_kind FROM contract_evidence_items "
            "WHERE contract_id = '24HI0131' AND stage = 'notice_to_proceed'"
        ).fetchone()
    finally:
        connection.close()

    assert row == ("not_located", "2024-06-27", "actual")
