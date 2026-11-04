"""Build a verified D1 bundle for a scoped official facility registry."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engine.budget_watchdog.facility_identity import FacilityLink, FacilityRegistryRecord
from engine.budget_watchdog.facility_release_gate import (
    MIN_AGREEMENT_BPS,
    MIN_PRECISION_BPS,
    MIN_REVIEWED_CASES,
    candidate_set_sha256,
    evaluate_facility_release,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = (
    ROOT / "cloudflare/busisi/migrations/0026_facility_identity.sql",
    ROOT / "cloudflare/busisi/migrations/0027_facility_registry_details.sql",
)


@dataclass(frozen=True, slots=True)
class FacilityRegistrySource:
    source_id: str
    publisher: str
    dataset_name: str
    source_url: str
    artifact_sha256: str
    acquired_at: str
    scope_note: str
    status: Literal["active", "partial", "superseded"]


@dataclass(frozen=True, slots=True)
class FacilityRegistryBundleResult:
    output_dir: Path
    source_count: int
    facility_count: int
    link_count: int
    sql_sha256: str
    manifest_sha256: str


def _text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _optional_integer(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _source_sql(source: FacilityRegistrySource) -> str:
    values = (
        source.source_id,
        source.publisher,
        source.dataset_name,
        source.source_url,
        source.artifact_sha256,
        source.acquired_at,
        source.scope_note,
        source.status,
    )
    return f"INSERT INTO facility_registry_sources VALUES ({', '.join(_text(value) for value in values)});"  # noqa: S608


def _identity_sql(record: FacilityRegistryRecord) -> str:
    values = [
        _text(record.facility_id),
        _text(record.facility_type),
        _text(record.official_id),
        _text(record.official_name),
        _text(record.municipality),
        _text(record.province),
        _text(record.region),
        _optional_integer(record.latitude_e6),
        _optional_integer(record.longitude_e6),
        _text(record.source_id),
    ]
    return f"INSERT INTO facility_identities VALUES ({', '.join(values)});"  # noqa: S608


def _detail_sql(record: FacilityRegistryRecord) -> str:
    if record.source_row is None:
        raise ValueError("facility registry source row is required")
    values = (
        _text(record.facility_id),
        str(record.source_row),
        _text(record.division),
        str(int(record.demolition_required)),
        str(int(record.geotechnical_report)),
        str(int(record.site_development_plan)),
        str(int(record.ownership_documents)),
    )
    ordered = (values[0], values[2], values[1], *values[3:])
    return f"INSERT INTO facility_identity_details VALUES ({', '.join(ordered)});"  # noqa: S608


def _link_sql(link: FacilityLink, reviewed_at: str) -> str:
    facility_id = "NULL" if link.facility_id is None else _text(link.facility_id)
    group_key = "NULL" if link.record_group_key is None else _text(link.record_group_key)
    values = (
        _text(link.source_type),
        _text(link.record_id),
        _text(link.match_state),
        facility_id,
        group_key,
        _text(link.record_group_label),
        _text(link.match_method),
        str(link.confidence),
        _text(json.dumps(link.signals, separators=(",", ":"))),
        _text(link.limitation),
        _text(reviewed_at),
    )
    return f"INSERT INTO facility_record_links VALUES ({', '.join(values)});"  # noqa: S608


def _sql(
    records: tuple[FacilityRegistryRecord, ...],
    source: FacilityRegistrySource,
    links: tuple[FacilityLink, ...],
) -> str:
    if not records or any(record.source_id != source.source_id for record in records):
        raise ValueError("facility records must belong to the registered source")
    lines = [
        "DELETE FROM facility_record_links;",
        "DELETE FROM facility_identity_details;",
        "DELETE FROM facility_identities;",
        "DELETE FROM facility_registry_sources;",
        _source_sql(source),
    ]
    for record in records:
        lines.extend((_identity_sql(record), _detail_sql(record)))
    lines.extend(
        _link_sql(link, source.acquired_at) for link in links if link.match_state != "unlinked"
    )
    return "\n".join(lines) + "\n"


def _verify(sql: str, expected: int, expected_links: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for migration in MIGRATIONS:
            connection.executescript(migration.read_text(encoding="utf-8"))
        connection.executescript(sql)
        source_count = connection.execute(
            "SELECT COUNT(*) FROM facility_registry_sources"
        ).fetchone()[0]
        facility_count = connection.execute("SELECT COUNT(*) FROM facility_identities").fetchone()[
            0
        ]
        detail_count = connection.execute(
            "SELECT COUNT(*) FROM facility_identity_details"
        ).fetchone()[0]
        link_count = connection.execute("SELECT COUNT(*) FROM facility_record_links").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if (
        source_count != 1
        or facility_count != expected
        or detail_count != expected
        or link_count != expected_links
        or integrity != "ok"
    ):
        raise ValueError("facility registry bundle verification failed")


def build_facility_registry_bundle(
    records: tuple[FacilityRegistryRecord, ...],
    source: FacilityRegistrySource,
    output_dir: Path,
    *,
    links: tuple[FacilityLink, ...] = (),
    review_manifest: dict[str, Any] | None = None,
) -> FacilityRegistryBundleResult:
    """Write and independently replay one atomic facility-registry release."""

    candidate_digest = candidate_set_sha256(links)
    release_gate = (
        evaluate_facility_release(review_manifest, links, source.artifact_sha256)
        if review_manifest is not None
        else None
    )
    if (
        release_gate is not None
        and release_gate.passed
        and (
            release_gate.reviewed_cases < MIN_REVIEWED_CASES
            or release_gate.precision_bps < MIN_PRECISION_BPS
            or release_gate.agreement_bps < MIN_AGREEMENT_BPS
            or release_gate.critical_failures != 0
            or release_gate.reasons
        )
    ):
        raise ValueError("facility release gate result is inconsistent")
    published_links = tuple(
        link
        for link in links
        if release_gate is not None and release_gate.passed and link.match_state == "official_exact"
    )
    sql = _sql(records, source, published_links)
    _verify(sql, len(records), len(published_links))
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    sql_path = building / "facility-registry.sql"
    sql_path.write_text(sql, encoding="utf-8")
    sql_sha256 = hashlib.sha256(sql_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "source_id": source.source_id,
        "source_count": 1,
        "facility_count": len(records),
        "link_count": len(published_links),
        "link_states": {
            state: sum(link.match_state == state for link in published_links)
            for state in ("official_exact", "group_only", "ambiguous")
        },
        "candidate_count": sum(link.match_state == "official_exact" for link in links),
        "candidate_set_sha256": candidate_digest,
        "release_gate": (
            {
                "passed": release_gate.passed,
                "manifest_sha256": release_gate.manifest_sha256,
                "reviewed_cases": release_gate.reviewed_cases,
                "precision_bps": release_gate.precision_bps,
                "agreement_bps": release_gate.agreement_bps,
                "critical_failures": release_gate.critical_failures,
                "reasons": list(release_gate.reasons),
            }
            if release_gate is not None
            else None
        ),
        "artifact_sha256": source.artifact_sha256,
        "source_url": source.source_url,
        "acquired_at": source.acquired_at,
        "sql_sha256": sql_sha256,
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return FacilityRegistryBundleResult(
        output_dir,
        1,
        len(records),
        len(published_links),
        sql_sha256,
        manifest_sha256,
    )
