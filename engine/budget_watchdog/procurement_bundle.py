"""Build the reviewed procurement evidence D1 import bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.procurement import (
    ProcurementCatalog,
    ProcurementCoverage,
    ProcurementRecord,
    ProcurementSource,
    load_procurement_catalog,
    summarize_procurement_catalog,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0013_procurement_evidence.sql"
)


@dataclass(frozen=True, slots=True)
class ProcurementBundleResult:
    output_dir: Path
    source_count: int
    archived_sources: int
    record_count: int
    checked_projects: int
    projects_with_evidence: int
    catalog_sha256: str
    bundle_sha256: str


def _text(value: str | None) -> str:
    return "NULL" if value is None else f"'{value.replace("'", "''")}'"


def _number(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _json(value: object) -> str:
    return _text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _source_statement(item: ProcurementSource) -> str:
    values = (
        _text(item.source_id),
        _text(item.title),
        _text(item.publisher),
        _text(item.document_type),
        str(item.fiscal_year),
        _text(item.reporting_cutoff),
        _text(item.source_url),
        _text(item.acquisition_status),
        _text(item.artifact_sha256),
        _number(item.byte_size),
        _number(item.page_count),
        _text(item.evidence_note),
    )
    return f"INSERT INTO procurement_sources VALUES ({', '.join(values)});"  # noqa: S608


def _record_statement(item: ProcurementRecord) -> str:
    events = [
        {"stage": event.stage, "event_date": event.event_date, "date_kind": event.date_kind}
        for event in item.events
    ]
    values = (
        _text(item.evidence_id),
        _text(item.case_id),
        _text(item.contract_id),
        str(item.fiscal_year),
        _text(item.source_id),
        _text(item.evidence_type),
        _text(item.match_basis),
        _text(item.project_title),
        _text(item.procuring_entity),
        _text(item.procurement_mode),
        _text(item.procurement_status),
        _number(item.page_number),
        _text(item.reference_number),
        _number(item.abc_centavos),
        _number(item.contract_cost_centavos),
        _number(item.savings_centavos),
        _json(item.observers),
        _json(events),
        _text(item.reviewed_at),
        _text(item.boundary_note),
    )
    return f"INSERT INTO procurement_records VALUES ({', '.join(values)});"  # noqa: S608


def _coverage_statement(item: ProcurementCoverage) -> str:
    values = (
        _text(item.case_id),
        _text(item.contract_id),
        str(item.fiscal_year),
        _text(item.status),
        str(item.record_count),
        _text(item.review_note),
        _text(item.reviewed_at),
    )
    return f"INSERT INTO procurement_project_coverage VALUES ({', '.join(values)});"  # noqa: S608


def _render_bundle(catalog: ProcurementCatalog, catalog_sha256: str) -> str:
    summary = summarize_procurement_catalog(catalog)
    metadata = {
        "schema_version": "1",
        "checked_at": catalog.checked_at,
        "catalog_sha256": catalog_sha256,
        "source_count": str(summary.source_count),
        "archived_sources": str(summary.archived_sources),
        "record_count": str(summary.record_count),
        "exact_records": str(summary.exact_records),
        "checked_projects": str(summary.checked_projects),
        "projects_with_evidence": str(summary.projects_with_evidence),
        **{f"status:{key}": str(value) for key, value in summary.status_counts.items()},
    }
    lines = [
        "DELETE FROM procurement_records;",
        "DELETE FROM procurement_project_coverage;",
        "DELETE FROM procurement_sources;",
        "DELETE FROM procurement_metadata;",
    ]
    lines.extend(
        f"INSERT INTO procurement_metadata VALUES ({_text(key)}, {_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    lines.extend(_source_statement(item) for item in catalog.sources)
    lines.extend(_record_statement(item) for item in catalog.records)
    lines.extend(_coverage_statement(item) for item in catalog.coverage)
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: tuple[int, int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(sql)
        actual = (
            connection.execute("SELECT COUNT(*) FROM procurement_sources").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM procurement_records").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM procurement_project_coverage").fetchone()[0],
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("procurement evidence D1 bundle verification failed")


def build_procurement_bundle(catalog_path: Path, output_dir: Path) -> ProcurementBundleResult:
    payload = catalog_path.read_bytes()
    catalog = load_procurement_catalog(payload)
    summary = summarize_procurement_catalog(catalog)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render_bundle(catalog, catalog_sha256)
    _verify(sql, (summary.source_count, summary.record_count, summary.checked_projects))

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle = building / "procurement-evidence.sql"
    bundle.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "archived_sources": summary.archived_sources,
                "bundle_sha256": bundle_sha256,
                "catalog_sha256": catalog_sha256,
                "checked_projects": summary.checked_projects,
                "projects_with_evidence": summary.projects_with_evidence,
                "record_count": summary.record_count,
                "source_count": summary.source_count,
                "status_counts": dict(summary.status_counts),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return ProcurementBundleResult(
        output_dir,
        summary.source_count,
        summary.archived_sources,
        summary.record_count,
        summary.checked_projects,
        summary.projects_with_evidence,
        catalog_sha256,
        bundle_sha256,
    )
