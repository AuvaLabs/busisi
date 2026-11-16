"""Acquire, archive, reconcile and package official PSA community context."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.community_needs import (
    build_population_snapshot,
    openstat_national_population_query,
    openstat_population_query,
    parse_national_population_control,
    parse_population_table,
)
from engine.budget_watchdog.community_needs_bundle import build_community_needs_bundle
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "budget_watchdog"
SNAPSHOT_DIR = DATA_ROOT / "community-needs-snapshot"
ARCHIVE_DIR = DATA_ROOT / "archive"
OUTPUT_DIR = DATA_ROOT / "community-needs-d1-bundle"
API_ROOT = "/PXWeb/api/v1/en/DB/1A/PO_2024"
NATIONAL_TABLE = "0191A6DTHP8.px"
REGIONAL_TABLES = (
    "0011A6DTPH0.px",
    "0021A6DTPH1.px",
    "0031A6DTPH2.px",
    "0041A6DTPH3.px",
    "0051A6DTPH4.px",
    "0061A6DTPH5.px",
    "0071A6DTPH6.px",
    "0081A6DTPH7.px",
    "0091A6DTPH8.px",
    "0101A6DTPH9.px",
    "0111A6DTHP0.px",
    "0121A6DTHP1.px",
    "0131A6DTHP2.px",
    "0141A6DTHP3.px",
    "0151A6DTHP4.px",
    "0161A6DTHP5.px",
    "0171A6DTHP6.px",
    "0181A6DTHP7.px",
)


def _acquire(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    building: Path,
    table: str,
    query: dict[str, object],
    retrieved_at: datetime,
):
    acquisition = fetcher.post_json(
        "psa-openstat",
        f"{API_ROOT}/{table}",
        query,
        retrieved_at=retrieved_at,
    )
    archived = archive.store(acquisition)
    output = building / "responses" / f"{table}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(acquisition.payload)
    query_bytes = json.dumps(query, separators=(",", ":"), sort_keys=True).encode()
    return (
        acquisition,
        archived,
        {
            "table": table,
            "path": str(output.relative_to(building)),
            "source_url": acquisition.source_url,
            "sha256": archived.sha256,
            "query_sha256": hashlib.sha256(query_bytes).hexdigest(),
        },
    )


def main() -> None:
    retrieved_at = datetime.now(UTC)
    building = SNAPSHOT_DIR.with_name(f".{SNAPSHOT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    fetcher = SourceFetcher(
        default_source_registry(), max_response_bytes=16 * 1024 * 1024, max_attempts=3
    )
    archive = ArtifactArchive(ARCHIVE_DIR)
    documents = []
    tables = []
    query = openstat_population_query()
    for table_name in REGIONAL_TABLES:
        acquisition, archived, document = _acquire(
            fetcher, archive, building, table_name, query, retrieved_at
        )
        tables.append(
            parse_population_table(
                acquisition.payload,
                source_sha256=archived.sha256,
                source_url=acquisition.source_url,
            )
        )
        documents.append(document)
    control_acquisition, control_archive, control_document = _acquire(
        fetcher,
        archive,
        building,
        NATIONAL_TABLE,
        openstat_national_population_query(),
        retrieved_at,
    )
    control = parse_national_population_control(
        control_acquisition.payload,
        source_sha256=control_archive.sha256,
        source_url=control_acquisition.source_url,
    )
    documents.append(control_document)
    snapshot = build_population_snapshot(
        tuple(tables),
        national_population=control.total_population,
        national_household_population=control.household_population,
        national_households=control.households,
        national_source_sha256=control.source_sha256,
    )
    manifest = {
        "barangay_count": snapshot.barangay_count,
        "census_date": "2024-07-01",
        "documents": documents,
        "excluded_out_of_region": snapshot.excluded_out_of_region,
        "hierarchy_gap_count": len(snapshot.hierarchy_gaps),
        "national_household_population": snapshot.national_household_population,
        "national_households": snapshot.national_households,
        "national_population": snapshot.national_population,
        "national_unallocated_household_population": (
            snapshot.national_unallocated_household_population
        ),
        "national_unallocated_households": snapshot.national_unallocated_households,
        "national_unallocated_population": snapshot.national_unallocated_population,
        "place_count": snapshot.place_count,
        "region_count": snapshot.region_count,
        "retrieved_at": retrieved_at.isoformat(),
        "snapshot_sha256": snapshot.snapshot_sha256,
    }
    (building / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)
    building.replace(SNAPSHOT_DIR)
    result = build_community_needs_bundle(snapshot, OUTPUT_DIR, checked_at=retrieved_at.isoformat())
    print(
        json.dumps(
            {
                "passed": True,
                "place_count": result.place_count,
                "region_count": result.region_count,
                "barangay_count": result.barangay_count,
                "national_population": snapshot.national_population,
                "national_unallocated_population": snapshot.national_unallocated_population,
                "excluded_out_of_region": snapshot.excluded_out_of_region,
                "hierarchy_gap_count": len(snapshot.hierarchy_gaps),
                "sql_chunks": result.sql_chunks,
                "manifest_sha256": result.manifest_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
