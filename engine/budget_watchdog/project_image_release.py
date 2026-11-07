"""Fail-closed checks for cumulative project-image releases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.project_image_queue import ImageCoverageSummary

_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_IMAGE_MIGRATION = _ROOT / "cloudflare/busisi/migrations/0021_project_images.sql"
_COVERAGE_MIGRATION = _ROOT / "cloudflare/busisi/migrations/0022_coverage_automation.sql"
_SHA256_LENGTH = 64


@dataclass(frozen=True, slots=True)
class CoverageRelease:
    release_id: str
    released_at: str
    source_sha256: str
    universe_contracts: int
    completed_contracts: int
    verified_exact_contracts: int
    no_image_contracts: int
    conflict_contracts: int
    retry_contracts: int
    blocked_contracts: int
    pending_contracts: int
    verified_images: int
    quarantined_images: int


def _count(manifest: dict[str, Any], key: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("project-image release manifest has an invalid count")
    return value


def _media(manifest: dict[str, Any]) -> dict[str, tuple[str, int]]:
    values = manifest.get("media")
    if isinstance(values, dict):
        values = [
            {**value, "sha256": digest}
            for digest, value in values.items()
            if isinstance(value, dict)
        ]
    if not isinstance(values, list):
        raise ValueError("project-image release manifest has invalid media")
    result: dict[str, tuple[str, int]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("project-image release manifest has invalid media")
        key = value.get("archive_key")
        digest = value.get("sha256")
        size = value.get("byte_size")
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(digest, str)
            or len(digest) != _SHA256_LENGTH
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or key in result
        ):
            raise ValueError("project-image release manifest has invalid media")
        result[key] = (digest, size)
    return result


def verify_release_progression(previous: dict[str, Any], candidate: dict[str, Any]) -> None:
    """Reject coverage regression or mutation of already released media."""
    previous_contracts = _count(previous, "contract_count")
    candidate_contracts = _count(candidate, "contract_count")
    previous_verified = _count(previous, "verified_image_count")
    candidate_verified = _count(candidate, "verified_image_count")
    if candidate_contracts < previous_contracts:
        raise ValueError("project-image contract coverage cannot regress")
    if candidate_verified < previous_verified:
        raise ValueError("verified project-image coverage cannot regress")
    previous_media = _media(previous)
    candidate_media = _media(candidate)
    for key, identity in previous_media.items():
        if candidate_media.get(key) != identity:
            raise ValueError("previously released immutable media changed or disappeared")


def _release(
    summary: ImageCoverageSummary,
    manifest: dict[str, Any],
    source_sha256: str,
    released_at: datetime,
) -> CoverageRelease:
    if released_at.tzinfo is None or len(source_sha256) != _SHA256_LENGTH:
        raise ValueError("coverage release identity is invalid")
    counts = summary.status_counts
    exact = counts.get("verified_exact", 0)
    no_images = counts.get("no_images", 0)
    conflicts = counts.get("count_conflict", 0)
    retries = counts.get("retry", 0)
    blocked = counts.get("blocked", 0)
    pending = counts.get("pending", 0) + counts.get("in_progress", 0)
    released_at_text = released_at.isoformat()
    completed = exact + no_images + conflicts
    verified_images = _count(manifest, "verified_image_count")
    quarantined_images = _count(manifest, "quarantined_image_count")
    payload = {
        "released_at": released_at_text,
        "source_sha256": source_sha256,
        "universe_contracts": summary.total_tasks,
        "completed_contracts": completed,
        "verified_exact_contracts": exact,
        "no_image_contracts": no_images,
        "conflict_contracts": conflicts,
        "retry_contracts": retries,
        "blocked_contracts": blocked,
        "pending_contracts": pending,
        "verified_images": verified_images,
        "quarantined_images": quarantined_images,
        "base_sql_sha256": manifest.get("sql_sha256"),
    }
    identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CoverageRelease(
        release_id=identity,
        released_at=released_at_text,
        source_sha256=source_sha256,
        universe_contracts=summary.total_tasks,
        completed_contracts=completed,
        verified_exact_contracts=exact,
        no_image_contracts=no_images,
        conflict_contracts=conflicts,
        retry_contracts=retries,
        blocked_contracts=blocked,
        pending_contracts=pending,
        verified_images=verified_images,
        quarantined_images=quarantined_images,
    )


def _sql(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"'{value.replace("'", "''")}'"


def _release_statement(release: CoverageRelease) -> str:
    values = tuple(asdict(release).values())
    return f"INSERT OR IGNORE INTO coverage_releases VALUES ({', '.join(_sql(value) for value in values)});"  # noqa: S608


def _verify_final_sql(sql: str, release_id: str) -> None:
    database = sqlite3.connect(":memory:")
    try:
        database.executescript(_PROJECT_IMAGE_MIGRATION.read_text(encoding="utf-8"))
        database.executescript(_COVERAGE_MIGRATION.read_text(encoding="utf-8"))
        database.executescript(sql)
        releases = database.execute(
            "SELECT COUNT(*) FROM coverage_releases WHERE release_id = ?", (release_id,)
        ).fetchone()[0]
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        database.close()
    if releases != 1 or integrity != "ok":
        raise ValueError("coverage release SQL verification failed")


def finalize_coverage_release(
    bundle_dir: Path,
    *,
    summary: ImageCoverageSummary,
    source_sha256: str,
    released_at: datetime,
    previous_manifest: dict[str, Any] | None,
) -> CoverageRelease:
    """Gate a candidate, append its public status row, and verify the final SQL."""
    manifest_path = bundle_dir / "manifest.json"
    sql_path = bundle_dir / "project-images.sql"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if previous_manifest is not None:
        verify_release_progression(previous_manifest, manifest)
    release = _release(summary, manifest, source_sha256, released_at)
    sql = sql_path.read_text(encoding="utf-8") + _release_statement(release) + "\n"
    _verify_final_sql(sql, release.release_id)
    sql_path.write_text(sql, encoding="utf-8")

    previous_keys = set(_media(previous_manifest)) if previous_manifest is not None else set()
    previous_states = previous_manifest.get("contracts", {}) if previous_manifest else {}
    states = manifest.get("contracts", {})
    publish_media = [
        item["archive_key"]
        for item in manifest["media"]
        if states.get(item["archive_key"].split("/", 2)[1], {}).get("state") == "verified_exact"
        and (
            item["archive_key"] not in previous_keys
            or previous_states.get(item["archive_key"].split("/", 2)[1], {}).get("state")
            != "verified_exact"
        )
    ]
    manifest["coverage_release"] = asdict(release)
    manifest["publish_media"] = sorted(publish_media)
    manifest["sql_sha256"] = hashlib.sha256(sql_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return release
