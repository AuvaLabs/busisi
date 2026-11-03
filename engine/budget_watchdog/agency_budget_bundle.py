"""Build a verified D1 bundle for the FY2027 appropriation-head ledger."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.agency_budgets import (
    BASELINE_YEAR,
    FISCAL_YEAR,
    HOUSE_CONGRESS_SPECS,
    HOUSE_HEAD_SPECS,
    HOUSE_SPF_SPECS,
    AgencyBudgetRecord,
    build_agency_budget_records,
    parse_house_totals,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0008_agency_budgets.sql"
)
ALL_HOUSE_SPECS = HOUSE_HEAD_SPECS + HOUSE_SPF_SPECS + HOUSE_CONGRESS_SPECS


@dataclass(frozen=True, slots=True)
class AgencyBudgetBundleResult:
    output_dir: Path
    record_count: int
    compared_records: int
    unavailable_records: int
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
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _document_map(snapshot_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents = manifest.get("documents")
    if not isinstance(documents, list):
        raise ValueError("snapshot document manifest is missing")
    output = {}
    for document in documents:
        path = snapshot_dir / str(document["path"])
        if not path.is_file():
            raise ValueError(f"snapshot document is missing: {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != document.get("sha256"):
            raise ValueError(f"snapshot document digest mismatch: {path.name}")
        key = str(document["key"])
        if key in output:
            raise ValueError(f"duplicate snapshot document key: {key}")
        output[key] = {**document, "path_object": path}
    return output


def _load_json(document: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(document["path_object"].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("snapshot JSON document must be an object")
    return payload


def _load_records(
    snapshot_dir: Path,
) -> tuple[tuple[AgencyBudgetRecord, ...], dict[str, dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((snapshot_dir / "snapshot-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("fiscal_year") != FISCAL_YEAR or manifest.get("baseline_year") != BASELINE_YEAR:
        raise ValueError("agency budget snapshot fiscal boundary is invalid")
    documents = _document_map(snapshot_dir, manifest)
    required = {"nep-overview", "nep-departments", "nep-congress", "house-ia", "house-ib"}
    if not required.issubset(documents):
        raise ValueError("agency budget snapshot is incomplete")
    house_text = {
        key: documents[key]["path_object"].read_text(encoding="utf-8")
        for key in ("house-ia", "house-ib")
    }
    house_totals = parse_house_totals(house_text, ALL_HOUSE_SPECS)
    departments_payload = _load_json(documents["nep-departments"])
    overview_payload = _load_json(documents["nep-overview"])
    departments = departments_payload.get("data", [])
    national_amount = overview_payload.get("data", {}).get("national", {}).get("amount")
    if (
        not isinstance(departments, list)
        or sum(int(row["amount"]) for row in departments) != national_amount
    ):
        raise ValueError("NEP national control total does not reconcile")
    records = build_agency_budget_records(
        departments_payload,
        _load_json(documents["nep-congress"]),
        house_totals,
    )
    house_by_id = {record.record_id: record.amount_pesos for record in house_totals}
    actual_house = sum(house_by_id[spec.record_id] for spec in HOUSE_HEAD_SPECS)
    actual_house += sum(house_by_id[spec.record_id] for spec in HOUSE_SPF_SPECS)
    if actual_house != manifest.get("house_control_pesos"):
        raise ValueError("House control total does not reconcile")
    return records, documents, manifest


def _record_statement(record: AgencyBudgetRecord, documents: dict[str, dict[str, Any]]) -> str:
    nep_document = documents["nep-departments"]
    if record.level == "congress_institution":
        nep_document = documents["nep-congress"]
    house_document = documents.get(record.house_document_key or "")
    note = (
        "Compared with a page-specific total in the mirrored HB 10858 third-reading volume."
        if house_document
        else "Automatic appropriations are outside the House general appropriations bill comparison."
    )
    values = (
        record.record_id,
        record.fiscal_year,
        record.baseline_year,
        record.level,
        record.parent_id,
        record.code,
        record.name,
        record.base_centavos,
        record.nep_centavos,
        record.house_centavos,
        record.difference_centavos,
        record.change_bps,
        record.stage_status,
        record.house_document_key,
        json.dumps(record.house_pages, separators=(",", ":")),
        house_document.get("source_url") if house_document else None,
        nep_document["source_url"],
        nep_document["sha256"],
        house_document.get("pdf_sha256") if house_document else None,
        note,
    )
    return f"INSERT INTO agency_budget_items VALUES ({_sql_values(values)});"  # noqa: S608


def _write_chunks(directory: Path, rows: Iterable[str], size: int) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(rows, size), start=1):
        path = directory / f"100-agency-budgets-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _verify(chunks: Sequence[Path], expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = connection.execute("SELECT COUNT(*) FROM agency_budget_items").fetchone()[0]
        unavailable = connection.execute(
            "SELECT COUNT(*) FROM agency_budget_items WHERE stage_status = 'not_applicable'"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or unavailable != 1 or integrity != "ok":
        raise ValueError("agency budget D1 bundle verification failed")


def build_agency_budget_bundle(
    snapshot_dir: Path, output_dir: Path, *, chunk_rows: int = 100
) -> AgencyBudgetBundleResult:
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    records, documents, source_manifest = _load_records(snapshot_dir)
    compared = sum(record.stage_status == "compared" for record in records)
    unavailable = len(records) - compared
    head_records = tuple(record for record in records if record.level == "appropriation_head")
    metadata = {
        "fiscal_year": "2027",
        "baseline_year": "2026",
        "record_count": str(len(records)),
        "appropriation_heads": str(len(head_records)),
        "congress_institutions": str(len(records) - len(head_records)),
        "compared_records": str(compared),
        "unavailable_records": str(unavailable),
        "house_control_centavos": str(int(source_manifest["house_control_pesos"]) * 100),
        "nep_bill_scope_centavos": str(
            sum(record.nep_centavos for record in head_records if record.code != "AUTO")
        ),
        "house_bill_scope_centavos": str(
            sum(record.house_centavos or 0 for record in head_records)
        ),
    }
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata_path = chunks_dir / "000-metadata.sql"
    metadata_lines = ["DELETE FROM agency_budget_items;", "DELETE FROM agency_budget_metadata;"]
    metadata_lines.extend(
        f"INSERT INTO agency_budget_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    metadata_path.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")
    chunks = [
        metadata_path,
        *_write_chunks(
            chunks_dir,
            (_record_statement(record, documents) for record in records),
            chunk_rows,
        ),
    ]
    _verify(chunks, len(records))
    manifest = {
        **metadata,
        "source_manifest_sha256": hashlib.sha256(
            (snapshot_dir / "snapshot-manifest.json").read_bytes()
        ).hexdigest(),
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
    return AgencyBudgetBundleResult(
        output_dir,
        len(records),
        compared,
        unavailable,
        len(chunks),
        manifest_sha256,
    )
