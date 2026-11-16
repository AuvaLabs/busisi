import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.community_needs import (
    PopulationPlace,
    PopulationSnapshot,
)
from engine.budget_watchdog.community_needs_bundle import build_community_needs_bundle


def _snapshot() -> PopulationSnapshot:
    first_sha = "a" * 64
    control_sha = "b" * 64
    source = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/test.px"
    records = (
        PopulationPlace("0100000000", None, "Region I", "region", 100, 98, 30, first_sha, source),
        PopulationPlace(
            "0102800000",
            "0100000000",
            "Ilocos Norte",
            "province_or_huc",
            100,
            98,
            30,
            first_sha,
            source,
        ),
    )
    return PopulationSnapshot(
        records=records,
        national_population=100,
        national_household_population=98,
        national_households=30,
        national_source_sha256=control_sha,
        source_sha256=(first_sha, control_sha),
        snapshot_sha256="c" * 64,
        region_count=1,
        place_count=2,
        barangay_count=0,
        excluded_out_of_region=0,
        hierarchy_gaps=(),
        national_unallocated_population=0,
        national_unallocated_household_population=0,
        national_unallocated_households=0,
    )


def test_community_needs_bundle_writes_verified_atomic_d1_seed(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    result = build_community_needs_bundle(
        _snapshot(), output, checked_at="2026-11-16T10:00:00+08:00", chunk_rows=1
    )

    assert result.place_count == 2
    assert result.region_count == 1
    assert result.sql_chunks == 3
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["national_population"] == "100"
    assert manifest["census_date"] == "2024-07-01"

    root = Path(__file__).resolve().parents[3]
    migration = root / "cloudflare" / "busisi" / "migrations" / "0032_community_needs.sql"
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(migration.read_text())
        for path in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(path.read_text())
        assert connection.execute("SELECT COUNT(*) FROM community_need_places").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT total_population FROM community_need_places WHERE psgc_code = '0100000000'"
            ).fetchone()[0]
            == 100
        )
    finally:
        connection.close()


def test_community_needs_bundle_rejects_invalid_chunk_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        build_community_needs_bundle(
            _snapshot(), tmp_path / "bundle", checked_at="2026-11-16", chunk_rows=0
        )
