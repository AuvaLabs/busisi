"""Acquire, archive, validate and gate the scoped DepEd facility pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.facility_identity import FacilityRegistryRecord, link_school_title
from engine.budget_watchdog.facility_record_source import load_public_school_records
from engine.budget_watchdog.facility_registry import (
    DEPED_PPP_SOURCE_URL,
    EXPECTED_DEPED_PPP_SCHOOLS,
    SOURCE_ID,
    parse_deped_ppp_workbook,
)
from engine.budget_watchdog.facility_registry_bundle import (
    FacilityRegistrySource,
    build_facility_registry_bundle,
)
from engine.budget_watchdog.facility_release_gate import (
    FacilityReleaseGateResult,
    build_facility_review_packet,
    evaluate_facility_release,
)
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "facility-registry-deped-ppp-snapshot"
OUTPUT_DIR = DATA_ROOT / "facility-registry-d1-bundle"
ARCHIVE_DIR = DATA_ROOT / "archive"
CANONICAL_DATABASE = DATA_ROOT / "watchdog.sqlite3"
HGAB_BUNDLE_DIR = DATA_ROOT / "hgab-d1-bundle"
SOURCE_PATH = urlparse(DEPED_PPP_SOURCE_URL).path
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def acquire_facility_registry(
    retrieved_at: datetime,
    archive_dir: Path = ARCHIVE_DIR,
) -> tuple[Acquisition, str, tuple[FacilityRegistryRecord, ...]]:
    """Acquire and archive only an official workbook that passes every source control."""

    fetcher = SourceFetcher(
        default_source_registry(),
        max_response_bytes=MAX_RESPONSE_BYTES,
        max_attempts=3,
    )
    acquisition = fetcher.fetch("deped-facilities", SOURCE_PATH, retrieved_at=retrieved_at)
    digest = hashlib.sha256(acquisition.payload).hexdigest()
    records = parse_deped_ppp_workbook(
        acquisition.payload,
        acquisition.source_url,
        digest,
        expected_count=EXPECTED_DEPED_PPP_SCHOOLS,
    )
    archived = ArtifactArchive(archive_dir).store(acquisition)
    if archived.sha256 != digest:
        raise ValueError("archived DepEd facility workbook digest mismatch")
    return acquisition, digest, records


def _review_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("facility review manifest must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("facility review manifest must be an object")
    return value


def build_facility_release(
    acquisition: Acquisition,
    digest: str,
    records: tuple[FacilityRegistryRecord, ...],
    retrieved_at: datetime,
    *,
    snapshot_dir: Path = SNAPSHOT_DIR,
    output_dir: Path = OUTPUT_DIR,
    canonical_database: Path = CANONICAL_DATABASE,
    hgab_bundle_dir: Path = HGAB_BUNDLE_DIR,
    review_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Build candidate evidence and publish links only when measured review passes."""

    building = snapshot_dir.with_name(f".{snapshot_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    workbook_path = building / "deped-ppp-schools.xlsx"
    workbook_path.write_bytes(acquisition.payload)
    records_path = building / "facilities.json"
    records_path.write_text(
        json.dumps([asdict(record) for record in records], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source = FacilityRegistrySource(
        source_id=SOURCE_ID,
        publisher="Department of Education",
        dataset_name="Indicative List of Schools for PPP Project in 2026",
        source_url=acquisition.source_url,
        artifact_sha256=digest,
        acquired_at=retrieved_at.isoformat(),
        scope_note=(
            "Preliminary list of 1,095 possible PPP sites in eight announced regions. "
            "It is non-binding, subject to change, and not a national school registry."
        ),
        status="partial",
    )
    public_records = load_public_school_records(canonical_database, hgab_bundle_dir)
    links = tuple(link_school_title(record, records) for record in public_records)
    review_packet = build_facility_review_packet(public_records, records, links, digest)
    review_packet_path = building / "review-packet.json"
    review_packet_path.write_text(
        json.dumps(review_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    review = _review_manifest(review_manifest_path)
    gate: FacilityReleaseGateResult | None = (
        evaluate_facility_release(review, links, digest) if review is not None else None
    )
    result = build_facility_registry_bundle(
        records, source, output_dir, links=links, review_manifest=review
    )
    manifest = {
        "schema_version": 2,
        "source_id": SOURCE_ID,
        "source_url": acquisition.source_url,
        "source_path": workbook_path.name,
        "source_sha256": digest,
        "source_byte_size": len(acquisition.payload),
        "source_media_type": acquisition.media_type,
        "retrieved_at": retrieved_at.isoformat(),
        "facility_count": len(records),
        "records_path": records_path.name,
        "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
        "review_packet_path": review_packet_path.name,
        "review_packet_sha256": hashlib.sha256(review_packet_path.read_bytes()).hexdigest(),
        "candidate_links": review_packet["candidate_count"],
        "published_links": result.link_count,
        "release_gate": (
            {
                "passed": gate.passed,
                "manifest_sha256": gate.manifest_sha256,
                "reviewed_cases": gate.reviewed_cases,
                "precision_bps": gate.precision_bps,
                "agreement_bps": gate.agreement_bps,
                "critical_failures": gate.critical_failures,
                "reasons": list(gate.reasons),
            }
            if gate is not None
            else None
        ),
        "scope": "Indicative PPP sites in eight announced regions, not a national registry.",
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(snapshot_dir, ignore_errors=True)
    building.replace(snapshot_dir)
    release_state = (
        "ready_for_publication"
        if gate is not None and gate.passed
        else "gate_failed"
        if gate is not None
        else "awaiting_review"
    )
    return {
        "passed": True,
        "facility_count": result.facility_count,
        "school_records_examined": len(public_records),
        "candidate_links": review_packet["candidate_count"],
        "published_links": result.link_count,
        "release_state": release_state,
        "reviewed_cases": gate.reviewed_cases if gate else 0,
        "precision_bps": gate.precision_bps if gate else None,
        "agreement_bps": gate.agreement_bps if gate else None,
        "critical_failures": gate.critical_failures if gate else 0,
        "gate_reasons": list(gate.reasons) if gate else ["review manifest not available"],
        "source_sha256": digest,
        "bundle_sha256": result.manifest_sha256,
        "snapshot_dir": str(snapshot_dir),
        "output_dir": str(result.output_dir),
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-manifest", type=Path)
    return parser.parse_args()


def main() -> None:
    options = arguments()
    retrieved_at = datetime.now(UTC)
    acquisition, digest, records = acquire_facility_registry(retrieved_at)
    report = build_facility_release(
        acquisition,
        digest,
        records,
        retrieved_at,
        review_manifest_path=options.review_manifest,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
