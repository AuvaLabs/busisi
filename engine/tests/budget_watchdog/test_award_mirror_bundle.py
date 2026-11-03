import sqlite3
from pathlib import Path

from engine.budget_watchdog.award_mirror_bundle import build_award_mirror_bundle


def test_builds_verified_award_mirror_bundle(tmp_path: Path) -> None:
    result = build_award_mirror_bundle(
        Path("ops/harness/fixtures/philgeps_award_mirror.json"),
        tmp_path / "bundle",
    )

    assert result.record_count == 3
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            Path("cloudflare/busisi/migrations/0014_contract_award_mirror.sql").read_text()
        )
        connection.executescript(
            Path("cloudflare/busisi/migrations/0017_archived_award_mirror.sql").read_text()
        )
        connection.executescript((result.output_dir / "contract-award-mirror.sql").read_text())
        row = connection.execute(
            "SELECT awardee_name, contract_amount_centavos FROM contract_award_mirror_records "
            "WHERE contract_id = '25HI0028'"
        ).fetchone()
        metadata = dict(connection.execute(
            "SELECT key, value FROM contract_award_mirror_metadata"
        ))
    finally:
        connection.close()
    assert row == ("LA PRUEBA CONSTRUCTION", 197899499)
    assert metadata["source_file_archived"] == "1"
    assert metadata["source_file_sha256"] == (
        "9bfa9e7cbf5041dc3b51a4c2742e60a43d1615f119955581d4b155bf3a6d4a8b"
    )
