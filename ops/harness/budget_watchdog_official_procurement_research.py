"""Build research release v6 from the reviewed official-procurement sprint."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from engine.budget_watchdog.research_official_procurement import (
    build_official_procurement_release,
)
from engine.budget_watchdog.research_package import write_release_package

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = (
    ROOT / "cloudflare" / "busisi" / "public" / "data" / "research" / "multipurpose-buildings"
)
V5 = PUBLIC_ROOT / "v5"
OUTPUT_DIR = PUBLIC_ROOT / "v6"
ACQUISITION = ROOT / "data" / "budget_watchdog" / "public-value-acquisition" / "snapshot.json"
OFFICIAL_REVIEW = (
    ROOT / "data" / "budget_watchdog" / "official-procurement-evidence" / "review.json"
)
V5_SHA256 = "5847526c3954802791e0d79075e31eceb14a477c9d2a5264dcff9301bfe33926"


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_release() -> dict:
    mapping = {
        "metadata": "manifest.json",
        "claims": "claims.json",
        "findings": "findings.json",
        "investigations": "investigations.json",
        "chart_data": "chart-data.json",
        "project_examples": "project-examples.json",
        "sources": "sources.json",
        "limitations": "limitations.json",
        "story": "story.json",
        "editorial_package": "editorial-package.json",
    }
    return {field: _read(V5 / filename) for field, filename in mapping.items()}


def main() -> int:
    if not ACQUISITION.is_file() or not OFFICIAL_REVIEW.is_file():
        raise FileNotFoundError(
            "official review and public-value acquisition snapshot are required"
        )
    base = _base_release()
    if base["metadata"].get("package_sha256") != V5_SHA256:
        raise ValueError("v5 package identity changed")
    release = build_official_procurement_release(
        base,
        _read(ACQUISITION),
        _read(OFFICIAL_REVIEW),
        supersedes={
            "version": 5,
            "manifest_url": (
                "https://busisi.org/data/research/multipurpose-buildings/v5/manifest.json"
            ),
            "package_sha256": V5_SHA256,
        },
    )
    building = OUTPUT_DIR.with_name(f".{OUTPUT_DIR.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    manifest = write_release_package(release, building)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    building.replace(OUTPUT_DIR)
    print(
        json.dumps(
            {
                "passed": True,
                "version": manifest["version"],
                "package_sha256": manifest["package_sha256"],
                "official_summary": release["chart_data"]["official_procurement_evidence"][
                    "summary"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
