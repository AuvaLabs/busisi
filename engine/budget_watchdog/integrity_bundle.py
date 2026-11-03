"""Build verified D1 chunks for delivery-integrity signals and contractors."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from engine.budget_watchdog.integrity import (
    ContractorSummary,
    DeliveryIntegrityRecord,
    IntegritySignal,
    build_integrity_snapshot,
)
from engine.budget_watchdog.models import validate_fiscal_year
from engine.budget_watchdog.money import parse_centavos

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0005_integrity.sql"
)
SNAPSHOT_COLUMNS = (
    "contractId",
    "description",
    "category",
    "status",
    "budget",
    "progress",
    "location",
    "contractor",
    "startDate",
    "completionDate",
    "infraYear",
    "latitude",
    "longitude",
    "hasSatelliteImage",
)


@dataclass(frozen=True, slots=True)
class IntegrityBundleResult:
    output_dir: Path
    source_records: int
    integrity_signals: int
    contractors: int
    sql_chunks: int
    manifest_sha256: str


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _record(row: dict[str, Any], source_digest: str) -> DeliveryIntegrityRecord:
    location = row.get("location")
    if not isinstance(location, dict):
        location = {}
    year = int(_text(row.get("infraYear")))
    validate_fiscal_year(year)
    progress = _decimal_text(row.get("progress"))
    if progress is None:
        raise ValueError("progress must be present")
    return DeliveryIntegrityRecord(
        contract_id=_text(row.get("contractId")),
        fiscal_year=year,
        description=_text(row.get("description")),
        category=_text(row.get("category")),
        status=_text(row.get("status")),
        budget_centavos=parse_centavos(Decimal(str(row.get("budget")))),
        progress=progress,
        province=_text(location.get("province")),
        region=_text(location.get("region")),
        contractor=_text(row.get("contractor")),
        start_date=_date(row.get("startDate")),
        completion_date=_date(row.get("completionDate")),
        latitude=_decimal_text(row.get("latitude")),
        longitude=_decimal_text(row.get("longitude")),
        has_satellite_image=bool(row.get("hasSatelliteImage")),
        source_artifact_sha256=source_digest,
    )


def _load_records(
    snapshot_path: Path,
    fiscal_years: tuple[int, ...],
    source_digest: str,
) -> tuple[DeliveryIntegrityRecord, ...]:
    if not fiscal_years or len(set(fiscal_years)) != len(fiscal_years):
        raise ValueError("fiscal_years must be unique and non-empty")
    for year in fiscal_years:
        validate_fiscal_year(year)
    table = pq.read_table(
        snapshot_path,
        columns=list(SNAPSHOT_COLUMNS),
        filters=[("infraYear", "in", [str(year) for year in fiscal_years])],
    )
    records = tuple(_record(row, source_digest) for row in table.to_pylist())
    identifiers = {record.contract_id for record in records}
    if len(identifiers) != len(records):
        raise ValueError("contractId must be unique inside the selected snapshot")
    return records


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_values(values: Sequence[str | int]) -> str:
    return ", ".join(str(value) if isinstance(value, int) else _sql_text(value) for value in values)


def _signal_statement(signal: IntegritySignal) -> str:
    values = (
        f"{signal.contract_id}:{signal.code}",
        signal.contract_id,
        signal.fiscal_year,
        signal.code,
        signal.classification,
        signal.label,
        signal.description,
        signal.contractor_name,
        signal.pcab_id,
        signal.budget_centavos,
        signal.status,
        signal.progress,
        signal.province,
        signal.region,
        signal.latitude,
        signal.longitude,
        signal.evidence,
        signal.limitations,
        signal.source_artifact_sha256,
    )
    return f"INSERT INTO integrity_signal_items VALUES ({_sql_values(values)});"  # noqa: S608


def _contractor_statement(contractor: ContractorSummary) -> str:
    values = (
        contractor.contractor_key,
        contractor.contractor_name,
        contractor.pcab_id,
        contractor.project_count,
        contractor.total_budget_centavos,
        contractor.completed_count,
        contractor.ongoing_count,
        contractor.terminated_count,
        contractor.first_year,
        contractor.last_year,
    )
    return f"INSERT INTO contractor_rankings VALUES ({_sql_values(values)});"  # noqa: S608


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
    directory: Path,
    prefix: str,
    statements: Iterable[str],
    chunk_rows: int,
) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(statements, chunk_rows), start=1):
        path = directory / f"{prefix}-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _metadata_sql(metadata: dict[str, str]) -> str:
    lines = [
        "DELETE FROM integrity_signal_items;",
        "DELETE FROM contractor_rankings;",
        "DELETE FROM integrity_metadata;",
    ]
    lines.extend(
        f"INSERT INTO integrity_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    return "\n".join(lines) + "\n"


def _verify_bundle(chunks: Sequence[Path], expected: tuple[int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = (
            connection.execute("SELECT COUNT(*) FROM integrity_signal_items").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM contractor_rankings").fetchone()[0],
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("integrity bundle verification failed")


def build_integrity_bundle(
    snapshot_path: Path,
    output_dir: Path,
    *,
    fiscal_years: tuple[int, ...] = (2024, 2025, 2026),
    chunk_rows: int = 2_000,
) -> IntegrityBundleResult:
    """Create reproducible SQL chunks from an immutable DPWH Parquet snapshot."""

    if not snapshot_path.is_file():
        raise ValueError("snapshot_path must exist")
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    source_digest = _digest(snapshot_path)
    records = _load_records(snapshot_path, fiscal_years, source_digest)
    snapshot = build_integrity_snapshot(records)
    signal_counts = Counter(signal.code for signal in snapshot.signals)
    metadata = {
        "contractors": str(len(snapshot.contractors)),
        "fiscal_years": ",".join(str(year) for year in fiscal_years),
        "integrity_signals": str(len(snapshot.signals)),
        "schema_version": "1",
        "source_artifact_sha256": source_digest,
        "source_records": str(len(records)),
        **{f"signal:{code}": str(count) for code, count in sorted(signal_counts.items())},
    }
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata_path = chunks_dir / "000-metadata.sql"
    metadata_path.write_text(_metadata_sql(metadata), encoding="utf-8")
    chunks = [metadata_path]
    chunks.extend(
        _write_chunks(
            chunks_dir,
            "100-signals",
            (_signal_statement(signal) for signal in snapshot.signals),
            chunk_rows,
        )
    )
    chunks.extend(
        _write_chunks(
            chunks_dir,
            "200-contractors",
            (_contractor_statement(contractor) for contractor in snapshot.contractors),
            chunk_rows,
        )
    )
    _verify_bundle(chunks, (len(snapshot.signals), len(snapshot.contractors)))
    manifest = {
        **metadata,
        "fiscal_years": list(fiscal_years),
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
    return IntegrityBundleResult(
        output_dir=output_dir,
        source_records=len(records),
        integrity_signals=len(snapshot.signals),
        contractors=len(snapshot.contractors),
        sql_chunks=len(chunks),
        manifest_sha256=manifest_sha256,
    )
