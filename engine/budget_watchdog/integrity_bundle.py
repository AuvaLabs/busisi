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

from engine.budget_watchdog.districts import (
    DistrictSnapshot,
    OfficeDistrictAttribution,
    parse_district_pages,
)
from engine.budget_watchdog.integrity import (
    ContractorConcentration,
    ContractorSummary,
    DeliveryIntegrityRecord,
    IntegritySignal,
    build_integrity_snapshot,
    contractor_concentrations,
    contractor_identities,
)
from engine.budget_watchdog.models import validate_fiscal_year
from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.pcab import parse_pcab_regular_licenses

MIGRATION_DIRECTORY = Path(__file__).resolve().parents[2] / "cloudflare" / "busisi" / "migrations"
MIGRATION_PATHS = (
    MIGRATION_DIRECTORY / "0005_integrity.sql",
    MIGRATION_DIRECTORY / "0006_contractor_verification.sql",
    MIGRATION_DIRECTORY / "0007_district_attribution.sql",
    MIGRATION_DIRECTORY / "0011_delivery_details.sql",
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
    concentrations: int
    district_offices: int
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


def _detail_statement(record: DeliveryIntegrityRecord) -> str:
    parties = [
        {
            "contractor_key": item.key,
            "contractor_name": item.display_name,
            "pcab_id": item.pcab_id,
        }
        for item in contractor_identities(record.contractor)
    ]
    values = (
        record.contract_id,
        record.fiscal_year,
        record.category,
        record.status,
        record.progress,
        record.contractor,
        json.dumps(parties, ensure_ascii=False, separators=(",", ":")),
        record.start_date.isoformat() if record.start_date else "",
        record.completion_date.isoformat() if record.completion_date else "",
        record.province,
        record.region,
        record.latitude or "",
        record.longitude or "",
        int(record.has_satellite_image),
        record.source_artifact_sha256,
    )
    return f"INSERT INTO delivery_project_details VALUES ({_sql_values(values)});"  # noqa: S608


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
        contractor.joint_project_count,
        contractor.pcab_status,
        contractor.pcab_name,
        contractor.pcab_category,
        contractor.pcab_valid_to,
        contractor.pcab_gov_infra,
        contractor.pcab_snapshot_sha256,
    )
    return f"INSERT INTO contractor_rankings VALUES ({_sql_values(values)});"  # noqa: S608


def _concentration_statement(item: ContractorConcentration) -> str:
    values = (
        item.dimension,
        item.group_label,
        item.fiscal_year,
        item.project_count,
        item.named_project_count,
        item.party_association_count,
        item.contractor_count,
        item.top_contractor_key,
        item.top_contractor_name,
        item.top_pcab_id,
        item.top_project_count,
        item.top_share_basis_points,
        item.top_associated_budget_centavos,
    )
    return f"INSERT INTO contractor_concentrations VALUES ({_sql_values(values)});"  # noqa: S608


