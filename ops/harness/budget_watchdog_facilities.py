"""Acquire, archive, validate and bundle the scoped DepEd facility pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
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
from engine.budget_watchdog.facility_identity import link_school_title
from engine.budget_watchdog.facility_record_source import load_public_school_records
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


def main() -> None:
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    retrieved_at = datetime.now(UTC)
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
    archived = ArtifactArchive(ARCHIVE_DIR).store(acquisition)
    if archived.sha256 != digest:
        raise ValueError("archived DepEd facility workbook digest mismatch")
    building.mkdir(parents=True)
    workbook_path = building / "deped-ppp-schools.xlsx"
    workbook_path.write_bytes(acquisition.payload)
    records_path = building / "facilities.json"
    records_path.write_text(
        json.dumps([asdict(record) for record in records], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
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
        "scope": "Indicative PPP sites in eight announced regions, not a national registry.",
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
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
    public_records = load_public_school_records(CANONICAL_DATABASE, HGAB_BUNDLE_DIR)
    links = tuple(link_school_title(record, records) for record in public_records)
    result = build_facility_registry_bundle(records, source, OUTPUT_DIR, links=links)
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    print(json.dumps({
        "passed": True,
        "facility_count": result.facility_count,
        "school_records_examined": len(public_records),
        "published_links": result.link_count,
        "source_sha256": digest,
        "bundle_sha256": result.manifest_sha256,
        "snapshot_dir": str(SNAPSHOT_DIR),
        "output_dir": str(result.output_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
