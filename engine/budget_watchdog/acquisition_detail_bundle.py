"""Build verified D1 chunks for contract-level acquisition evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.acquisition_universe import AcquisitionUniverseSnapshot

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0018_contract_acquisition_detail.sql"
)


@dataclass(frozen=True, slots=True)
class AcquisitionDetailBundleResult:
    output_dir: Path
    contract_count: int
    match_count: int
    quarantine_count: int
    quarantine_candidate_count: int
    sql_chunks: int
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_value(value: str | int | None) -> str:
    if value is None:
        return "NULL"
    return str(value) if isinstance(value, int) else _sql_text(value)


def _values(values: Sequence[str | int | None]) -> str:
    return ", ".join(_sql_value(value) for value in values)


def _batched(rows: Iterable[str], size: int) -> Iterator[tuple[str, ...]]:
    batch: list[str] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _write_chunks(
    directory: Path, prefix: str, statements: Iterable[str], chunk_rows: int
) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(statements, chunk_rows), start=1):
        path = directory / f"{prefix}-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _contract_statements(snapshot: AcquisitionUniverseSnapshot) -> Iterator[str]:
    for item in snapshot.contracts:
        values = (
            item.contract_id,
            item.fiscal_year,
            item.identifier_status,
            item.year_alignment,
            item.match_state,
            item.accepted_match_rows,
            item.quarantined_match_rows,
        )
        yield f"INSERT INTO contract_acquisition_details VALUES ({_values(values)});"  # noqa: S608


def _match_statements(snapshot: AcquisitionUniverseSnapshot) -> Iterator[str]:
    for item in snapshot.matches:
        values = (
            item.source_row_id,
            item.contract_id,
            item.match_basis,
            item.reference_id,
            item.contract_no,
            item.award_title,
            item.notice_title,
            item.awardee_name,
            item.organization_name,
            item.area_of_delivery,
            item.business_category,
            item.contract_amount_centavos,
            item.award_date,
            item.award_status,
            item.row_sha256,
        )
        yield f"INSERT INTO contract_award_matches VALUES ({_values(values)});"  # noqa: S608


def _quarantine_statements(snapshot: AcquisitionUniverseSnapshot) -> Iterator[str]:
    for item in snapshot.quarantine:
        values = (
            item.source_row_id,
            item.reason,
            item.row_sha256,
            item.reference_id,
            item.contract_no,
            item.award_title,
            item.notice_title,
        )
        yield f"INSERT INTO contract_quarantine_rows VALUES ({_values(values)});"  # noqa: S608


def _candidate_statements(snapshot: AcquisitionUniverseSnapshot) -> Iterator[str]:
    for item in snapshot.quarantine:
        for contract_id in item.candidate_contract_ids:
            values = _values((item.source_row_id, contract_id))
            yield f"INSERT INTO contract_quarantine_candidates VALUES ({values});"  # noqa: S608


def _metadata(snapshot: AcquisitionUniverseSnapshot) -> dict[str, str]:
    return {
        "award_revision": snapshot.award_revision,
        "award_sha256": snapshot.award_sha256,
        "checked_on": snapshot.checked_on.isoformat(),
        "contract_count": str(len(snapshot.contracts)),
        "delivery_sha256": snapshot.delivery_sha256,
        "match_count": str(len(snapshot.matches)),
        "quarantine_candidate_count": str(
            sum(len(item.candidate_contract_ids) for item in snapshot.quarantine)
        ),
        "quarantine_count": str(len(snapshot.quarantine)),
        "schema_version": "1",
    }


def _metadata_sql(snapshot: AcquisitionUniverseSnapshot) -> str:
    lines = [
        "DELETE FROM contract_quarantine_candidates;",
        "DELETE FROM contract_quarantine_rows;",
        "DELETE FROM contract_award_matches;",
        "DELETE FROM contract_acquisition_details;",
        "DELETE FROM contract_acquisition_metadata;",
    ]
    lines.extend(
        f"INSERT INTO contract_acquisition_metadata VALUES ({_values((key, value))});"  # noqa: S608
        for key, value in sorted(_metadata(snapshot).items())
    )
    return "\n".join(lines) + "\n"


def _verify(chunks: Sequence[Path], expected: tuple[int, int, int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "contract_acquisition_details",
                "contract_award_matches",
                "contract_quarantine_rows",
                "contract_quarantine_candidates",
            )
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()
    if actual != expected or integrity != "ok" or foreign_keys:
        raise ValueError("contract acquisition detail bundle verification failed")


def build_acquisition_detail_bundle(
    snapshot: AcquisitionUniverseSnapshot,
    output_dir: Path,
    *,
    chunk_rows: int = 1_000,
) -> AcquisitionDetailBundleResult:
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata_path = chunks_dir / "000-metadata.sql"
    metadata_path.write_text(_metadata_sql(snapshot), encoding="utf-8")
    chunks = [metadata_path]
    chunks += _write_chunks(chunks_dir, "100-contracts", _contract_statements(snapshot), chunk_rows)
    chunks += _write_chunks(chunks_dir, "200-matches", _match_statements(snapshot), chunk_rows)
    chunks += _write_chunks(
        chunks_dir, "300-quarantine", _quarantine_statements(snapshot), chunk_rows
    )
    chunks += _write_chunks(
        chunks_dir, "400-candidates", _candidate_statements(snapshot), chunk_rows
    )
    expected = (
        len(snapshot.contracts),
        len(snapshot.matches),
        len(snapshot.quarantine),
        sum(len(item.candidate_contract_ids) for item in snapshot.quarantine),
    )
    _verify(chunks, expected)
    manifest = {
        **_metadata(snapshot),
        "contract_count": expected[0],
        "match_count": expected[1],
        "quarantine_count": expected[2],
        "quarantine_candidate_count": expected[3],
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
    return AcquisitionDetailBundleResult(output_dir, *expected, len(chunks), manifest_sha256)