def _district_statement(
    office_key: str,
    item: OfficeDistrictAttribution,
    snapshot: DistrictSnapshot,
) -> str:
    districts = [
        {
            "district_id": seat.district_id,
            "label": seat.label,
            "representative_name": seat.representative_name,
            "representative_status": seat.representative_status,
            "representative_status_note": seat.representative_status_note,
            "representative_profile_url": seat.representative_profile_url,
        }
        for seat in item.seats
    ]
    values = (
        office_key,
        item.office_name,
        item.classification,
        len(item.seats),
        json.dumps(districts, ensure_ascii=False, separators=(",", ":")),
        snapshot.source_commit,
        snapshot.source_built_at,
        snapshot.retrieved_on.isoformat(),
        snapshot.snapshot_sha256,
    )
    return f"INSERT INTO district_office_attributions VALUES ({_sql_values(values)});"  # noqa: S608


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
        "DELETE FROM delivery_project_details;",
        "DELETE FROM integrity_signal_items;",
        "DELETE FROM contractor_rankings;",
        "DELETE FROM contractor_concentrations;",
        "DELETE FROM district_office_attributions;",
        "DELETE FROM integrity_metadata;",
    ]
    lines.extend(
        f"INSERT INTO integrity_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    return "\n".join(lines) + "\n"


def _verify_bundle(chunks: Sequence[Path], expected: tuple[int, int, int, int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        for migration in MIGRATION_PATHS:
            connection.executescript(migration.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = (
            connection.execute("SELECT COUNT(*) FROM delivery_project_details").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM integrity_signal_items").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM contractor_rankings").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM contractor_concentrations").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM district_office_attributions").fetchone()[0],
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("integrity bundle verification failed")


def _load_district_snapshot(
    paths: tuple[Path, ...],
    retrieved_on: date | None,
) -> DistrictSnapshot | None:
    if bool(paths) != (retrieved_on is not None):
        raise ValueError("district snapshot paths and retrieval date must be provided together")
    if not paths or retrieved_on is None:
        return None
    if any(not path.is_file() for path in paths):
        raise ValueError("every district snapshot path must exist")
    return parse_district_pages(
        tuple(path.read_bytes() for path in paths),
        source_sha256=tuple(_digest(path) for path in paths),
        retrieved_on=retrieved_on,
    )


def _district_metadata(
    snapshot: DistrictSnapshot,
    records: tuple[DeliveryIntegrityRecord, ...],
) -> dict[str, str]:
    coverage = Counter(snapshot.lookup(record.province).classification for record in records)
    return {
        "district_count": str(snapshot.district_count),
        "district_offices": str(snapshot.office_count),
        "district_source_built_at": snapshot.source_built_at,
        "district_source_commit": snapshot.source_commit,
        "district_source_retrieved_on": snapshot.retrieved_on.isoformat(),
        "district_snapshot_sha256": snapshot.snapshot_sha256,
        "district_source_sha256": json.dumps(snapshot.source_sha256),
        **{
            f"district_coverage:{classification}": str(count)
            for classification, count in sorted(coverage.items())
        },
    }


def build_integrity_bundle(
    snapshot_path: Path,
    output_dir: Path,
    *,
    fiscal_years: tuple[int, ...] = (2024, 2025, 2026),
    chunk_rows: int = 2_000,
    pcab_snapshot_path: Path | None = None,
    pcab_retrieved_on: date | None = None,
    source_as_of: date | None = None,
    minimum_concentration_projects: int = 20,
    district_snapshot_paths: tuple[Path, ...] = (),
    district_retrieved_on: date | None = None,
) -> IntegrityBundleResult:
    """Create reproducible SQL chunks from an immutable DPWH Parquet snapshot."""

    if not snapshot_path.is_file():
        raise ValueError("snapshot_path must exist")
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    source_digest = _digest(snapshot_path)
    records = _load_records(snapshot_path, fiscal_years, source_digest)
    if (pcab_snapshot_path is None) != (pcab_retrieved_on is None):
        raise ValueError("PCAB snapshot path and retrieval date must be provided together")
    pcab = None
    if pcab_snapshot_path is not None and pcab_retrieved_on is not None:
        pcab_digest = _digest(pcab_snapshot_path)
        pcab = parse_pcab_regular_licenses(
            pcab_snapshot_path.read_bytes(),
            retrieved_on=pcab_retrieved_on,
            source_sha256=pcab_digest,
        )
    snapshot = build_integrity_snapshot(records, pcab=pcab, as_of=source_as_of)
    concentrations = contractor_concentrations(
        records,
        minimum_projects=minimum_concentration_projects,
    )
    district_snapshot = _load_district_snapshot(
        district_snapshot_paths,
        district_retrieved_on,
    )
    signal_counts = Counter(signal.code for signal in snapshot.signals)
    pcab_status_counts = Counter(item.pcab_status for item in snapshot.contractors)
    metadata = {
        "contractors": str(len(snapshot.contractors)),
        "delivery_details": str(len(records)),
        "fiscal_years": ",".join(str(year) for year in fiscal_years),
        "integrity_signals": str(len(snapshot.signals)),
        "concentrations": str(len(concentrations)),
        "schema_version": "3",
        "source_artifact_sha256": source_digest,
        "source_records": str(len(records)),
        **{f"signal:{code}": str(count) for code, count in sorted(signal_counts.items())},
        **{
            f"pcab_status:{status}": str(count)
            for status, count in sorted(pcab_status_counts.items())
        },
    }
    if pcab is not None:
        metadata.update(
            {
                "pcab_records": str(pcab.record_count),
                "pcab_retrieved_on": pcab.retrieved_on.isoformat(),
                "pcab_source_sha256": pcab.source_sha256,
            }
        )
    if source_as_of is not None:
        metadata["source_as_of"] = source_as_of.isoformat()
    if district_snapshot is not None:
        metadata.update(_district_metadata(district_snapshot, records))
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
            "050-delivery-details",
            (_detail_statement(record) for record in records),
            chunk_rows,
        )
    )
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
    chunks.extend(
        _write_chunks(
            chunks_dir,
            "300-concentrations",
            (_concentration_statement(item) for item in concentrations),
            chunk_rows,
        )
    )
    if district_snapshot is not None:
        chunks.extend(
            _write_chunks(
                chunks_dir,
                "400-district-offices",
                (
                    _district_statement(key, item, district_snapshot)
                    for key, item in district_snapshot.offices.items()
                ),
                chunk_rows,
            )
        )
    district_offices = district_snapshot.office_count if district_snapshot else 0
    _verify_bundle(
        chunks,
        (
            len(records),
            len(snapshot.signals),
            len(snapshot.contractors),
            len(concentrations),
            district_offices,
        ),
    )
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
        concentrations=len(concentrations),
        district_offices=district_offices,
        sql_chunks=len(chunks),
        manifest_sha256=manifest_sha256,
    )
