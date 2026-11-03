"""Build a reconciled D1 import bundle for the Senate budget-cycle catalogue."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.senate_budget import (
    STAGES,
    SenateCatalog,
    load_senate_catalog,
    reconcile_senate_catalog,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0010_budget_cycle.sql"
)


@dataclass(frozen=True, slots=True)
class SenateBudgetBundleResult:
    output_dir: Path
    document_count: int
    verified_document_count: int
    catalog_sha256: str
    bundle_sha256: str


def _sql_text(value: str | None) -> str:
    if value is None:
        return "NULL"
    return f"'{value.replace("'", "''")}'"


def _document_statement(catalog: SenateCatalog, index: int) -> str:
    document = catalog.documents[index]
    values = (
        _sql_text(document.document_id),
        str(catalog.fiscal_year),
        _sql_text(document.source_record_id),
        _sql_text(document.title),
        _sql_text(document.stage),
        _sql_text(document.stage_label),
        _sql_text(document.publisher),
        _sql_text(document.volume),
        _sql_text(document.publication_date),
        _sql_text(document.source_url),
        _sql_text(document.viewer_url),
        _sql_text(document.acquisition_status),
        _sql_text(document.artifact_sha256),
        str(document.byte_size) if document.byte_size is not None else "NULL",
        _sql_text(document.mirror_url),
        _sql_text(document.evidence_note),
    )
    return f"INSERT INTO budget_cycle_documents VALUES ({', '.join(values)});"  # noqa: S608


def _render_bundle(catalog: SenateCatalog, catalog_sha256: str) -> str:
    summary = reconcile_senate_catalog(catalog)
    metadata = {
        "fiscal_year": str(catalog.fiscal_year),
        "document_count": str(summary.document_count),
        "verified_document_count": str(summary.verified_document_count),
        "discovered_document_count": str(summary.discovered_document_count),
        "source_url": catalog.source_url,
        "retrieved_at": catalog.retrieved_at,
        "acquisition_status": catalog.acquisition_status,
        "discovery_source_id": catalog.discovery_source_id or "",
        "catalog_sha256": catalog_sha256,
    }
    lines = [
        "DELETE FROM budget_cycle_documents;",
        "DELETE FROM budget_cycle_stages;",
        "DELETE FROM budget_cycle_metadata;",
    ]
    lines.extend(
        f"INSERT INTO budget_cycle_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    lines.extend(
        "INSERT INTO budget_cycle_stages VALUES "  # noqa: S608
        f"({_sql_text(coverage.stage)}, {index}, {_sql_text(coverage.status)}, "
        f"{coverage.document_count});"
        for index, coverage in enumerate(catalog.stage_coverage, start=1)
    )
    lines.extend(_document_statement(catalog, index) for index in range(len(catalog.documents)))
    return "\n".join(lines) + "\n"


def _verify_bundle(sql: str, expected_documents: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(sql)
        document_count = connection.execute(
            "SELECT COUNT(*) FROM budget_cycle_documents"
        ).fetchone()[0]
        stage_count = connection.execute("SELECT COUNT(*) FROM budget_cycle_stages").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if document_count != expected_documents or stage_count != len(STAGES) or integrity != "ok":
        raise ValueError("budget-cycle D1 bundle verification failed")


def build_senate_budget_bundle(catalog_path: Path, output_dir: Path) -> SenateBudgetBundleResult:
    """Validate a catalogue, reconcile its stages and atomically emit D1 SQL."""

    payload = catalog_path.read_bytes()
    catalog = load_senate_catalog(payload)
    summary = reconcile_senate_catalog(catalog)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render_bundle(catalog, catalog_sha256)
    _verify_bundle(sql, summary.document_count)

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle_path = building / "budget-cycle.sql"
    bundle_path.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    manifest = {
        "catalog_sha256": catalog_sha256,
        "bundle_sha256": bundle_sha256,
        "document_count": summary.document_count,
        "verified_document_count": summary.verified_document_count,
        "discovered_document_count": summary.discovered_document_count,
        "unavailable_stages": list(summary.unavailable_stages),
    }
    (building / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return SenateBudgetBundleResult(
        output_dir=output_dir,
        document_count=summary.document_count,
        verified_document_count=summary.verified_document_count,
        catalog_sha256=catalog_sha256,
        bundle_sha256=bundle_sha256,
    )
