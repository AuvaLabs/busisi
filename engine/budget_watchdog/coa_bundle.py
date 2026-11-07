"""Build the reviewed Commission on Audit evidence D1 import bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.coa import (
    CoaCatalog,
    CoaProjectCoverage,
    CoaReport,
    CoaSourceCatalog,
    load_coa_catalog,
    summarize_coa_catalog,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0012_coa_audit_evidence.sql"
)


@dataclass(frozen=True, slots=True)
class CoaBundleResult:
    output_dir: Path
    report_count: int
    archived_reports: int
    checked_projects: int
    project_matches: int
    catalog_sha256: str
    bundle_sha256: str


def _text(value: str | None) -> str:
    if value is None:
        return "NULL"
    return f"'{value.replace("'", "''")}'"


def _number(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _report_statement(report: CoaReport) -> str:
    values = (
        _text(report.report_id),
        _text(report.title),
        _text(report.report_type),
        _text(report.audited_entity),
        str(report.fiscal_year),
        _text(report.publication_date),
        _text(report.source_url),
        _text(report.landing_url),
        _text(report.acquisition_status),
        _text(report.artifact_sha256),
        _number(report.byte_size),
        _number(report.page_count),
        _text(report.scope_note),
        _text(report.evidence_note),
    )
    return f"INSERT INTO coa_reports VALUES ({', '.join(values)});"  # noqa: S608


def _coverage_statement(item: CoaProjectCoverage) -> str:
    values = (
        _text(item.case_id),
        _text(item.contract_id),
        str(item.fiscal_year),
        _text(item.status),
        _text(item.report_id),
        _text(item.match_confidence),
        _text(json.dumps(item.match_basis, ensure_ascii=False, separators=(",", ":"))),
        _number(item.page_start),
        _number(item.page_end),
        _text(item.observation_summary),
        _text(item.recommendation_summary),
        _text(item.management_response),
        _text(item.implementation_status),
        _text(item.review_note),
        _text(item.reviewed_at),
    )
    return f"INSERT INTO coa_project_coverage VALUES ({', '.join(values)});"  # noqa: S608


def _catalog_statement(item: CoaSourceCatalog) -> str:
    values = (
        _text(item.catalog_id),
        _text(item.title),
        _text(item.source_url),
        _text(item.checked_status),
        _text(item.evidence_note),
    )
    return f"INSERT INTO coa_source_catalogs VALUES ({', '.join(values)});"  # noqa: S608


def _render_bundle(catalog: CoaCatalog, catalog_sha256: str) -> str:
    summary = summarize_coa_catalog(catalog)
    metadata = {
        "schema_version": "1",
        "checked_at": catalog.checked_at,
        "catalog_sha256": catalog_sha256,
        "catalog_count": str(len(catalog.catalogs)),
        "report_count": str(summary.report_count),
        "archived_reports": str(summary.archived_reports),
        "checked_projects": str(summary.checked_projects),
        "project_matches": str(summary.project_matches),
        **{f"status:{key}": str(value) for key, value in summary.status_counts.items()},
    }
    lines = [
        "DELETE FROM coa_project_coverage;",
        "DELETE FROM coa_reports;",
        "DELETE FROM coa_source_catalogs;",
        "DELETE FROM coa_metadata;",
    ]
    lines.extend(
        f"INSERT INTO coa_metadata VALUES ({_text(key)}, {_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    lines.extend(_catalog_statement(item) for item in catalog.catalogs)
    lines.extend(_report_statement(report) for report in catalog.reports)
    lines.extend(_coverage_statement(item) for item in catalog.project_coverage)
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: tuple[int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(sql)
        actual = (
            connection.execute("SELECT COUNT(*) FROM coa_reports").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM coa_project_coverage").fetchone()[0],
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("COA evidence D1 bundle verification failed")


def build_coa_bundle(catalog_path: Path, output_dir: Path) -> CoaBundleResult:
    payload = catalog_path.read_bytes()
    catalog = load_coa_catalog(payload)
    summary = summarize_coa_catalog(catalog)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render_bundle(catalog, catalog_sha256)
    _verify(sql, (summary.report_count, summary.checked_projects))

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle = building / "coa-audit-evidence.sql"
    bundle.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "archived_reports": summary.archived_reports,
                "bundle_sha256": bundle_sha256,
                "catalog_sha256": catalog_sha256,
                "checked_projects": summary.checked_projects,
                "project_matches": summary.project_matches,
                "report_count": summary.report_count,
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
    return CoaBundleResult(
        output_dir,
        summary.report_count,
        summary.archived_reports,
        summary.checked_projects,
        summary.project_matches,
        catalog_sha256,
        bundle_sha256,
    )
