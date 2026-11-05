"""Build the published Busisi research package from an immutable DPWH snapshot."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
from engine.budget_watchdog.research_multipurpose_value import (
    build_multipurpose_value_release,
)
from engine.budget_watchdog.research_package import write_release_package

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123"
SOURCE_PATH = ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / SOURCE_SHA256
TECHNICAL_NOTES_SHA256 = "79a81214664157b9721a902151240d603e10ac94bc1652d13814b88816083bd6"
CLASSROOM_RELEASE_SHA256 = "6ef90a400adb64211bb4a16b3277242dc9c6615f5e432d5c37302fa3117817d1"
BENCHMARK_SOURCE_PATHS = (
    ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / TECHNICAL_NOTES_SHA256,
    ROOT / "data" / "budget_watchdog" / "archive" / "blobs" / CLASSROOM_RELEASE_SHA256,
)
OUTPUT_DIR = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v3"
)
SOURCE_MODIFIED = "2026-01-22"
PUBLISHED_AT = "2026-11-05"
EXPECTED_CLAIMS = {
    "mpb-total-records": 12_609,
    "mpb-ongoing": 5_842,
    "mpb-active-pipeline": 7_024,
    "mpb-completed": 5_582,
    "mpb-positive-active-budget": 6_093,
    "mpb-existing-work-wording": 2_812,
    "mpb-prior-coordinate-candidates": 31,
    "mpb-active-budget": 8_878_625_428_536,
    "mpb-all-recorded-budget": 12_977_915_530_776,
    "mpb-completed-budget": 4_099_290_102_240,
    "mpb-classroom-equivalent-low": 25_499,
    "mpb-classroom-equivalent-high": 32_503,
    "mpb-necessity-assessment": 0,
}

BENCHMARK_SOURCES = [
    {
        "id": "dbm-technical-notes-2026",
        "publisher": "Department of Budget and Management",
        "access_provider": "Department of Budget and Management",
        "source_kind": "official_record",
        "scope": "Technical notes on the 2026 proposed national budget",
        "modified": "2025-08-13",
        "retrieved_at": "2026-11-05",
        "origin_url": "https://www.dbm.gov.ph/",
        "source_url": "https://www.dbm.gov.ph/images/pdffiles/2026-Technical-Notes.pdf",
        "sha256": TECHNICAL_NOTES_SHA256,
    },
    {
        "id": "dbm-classroom-release-2026",
        "publisher": "Department of Budget and Management",
        "access_provider": "Department of Budget and Management",
        "source_kind": "official_record",
        "scope": "April 2026 release for 4,960 classrooms and essential furniture",
        "modified": "2026-04-20",
        "retrieved_at": "2026-11-05",
        "origin_url": "https://www.dbm.gov.ph/",
        "source_url": (
            "https://www.dbm.gov.ph/index.php/homepage-2/"
            "3953-pbbm-orders-p17-27b-release-to-build-4-960-classrooms-"
            "nationwide-close-learning-gaps"
        ),
        "sha256": CLASSROOM_RELEASE_SHA256,
    },
]

CLASSROOM_BENCHMARKS = [
    {
        "id": "dbm-proposed-new-classrooms-2026",
        "label": "2026 proposed budget technical-note target",
        "budget_centavos": 1_330_000_000_000,
        "physical_target": 4_869,
        "unit": "new classrooms",
        "source_id": "dbm-technical-notes-2026",
    },
    {
        "id": "dbm-released-new-classrooms-2026",
        "label": "April 2026 classroom and furniture release",
        "budget_centavos": 1_727_000_000_000,
        "physical_target": 4_960,
        "unit": "new classrooms",
        "source_id": "dbm-classroom-release-2026",
    },
    {
        "id": "dbm-proposed-classroom-repairs-2026",
        "label": "2026 proposed classroom repair and rehabilitation target",
        "budget_centavos": 610_000_000_000,
        "physical_target": 9_440,
        "unit": "classroom repairs or rehabilitations",
        "source_id": "dbm-technical-notes-2026",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f"archived DPWH source is unavailable: {SOURCE_PATH}")
    if _sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise ValueError("archived DPWH source digest does not match the registered identity")
    for path in BENCHMARK_SOURCE_PATHS:
        if not path.is_file() or _sha256(path) != path.name:
            raise ValueError(f"archived benchmark source is unavailable or invalid: {path.name}")

    columns = [
        "contractId",
        "description",
        "status",
        "budget",
        "infraYear",
        "location",
        "latitude",
        "longitude",
        "hasSatelliteImage",
    ]
    rows = pq.read_table(SOURCE_PATH, columns=columns).to_pylist()
    release = build_multipurpose_value_release(
        rows,
        source_sha256=SOURCE_SHA256,
        source_modified=SOURCE_MODIFIED,
        published_at=PUBLISHED_AT,
        benchmark_sources=BENCHMARK_SOURCES,
        classroom_benchmarks=CLASSROOM_BENCHMARKS,
        supersedes={
            "version": 2,
            "manifest_url": (
                "https://busisi.org/data/research/multipurpose-buildings/v2/manifest.json"
            ),
            "package_sha256": ("bdf6fd74d6fc4a53a9c8025cc5e3214b31e61a4f84911020701a3f2709eadec1"),
        },
    )
    claims = {claim["id"]: claim["value"] for claim in release["claims"]}
    observed = {key: claims.get(key) for key in EXPECTED_CLAIMS}
    if observed != EXPECTED_CLAIMS:
        raise ValueError(f"research control totals changed: {observed!r}")

    building = OUTPUT_DIR.with_name(f".{OUTPUT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    manifest = write_release_package(release, building)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    building.replace(OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "story_id": manifest["story_id"],
                "version": manifest["version"],
                "package_sha256": manifest["package_sha256"],
                "claims": observed,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
