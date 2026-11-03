"""Build deterministic static assets and reviewed D1 seed data for Busisi."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.publication import ProjectDossierView, build_publication
from engine.budget_watchdog.site_builder import build_site


@dataclass(frozen=True, slots=True)
class CloudflareBundleResult:
    output_dir: Path
    reviewed_records: int
    static_pages: int
    seed_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_value(value: str | int) -> str:
    return str(value) if isinstance(value, int) else _sql_text(value)


def _project_values(record: ProjectDossierView) -> tuple[str | int, ...]:
    return (
        record.slug,
        record.case_id,
        record.title,
        record.fiscal_year,
        record.location,
        record.appropriation_centavos,
        record.contract_budget_centavos,
        record.variance_centavos,
        record.contract_id,
        record.delivery_title,
        record.implementing_office,
        record.source_of_funds,
        record.confidence,
        record.confidence_score,
        json.dumps(record.match_signals, ensure_ascii=False, separators=(",", ":")),
        record.match_limitations,
        json.dumps(record.evidence_urls, ensure_ascii=False, separators=(",", ":")),
        record.family_id,
        record.family_label,
        record.status_label,
        "reviewed" if record.is_confirmed_link else "quarantine",
        int(record.is_confirmed_link),
    )


def _seed_sql(records: tuple[ProjectDossierView, ...], metadata: dict[str, str]) -> str:
    lines = ["DELETE FROM project_search;", "DELETE FROM projects;", "DELETE FROM metadata;"]
    for key, value in sorted(metadata.items()):
        lines.append(
            f"INSERT INTO metadata (key, value) VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608 - escaped offline seed generation
        )
    for record in records:
        values = ", ".join(_sql_value(value) for value in _project_values(record))
        lines.append(
            f"INSERT INTO projects VALUES ({values});"  # noqa: S608 - escaped seed values
        )
        search_values = (
            record.slug,
            record.title,
            record.location,
            record.contract_id,
            record.delivery_title,
            record.implementing_office,
        )
        search = ", ".join(_sql_text(value) for value in search_values)
        lines.append(
            f"INSERT INTO project_search VALUES ({search});"  # noqa: S608 - escaped seed values
        )
    return "\n".join(lines) + "\n"


def _verify_sql(migration: str, seed: str, expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(migration)
        connection.executescript(seed)
        actual = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("generated D1 seed failed verification")


def build_cloudflare_bundle(
    golden_path: Path,
    migration_path: Path,
    output_dir: Path,
) -> CloudflareBundleResult:
    if not migration_path.is_file():
        raise ValueError("D1 migration does not exist")
    publication = build_publication(golden_path)
    golden_digest = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    metadata = {
        "golden_sha256": golden_digest,
        "release_ready": json.dumps(publication.release_gate.release_ready),
        "reviewed_cases": str(publication.release_gate.reviewed_cases),
        "schema_version": "1",
    }
    seed = _seed_sql(publication.dossiers, metadata)
    migration = migration_path.read_text(encoding="utf-8")
    _verify_sql(migration, seed, len(publication.dossiers))

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    site = build_site(golden_path, building / "public")
    (building / "reviewed-seed.sql").write_text(seed, encoding="utf-8")
    manifest = {
        "golden_sha256": golden_digest,
        "release_ready": publication.release_gate.release_ready,
        "reviewed_cases": publication.release_gate.reviewed_cases,
        "schema_version": 1,
    }
    (building / "publication-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return CloudflareBundleResult(
        output_dir=output_dir,
        reviewed_records=len(publication.dossiers),
        static_pages=site.pages_written,
        seed_sha256=hashlib.sha256(seed.encode()).hexdigest(),
    )
