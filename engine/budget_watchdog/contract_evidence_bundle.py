"""Build the contract-lifecycle evidence D1 import bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.contract_evidence import (
    ContractEvidenceCatalog,
    ContractEvidenceItem,
    load_contract_evidence_catalog,
    summarize_contract_evidence,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0015_contract_evidence.sql"
)


@dataclass(frozen=True, slots=True)
class ContractEvidenceBundleResult:
    output_dir: Path
    contract_count: int
    item_count: int
    retry_item_count: int
    catalog_sha256: str
    bundle_sha256: str


def _text(value: str | None) -> str:
    return "NULL" if value is None else f"'{value.replace("'", "''")}'"


def _number(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _item_statement(catalog: ContractEvidenceCatalog, item: ContractEvidenceItem) -> str:
    values = (
        _text(item.evidence_id),
        _text(item.case_id),
        _text(item.contract_id),
        str(item.fiscal_year),
        _text(item.stage),
        str(catalog.stage_order.index(item.stage)),
        _text(item.status),
        _text(item.evidence_class),
        _text(item.title),
        _text(item.reported_date),
        _text(item.date_kind),
        _text(item.source_title),
        _text(item.source_url),
        _text(item.source_row_id),
        _text(item.artifact_sha256),
        _text(item.source_revision),
        _text(item.last_checked_at),
        _number(item.http_status),
        "1" if item.retry_eligible else "0",
        _text(item.limitation),
    )
    return f"INSERT INTO contract_evidence_items VALUES ({', '.join(values)});"  # noqa: S608


def _render(catalog: ContractEvidenceCatalog, catalog_sha256: str) -> str:
    summary = summarize_contract_evidence(catalog)
    metadata = {
        "schema_version": "1",
        "checked_at": catalog.checked_at,
        "catalog_sha256": catalog_sha256,
        "contract_count": str(summary.contract_count),
        "item_count": str(summary.item_count),
        "retry_item_count": str(summary.retry_item_count),
        **{f"status:{key}": str(value) for key, value in summary.status_counts.items()},
    }
    lines = [
        "DELETE FROM contract_evidence_items;",
        "DELETE FROM contract_evidence_metadata;",
        *(
            f"INSERT INTO contract_evidence_metadata VALUES ({_text(key)}, {_text(value)});"  # noqa: S608
            for key, value in sorted(metadata.items())
        ),
        *(_item_statement(catalog, item) for item in catalog.items),
    ]
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(sql)
        count = connection.execute("SELECT COUNT(*) FROM contract_evidence_items").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if count != expected or integrity != "ok":
        raise ValueError("contract evidence D1 bundle verification failed")


def build_contract_evidence_bundle(
    catalog_path: Path,
    output_dir: Path,
) -> ContractEvidenceBundleResult:
    payload = catalog_path.read_bytes()
    catalog = load_contract_evidence_catalog(payload)
    summary = summarize_contract_evidence(catalog)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render(catalog, catalog_sha256)
    _verify(sql, summary.item_count)

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle = building / "contract-evidence.sql"
    bundle.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_sha256": bundle_sha256,
                "catalog_sha256": catalog_sha256,
                "contract_count": summary.contract_count,
                "item_count": summary.item_count,
                "retry_item_count": summary.retry_item_count,
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
    return ContractEvidenceBundleResult(
        output_dir=output_dir,
        contract_count=summary.contract_count,
        item_count=summary.item_count,
        retry_item_count=summary.retry_item_count,
        catalog_sha256=catalog_sha256,
        bundle_sha256=bundle_sha256,
    )
