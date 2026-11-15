"""Build a verified project-image publication bundle for D1 and private R2."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from engine.budget_watchdog.project_images import (
    ImageInspection,
    ProjectImageCoverage,
    ProjectImageRecord,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0021_project_images.sql"
)
SHA256_HEX_LENGTH = sha256().digest_size * 2


@dataclass(frozen=True, slots=True)
class AcquiredProjectImage:
    metadata: ProjectImageRecord
    inspection: ImageInspection
    archive_key: str
    source_path: Path


@dataclass(frozen=True, slots=True)
class ProjectImageBundleResult:
    output_dir: Path
    contract_count: int
    verified_image_count: int
    quarantined_image_count: int
    sql_sha256: str
    manifest_sha256: str


def _sql(value: str | int | float | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{value.replace("'", "''")}'"


def _coverage_statement(item: ProjectImageCoverage, retrieved_at: str) -> str:
    values: tuple[str | int, ...] = (
        item.contract_id,
        item.summary_count,
        item.endpoint_count,
        int(item.has_images),
        item.state,
        item.detail_sha256,
        item.list_sha256,
        retrieved_at,
        item.note,
    )
    return (
        f"INSERT INTO project_image_coverage VALUES ({', '.join(_sql(value) for value in values)});"  # noqa: S608
    )


def _image_statement(item: AcquiredProjectImage, publication_status: str) -> str:
    metadata = item.metadata
    inspection = item.inspection
    values: tuple[str | int | float | None, ...] = (
        metadata.image_id,
        metadata.contract_id,
        metadata.component_id,
        metadata.photo_number,
        metadata.purpose,
        metadata.status,
        metadata.captured_at,
        metadata.fiscal_year,
        metadata.latitude,
        metadata.longitude,
        metadata.coordinate_status,
        metadata.source_url,
        metadata.thumbnail_source_url,
        inspection.sha256,
        inspection.content_type,
        inspection.byte_size,
        inspection.width,
        inspection.height,
        item.archive_key,
        publication_status,
    )
    return f"INSERT INTO project_images VALUES ({', '.join(_sql(value) for value in values)});"  # noqa: S608


def _verify(sql: str, expected_contracts: int, expected_images: int) -> None:
    database = sqlite3.connect(":memory:")
    try:
        database.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        database.executescript(sql)
        actual = (
            database.execute("SELECT COUNT(*) FROM project_image_coverage").fetchone()[0],
            database.execute("SELECT COUNT(*) FROM project_images").fetchone()[0],
        )
        orphaned = database.execute(
            "SELECT COUNT(*) FROM project_images image LEFT JOIN project_image_coverage coverage "
            "ON coverage.contract_id = image.contract_id WHERE coverage.contract_id IS NULL"
        ).fetchone()[0]
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        database.close()
    if actual != (expected_contracts, expected_images) or orphaned or integrity != "ok":
        raise ValueError("project-image D1 bundle verification failed")


def _materialize_media(source: Path, destination: Path) -> None:
    """Reuse immutable archive bytes when possible, with a portable copy fallback."""

    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def _digest_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _previous_media(manifest: dict[str, Any] | None) -> dict[str, tuple[str, int]]:
    if manifest is None:
        return {}
    media = manifest.get("media", [])
    if not isinstance(media, list):
        raise ValueError("previous project-image manifest has invalid media")
    result: dict[str, tuple[str, int]] = {}
    for item in media:
        if not isinstance(item, dict):
            raise ValueError("previous project-image manifest has invalid media")
        key = item.get("archive_key")
        digest = item.get("sha256")
        byte_size = item.get("byte_size")
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(digest, str)
            or len(digest) != SHA256_HEX_LENGTH
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size <= 0
            or key in result
        ):
            raise ValueError("previous project-image manifest has invalid media")
        result[key] = (digest, byte_size)
    return result


def _previous_states(manifest: dict[str, Any] | None) -> dict[str, str]:
    if manifest is None:
        return {}
    contracts = manifest.get("contracts", {})
    if not isinstance(contracts, dict):
        raise ValueError("previous project-image manifest has invalid contracts")
    return {
        contract_id: value.get("state", "")
        for contract_id, value in contracts.items()
        if isinstance(contract_id, str) and isinstance(value, dict)
    }


def _publishable_images(
    coverage_by_contract: dict[str, ProjectImageCoverage],
    images: tuple[AcquiredProjectImage, ...],
    previous_media: dict[str, tuple[str, int]],
    previous_states: dict[str, str],
) -> list[AcquiredProjectImage]:
    publishable: list[AcquiredProjectImage] = []
    for item in images:
        if not item.source_path.is_file():
            raise ValueError("project image payload is missing")
        source_size = item.source_path.stat().st_size
        if source_size <= 0:
            raise ValueError("project image payload is empty")
        if source_size != item.inspection.byte_size:
            raise ValueError("project image payload does not match its inspection")
        state = coverage_by_contract[item.metadata.contract_id].state
        current_identity = (item.inspection.sha256, item.inspection.byte_size)
        needs_upload = state == "verified_exact" and (
            previous_media.get(item.archive_key) != current_identity
            or previous_states.get(item.metadata.contract_id) != "verified_exact"
        )
        if needs_upload and _digest_file(item.source_path) != item.inspection.sha256:
            raise ValueError("project image payload does not match its inspection")
        if needs_upload:
            publishable.append(item)
    return publishable


def build_project_image_bundle(
    coverage: tuple[ProjectImageCoverage, ...],
    images: tuple[AcquiredProjectImage, ...],
    retrieved_at: str,
    output_dir: Path,
    *,
    previous_manifest: dict[str, Any] | None = None,
) -> ProjectImageBundleResult:
    """Write an atomic, self-verifying D1/R2 upload bundle."""
    coverage_by_contract = {item.contract_id: item for item in coverage}
    if len(coverage_by_contract) != len(coverage):
        raise ValueError("project-image coverage contains duplicate contracts")
    if any(item.metadata.contract_id not in coverage_by_contract for item in images):
        raise ValueError("project image has no coverage record")
    previous_media = _previous_media(previous_manifest)
    previous_states = _previous_states(previous_manifest)
    publishable = _publishable_images(
        coverage_by_contract, images, previous_media, previous_states
    )

    lines = ["DELETE FROM project_images;", "DELETE FROM project_image_coverage;"]
    lines.extend(
        _coverage_statement(item, retrieved_at)
        for item in sorted(coverage, key=lambda value: value.contract_id)
    )
    verified = 0
    quarantined = 0
    for item in sorted(images, key=lambda value: value.metadata.image_id):
        state = coverage_by_contract[item.metadata.contract_id].state
        status = "verified" if state == "verified_exact" else "quarantine"
        verified += status == "verified"
        quarantined += status == "quarantine"
        lines.append(_image_statement(item, status))
    sql = "\n".join(lines) + "\n"
    _verify(sql, len(coverage), len(images))

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    media_dir = building / "media"
    media_dir.mkdir(parents=True)
    for item in publishable:
        destination = media_dir / f"{item.inspection.sha256}.jpg"
        if (
            destination.exists()
            and _digest_file(destination) != item.inspection.sha256
        ):
            raise ValueError("project-image media digest collision")
        if not destination.exists():
            _materialize_media(item.source_path, destination)

    sql_path = building / "project-images.sql"
    sql_path.write_text(sql, encoding="utf-8")
    sql_digest = sha256(sql_path.read_bytes()).hexdigest()
    manifest = {
        "contract_count": len(coverage),
        "contracts": {
            item.contract_id: {
                "endpoint_count": item.endpoint_count,
                "state": item.state,
                "summary_count": item.summary_count,
            }
            for item in sorted(coverage, key=lambda value: value.contract_id)
        },
        "image_count": len(images),
        "media": [
            {
                "archive_key": item.archive_key,
                "byte_size": item.inspection.byte_size,
                "height": item.inspection.height,
                "sha256": item.inspection.sha256,
                "width": item.inspection.width,
            }
            for item in sorted(images, key=lambda value: value.archive_key)
        ],
        "quarantined_image_count": quarantined,
        "retrieved_at": retrieved_at,
        "sql_sha256": sql_digest,
        "verified_image_count": verified,
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha256 = sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return ProjectImageBundleResult(
        output_dir=output_dir,
        contract_count=len(coverage),
        verified_image_count=verified,
        quarantined_image_count=quarantined,
        sql_sha256=sql_digest,
        manifest_sha256=manifest_sha256,
    )
