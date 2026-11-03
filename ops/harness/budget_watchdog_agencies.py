"""Acquire, archive, extract and reconcile the FY2027 appropriation-head ledger."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.agency_budget_bundle import build_agency_budget_bundle
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "agency-2027-snapshot"
ARCHIVE_DIR = DATA_ROOT / "archive"
OUTPUT_DIR = DATA_ROOT / "agency-d1-bundle"
SOURCE_COMMIT = "a0caa778442cdae5583f5a006ea7401dab00e5ac"
HOUSE_CONTROL_PESOS = 4_606_066_495_000
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
PDFTOTEXT = "/usr/bin/pdftotext"

HOUSE_DOCUMENTS = (
    {
        "key": "house-ia",
        "filename": "hb10858-3r-vol-ia.pdf",
        "path": (
            f"/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/{SOURCE_COMMIT}/"
            "HB_BUDGET_3rd_reading/1-%20HB%2010858%20FOR%203RD%20READING%20VOL%20I-A.pdf"
        ),
        "sha256": "79f56b8d577246342b59cc996afdd707523268f0bde10378e3c1b5ef844451fd",
    },
    {
        "key": "house-ib",
        "filename": "hb10858-3r-vol-ib.pdf",
        "path": (
            f"/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/{SOURCE_COMMIT}/"
            "HB_BUDGET_3rd_reading/2-%20HB%2010858%20FOR%203RD%20READING%20VOL%20I-B.pdf"
        ),
        "sha256": "4cc0f17e472d1af380ea6d3972561f6bb241137826fd85ed7e7e70bcd92986b9",
    },
)


def _store(fetcher, archive, source_id: str, path: str, output: Path):
    acquisition = fetcher.fetch(source_id, path, retrieved_at=datetime.now(UTC))
    archived = archive.store(acquisition)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(acquisition.payload)
    return acquisition, archived


def _extract_text(pdf_path: Path, text_path: Path) -> None:
    try:
        subprocess.run(  # noqa: S603 - fixed executable and locally controlled paths
            [PDFTOTEXT, "-layout", str(pdf_path), str(text_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("pdftotext failed for a House source volume") from exc
    if not text_path.is_file() or not text_path.read_bytes():
        raise RuntimeError("pdftotext produced an empty House source document")


def _acquire_json(fetcher, archive, building: Path) -> list[dict]:
    records = []
    for key, path in (
        ("nep-overview", "/api/v1/nep/2027"),
        ("nep-departments", "/api/v1/nep/2027/departments"),
        ("nep-congress", "/api/v1/nep/2027/departments/01"),
    ):
        output = building / f"{key}.json"
        acquisition, archived = _store(fetcher, archive, "bettergov-budget", path, output)
        json.loads(acquisition.payload)
        records.append(
            {
                "key": key,
                "path": output.name,
                "sha256": archived.sha256,
                "source_url": acquisition.source_url,
            }
        )
    return records


def _acquire_house(fetcher, archive, building: Path) -> list[dict]:
    records = []
    for document in HOUSE_DOCUMENTS:
        pdf_path = building / "documents" / document["filename"]
        acquisition, archived = _store(
            fetcher,
            archive,
            "bettergov-analysis-github",
            document["path"],
            pdf_path,
        )
        if archived.sha256 != document["sha256"]:
            raise ValueError(f"House PDF digest mismatch: {document['key']}")
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
                "source_commit": SOURCE_COMMIT,
            }
        )
    return records


def main() -> None:
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=MAX_RESPONSE_BYTES)
    archive = ArtifactArchive(ARCHIVE_DIR)
    documents = _acquire_json(fetcher, archive, building)
    documents.extend(_acquire_house(fetcher, archive, building))
    manifest = {
        "fiscal_year": 2027,
        "baseline_year": 2026,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "house_control_pesos": HOUSE_CONTROL_PESOS,
        "source_commit": SOURCE_COMMIT,
        "text_extractor": subprocess.run(  # noqa: S603 - fixed executable
            [PDFTOTEXT, "-v"], capture_output=True, text=True, check=True
        ).stderr.splitlines()[0],
        "documents": documents,
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    result = build_agency_budget_bundle(SNAPSHOT_DIR, OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "record_count": result.record_count,
                "compared_records": result.compared_records,
                "unavailable_records": result.unavailable_records,
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
