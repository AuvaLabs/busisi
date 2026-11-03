"""Acquire and verify official DBM evidence for the FY2027 public-value desk."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.public_value_bundle import build_public_value_bundle
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "public-value-2027-snapshot"
OUTPUT_DIR = DATA_ROOT / "public-value-d1-bundle"
ARCHIVE_DIR = DATA_ROOT / "archive"
PDFTOTEXT = "/usr/bin/pdftotext"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

DOCUMENTS = (
    {
        "key": "besf-a1",
        "path": "/wp-content/uploads/BESF/BESF2027/A1.pdf",
        "filename": "dbm-besf-2027-a1.pdf",
        "source_page": 1,
        "sha256": "9ba6e7cd41831474069d98ba6f396b3e072d883c6494c190f1afd4783fec388c",
    },
    {
        "key": "besf-a2",
        "path": "/wp-content/uploads/BESF/BESF2027/A2.pdf",
        "filename": "dbm-besf-2027-a2.pdf",
        "source_page": 2,
        "sha256": "20972f2651e080d828ee03eccaae06afab04287d2299e13883f36a53a86a9170",
    },
)


def _extract_text(pdf_path: Path, text_path: Path) -> None:
    try:
        subprocess.run(  # noqa: S603 - fixed executable and controlled paths
            [PDFTOTEXT, "-layout", str(pdf_path), str(text_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("pdftotext failed for a DBM BESF source") from exc
    if not text_path.is_file() or not text_path.read_bytes():
        raise RuntimeError("pdftotext produced an empty DBM BESF source")


def main() -> None:
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    (building / "documents").mkdir(parents=True)
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=MAX_RESPONSE_BYTES)
    archive = ArtifactArchive(ARCHIVE_DIR)
    records = []
    for document in DOCUMENTS:
        acquisition = fetcher.fetch("dbm-nep", document["path"], retrieved_at=datetime.now(UTC))
        archived = archive.store(acquisition)
        if archived.sha256 != document["sha256"]:
            raise ValueError(f"DBM BESF PDF digest mismatch: {document['key']}")
        pdf_path = building / "documents" / document["filename"]
        pdf_path.write_bytes(acquisition.payload)
        text_path = building / f"{document['key']}.txt"
        _extract_text(pdf_path, text_path)
        records.append(
            {
                "key": document["key"],
                "path": text_path.name,
                "sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
                "pdf_path": str(pdf_path.relative_to(building)),
                "pdf_sha256": archived.sha256,
                "source_url": acquisition.source_url,
                "source_page": document["source_page"],
            }
        )
    manifest = {
        "fiscal_year": 2027,
        "baseline_year": 2026,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "text_extractor": subprocess.run(  # noqa: S603 - fixed executable
            [PDFTOTEXT, "-v"], capture_output=True, text=True, check=True
        ).stderr.splitlines()[0],
        "documents": records,
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    result = build_public_value_bundle(SNAPSHOT_DIR, OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "indicator_count": result.indicator_count,
                "improving_count": result.improving_count,
                "pressure_count": result.pressure_count,
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
