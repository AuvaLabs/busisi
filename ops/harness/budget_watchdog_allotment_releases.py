"""Acquire, archive and publish the official FY2026 DBM allotment-release ledger."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.allotment_release_bundle import build_allotment_release_bundle
from engine.budget_watchdog.allotment_releases import AS_OF_DATE, FISCAL_YEAR, extract_xlsx_rows
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "allotment-release-2026-snapshot"
OUTPUT_DIR = DATA_ROOT / "allotment-release-d1-bundle"
ARCHIVE_DIR = DATA_ROOT / "archive"
SOURCE_PATH = (
    "/wp-content/uploads/e-Fund_Releases/Status-of-Allotment-Releases/"
    "2026/September/FY-2026-as-of-September-30-Website.xlsx"
)
EXPECTED_SHA256 = "05a902418e0a78339b82d71def04447eab44897b752d001343121bcbe6226aae"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def main() -> None:
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    retrieved_at = datetime.now(UTC)
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=MAX_RESPONSE_BYTES)
    acquisition = fetcher.fetch("dbm-saaodb", SOURCE_PATH, retrieved_at=retrieved_at)
    digest = hashlib.sha256(acquisition.payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("official allotment-release workbook digest changed")
    archived = ArtifactArchive(ARCHIVE_DIR).store(acquisition)
    if archived.sha256 != digest:
        raise ValueError("archived allotment-release workbook digest mismatch")
    workbook_path = building / "fy2026-as-of-september-30.xlsx"
    workbook_path.write_bytes(acquisition.payload)
    rows = extract_xlsx_rows(acquisition.payload, "By Dept")
    rows_path = building / "by-department.json"
    rows_path.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
    manifest = {
        "fiscal_year": FISCAL_YEAR,
        "as_of_date": AS_OF_DATE,
        "retrieved_at": retrieved_at.isoformat(),
        "source_url": acquisition.source_url,
        "source_path": workbook_path.name,
        "source_sha256": digest,
        "source_byte_size": len(acquisition.payload),
        "source_media_type": acquisition.media_type,
        "rows_path": rows_path.name,
        "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "worksheet": "By Dept",
        "source_unit": "thousand_pesos",
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    result = build_allotment_release_bundle(SNAPSHOT_DIR, OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "record_count": result.record_count,
                "department_count": result.department_count,
                "attached_count": result.attached_count,
                "source_sha256": digest,
                "manifest_sha256": result.manifest_sha256,
                "output_dir": str(result.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
