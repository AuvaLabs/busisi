"""Build verified D1 seed chunks for official PSA community context."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.budget_watchdog.community_needs import PopulationPlace, PopulationSnapshot

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0032_community_needs.sql"
)
CENSUS_DATE = "2024-07-01"


@dataclass(frozen=True, slots=True)
class CommunityNeedsBundleResult:
    output_dir: Path
    place_count: int
    region_count: int
    barangay_count: int
    sql_chunks: int
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_values(values: Sequence[str | int | None]) -> str:
    encoded = []
    for value in values:
        if value is None:
            encoded.append("NULL")
        elif isinstance(value, int):
            encoded.append(str(value))
        else:
            encoded.append(_sql_text(value))
    return ", ".join(encoded)


def _batched(rows: Iterable[str], size: int) -> Iterator[tuple[str, ...]]:
    batch: list[str] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _record_statement(record: PopulationPlace) -> str:
    values = (
        record.psgc_code,
        record.parent_psgc_code,
        record.name,
        record.geographic_level,
        CENSUS_DATE,
        record.total_population,
        record.household_population,
        record.households,
        record.source_url,
        record.source_sha256,
    )
    return f"INSERT INTO community_need_places VALUES ({_sql_values(values)});"  # noqa: S608


def _write_chunks(
    directory: Path,
    statements: Iterable[str],
    chunk_rows: int,
    *,
    prefix: str = "100-community-needs",
) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(statements, chunk_rows), start=1):
        path = directory / f"{prefix}-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _metadata(snapshot: PopulationSnapshot, checked_at: str) -> dict[str, str]:
    try:
        datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checked_at must use ISO format") from exc
    return {
        "barangay_count": str(snapshot.barangay_count),
        "census_date": CENSUS_DATE,
        "checked_at": checked_at,
        "excluded_out_of_region": str(snapshot.excluded_out_of_region),
        "geographic_source": "Philippine Statistics Authority OpenSTAT",
        "hierarchy_gap_count": str(len(snapshot.hierarchy_gaps)),
        "national_household_population": str(snapshot.national_household_population),
        "national_households": str(snapshot.national_households),
        "national_population": str(snapshot.national_population),
        "national_unallocated_household_population": str(
            snapshot.national_unallocated_household_population
        ),
        "national_unallocated_households": str(snapshot.national_unallocated_households),
        "national_unallocated_population": str(snapshot.national_unallocated_population),
        "place_count": str(snapshot.place_count),
        "region_count": str(snapshot.region_count),
        "snapshot_sha256": snapshot.snapshot_sha256,
    }


def _metadata_sql(metadata: dict[str, str]) -> str:
    lines = [
        "DELETE FROM community_need_hierarchy_gaps;",
        "DELETE FROM community_need_places;",
        "DELETE FROM community_needs_metadata;",
    ]
    lines.extend(
        f"INSERT INTO community_needs_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    return "\n".join(lines) + "\n"


def _gap_statements(snapshot: PopulationSnapshot) -> Iterator[str]:
    for gap in snapshot.hierarchy_gaps:
        values = (
            gap.parent_psgc_code,
            gap.unallocated_population,
            gap.unallocated_household_population,
            gap.unallocated_households,
        )
        yield f"INSERT INTO community_need_hierarchy_gaps VALUES ({_sql_values(values)});"  # noqa: S608


def _verify(chunks: Sequence[Path], snapshot: PopulationSnapshot) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        count = connection.execute("SELECT COUNT(*) FROM community_need_places").fetchone()[0]
        total = connection.execute(
            "SELECT SUM(total_population) FROM community_need_places "
            "WHERE geographic_level = 'region'"
        ).fetchone()[0]
        gaps = connection.execute("SELECT COUNT(*) FROM community_need_hierarchy_gaps").fetchone()[
            0
        ]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if (
        count != snapshot.place_count
        or total != snapshot.national_population - snapshot.national_unallocated_population
        or gaps != len(snapshot.hierarchy_gaps)
        or integrity != "ok"
    ):
        raise ValueError("community needs D1 bundle verification failed")


def build_community_needs_bundle(
    snapshot: PopulationSnapshot,
    output_dir: Path,
    *,
    checked_at: str,
    chunk_rows: int = 1_000,
) -> CommunityNeedsBundleResult:
    """Build an atomic, verified SQL bundle from a reconciled PSA snapshot."""

    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    metadata = _metadata(snapshot, checked_at)
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata_path = chunks_dir / "000-metadata.sql"
    metadata_path.write_text(_metadata_sql(metadata), encoding="utf-8")
    chunks = [
        metadata_path,
        *_write_chunks(
            chunks_dir,
            (_record_statement(record) for record in snapshot.records),
            chunk_rows,
        ),
    ]
    chunks.extend(
        _write_chunks(
            chunks_dir,
            _gap_statements(snapshot),
            chunk_rows,
            prefix="200-hierarchy-gaps",
        )
    )
    _verify(chunks, snapshot)
    manifest = {
        **metadata,
        "source_sha256": list(snapshot.source_sha256),
        "chunk_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in chunks
        },
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return CommunityNeedsBundleResult(
        output_dir,
        snapshot.place_count,
        snapshot.region_count,
        snapshot.barangay_count,
        len(chunks),
        manifest_sha256,
    )
