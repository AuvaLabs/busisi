"""Acquire, archive, reconcile and build the FY2027 NEP-to-House ledger."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.hgab_bundle import build_hgab_bundle
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "hgab-2027-snapshot"
ARCHIVE_DIR = DATA_ROOT / "archive"
OUTPUT_DIR = DATA_ROOT / "hgab-d1-bundle"
DATASETS = ("dpwh", "fmr", "hfep", "nia")
PAGE_SIZE = 200
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024


def _store_payload(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    source_id: str,
    path: str,
    output_path: Path,
    *,
    params: dict[str, str | int] | None = None,
):
    acquisition = fetcher.fetch(source_id, path, params=params, retrieved_at=datetime.now(UTC))
    archived = archive.store(acquisition)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(acquisition.payload)
    return acquisition, archived


def _archive_documents(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    documents: list[dict],
    snapshot_dir: Path,
) -> list[dict]:
    archived_documents = []
    for document in documents:
        parsed = urlparse(document["pdf_url"])
        acquisition, archived = _store_payload(
            fetcher,
            archive,
            "bettergov-budget-assets",
            parsed.path,
            snapshot_dir / "documents" / f"{document['key']}.pdf",
        )
        if archived.sha256 != document["sha256"]:
            raise ValueError(f"document digest mismatch: {document['key']}")
        archived_documents.append(
            {
                "key": document["key"],
                "sha256": archived.sha256,
                "byte_size": archived.byte_size,
                "source_url": document.get("source_url"),
                "mirror_url": acquisition.source_url,
            }
        )
    return archived_documents


def _archive_pages(
    fetcher: SourceFetcher, archive: ArtifactArchive, building: Path
) -> list[dict]:
    pages = []
    for dataset in DATASETS:
        offset = 0
        while True:
            relative = Path("pages") / f"{dataset}-{offset:06d}.json"
            acquisition, archived = _store_payload(
                fetcher,
                archive,
                "bettergov-budget",
                f"/api/v1/hgab/2027/datasets/{dataset}/projects",
                building / relative,
                params={"limit": PAGE_SIZE, "offset": offset},
            )
            payload = json.loads(acquisition.payload)
            pages.append(
                {
                    "dataset": dataset,
                    "offset": offset,
                    "path": str(relative),
                    "sha256": archived.sha256,
                    "record_count": len(payload["data"]["rows"]),
                }
            )
            next_offset = payload["data"]["next_offset"]
            if next_offset is None:
                break
            offset = int(next_offset)
    return pages


def _write_manifest(
    building: Path, overview_archive, overview: dict, pages: list[dict], documents: list[dict]
) -> None:
    manifest = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "overview_sha256": overview_archive.sha256,
        "source_commit": overview["meta"]["source_commit"],
        "pages": pages,
        "documents": documents,
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _result_payload(result) -> dict:
    return {
        "passed": True,
        "output_dir": str(result.output_dir),
        "record_count": result.record_count,
        "quarantine_count": result.quarantine_count,
        "sql_chunks": result.sql_chunks,
        "source_commit": result.source_commit,
        "manifest_sha256": result.manifest_sha256,
    }


def main() -> None:
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    fetcher = SourceFetcher(default_source_registry(), max_response_bytes=MAX_DOCUMENT_BYTES)
    archive = ArtifactArchive(ARCHIVE_DIR)
    overview_acquisition, overview_archive = _store_payload(
        fetcher,
        archive,
        "bettergov-budget",
        "/api/v1/hgab/2027",
        building / "overview.json",
    )
    overview = json.loads(overview_acquisition.payload)
    pages = _archive_pages(fetcher, archive, building)
    documents = _archive_documents(fetcher, archive, overview["data"]["documents"], building)
    _write_manifest(building, overview_archive, overview, pages, documents)
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    result = build_hgab_bundle(SNAPSHOT_DIR, OUTPUT_DIR)
    print(json.dumps(_result_payload(result), indent=2))


if __name__ == "__main__":
    main()
