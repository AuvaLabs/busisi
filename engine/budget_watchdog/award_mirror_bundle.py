"""Build the versioned PhilGEPS award mirror D1 import bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.award_mirror import AwardMirrorCatalog, load_award_mirror

MIGRATION_PATHS = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0014_contract_award_mirror.sql",
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0017_archived_award_mirror.sql",
)


@dataclass(frozen=True, slots=True)
class AwardMirrorBundleResult:
    output_dir: Path
    record_count: int
    catalog_sha256: str
    bundle_sha256: str


def _text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _record_statement(catalog: AwardMirrorCatalog, item) -> str:
    source = catalog.source
    values = (
        _text(item.source_row_id), _text(item.contract_id), str(item.fiscal_year),
        _text(item.reference_id), _text(item.award_title), _text(item.notice_title),
        _text(item.awardee_name), _text(item.organization_name), _text(item.area_of_delivery),
        _text(item.business_category), str(item.contract_amount_centavos),
        _text(item.award_date), _text(item.award_status), _text(item.row_sha256),
        _text(source.title), _text(source.publisher), _text(source.dataset_url),
        _text(source.file_url), _text(source.dataset_file), _text(source.revision),
        _text(source.last_modified), _text(source.retrieved_at), _text(source.license),
        _text(source.acquisition_status), _text(source.evidence_note),
    )
    return f"INSERT INTO contract_award_mirror_records VALUES ({', '.join(values)});"  # noqa: S608


def _render(catalog: AwardMirrorCatalog, catalog_sha256: str) -> str:
    metadata = {
        "schema_version": "1",
        "checked_at": catalog.checked_at,
        "catalog_sha256": catalog_sha256,
        "record_count": str(len(catalog.records)),
        "source_revision": catalog.source.revision,
        "source_file_archived": "1",
        "source_file_sha256": catalog.source.source_file_sha256,
        "source_file_byte_size": str(catalog.source.source_file_byte_size),
    }
    lines = [
        "DELETE FROM contract_award_mirror_records;",
        "DELETE FROM contract_award_mirror_metadata;",
        *(
            f"INSERT INTO contract_award_mirror_metadata VALUES ({_text(key)}, {_text(value)});"  # noqa: S608
            for key, value in sorted(metadata.items())
        ),
        *(_record_statement(catalog, item) for item in catalog.records),
    ]
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        for migration_path in MIGRATION_PATHS:
            connection.executescript(migration_path.read_text(encoding="utf-8"))
        connection.executescript(sql)
        count = connection.execute("SELECT COUNT(*) FROM contract_award_mirror_records").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if count != expected or integrity != "ok":
        raise ValueError("contract award mirror D1 bundle verification failed")


def build_award_mirror_bundle(catalog_path: Path, output_dir: Path) -> AwardMirrorBundleResult:
    payload = catalog_path.read_bytes()
    catalog = load_award_mirror(payload)
    catalog_sha256 = hashlib.sha256(payload).hexdigest()
    sql = _render(catalog, catalog_sha256)
    _verify(sql, len(catalog.records))

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    bundle = building / "contract-award-mirror.sql"
    bundle.write_text(sql, encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (building / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_sha256": bundle_sha256,
                "catalog_sha256": catalog_sha256,
                "record_count": len(catalog.records),
                "source_file_archived": True,
                "source_file_sha256": catalog.source.source_file_sha256,
                "source_file_byte_size": catalog.source.source_file_byte_size,
                "source_revision": catalog.source.revision,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return AwardMirrorBundleResult(output_dir, len(catalog.records), catalog_sha256, bundle_sha256)
