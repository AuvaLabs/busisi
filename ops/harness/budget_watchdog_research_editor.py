"""Validate public research and optionally publish complete private editor drafts."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from engine.budget_watchdog.research_editor import (
    validate_research_release,
    verify_published_package,
    write_research_release,
)

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT / "cloudflare" / "busisi" / "public" / "data" / "research"
PRIVATE_ROOT = ROOT / "data" / "budget_watchdog" / "research-editor"


def validate_public_packages(public_root: Path) -> list[dict[str, Any]]:
    packages = []
    for manifest_path in sorted(public_root.glob("*/v*/manifest.json")):
        manifest = verify_published_package(manifest_path.parent)
        packages.append(
            {
                "story_id": manifest["story_id"],
                "version": manifest["version"],
                "package_sha256": manifest["package_sha256"],
                "path": str(manifest_path.parent.relative_to(public_root)),
            }
        )
    if not packages:
        raise ValueError("no published research packages were found")
    return packages


def audit_private_drafts(draft_root: Path) -> dict[str, Any]:
    results = []
    for path in sorted((draft_root / "drafts").glob("*.json")):
        try:
            release = json.loads(path.read_text(encoding="utf-8"))
            validate_research_release(release)
            results.append({"path": str(path), "status": "ready", "release": release})
        except Exception as exc:
            results.append({"path": str(path), "status": "quarantined", "error": str(exc)})
    return {
        "drafts": len(results),
        "ready": sum(item["status"] == "ready" for item in results),
        "quarantined": sum(item["status"] == "quarantined" for item in results),
        "items": results,
    }


def publish_ready_drafts(
    audit: dict[str, Any], public_root: Path
) -> list[dict[str, Any]]:
    published = []
    for item in audit["items"]:
        if item["status"] != "ready":
            continue
        release = item["release"]
        metadata = release["metadata"]
        target = public_root / metadata["slug"] / f"v{metadata['version']}"
        if target.exists():
            raise FileExistsError(f"immutable research package already exists: {target}")
        building = target.with_name(f".{target.name}.building")
        shutil.rmtree(building, ignore_errors=True)
        manifest = write_research_release(release, building)
        target.parent.mkdir(parents=True, exist_ok=True)
        building.replace(target)
        published.append(
            {
                "story_id": manifest["story_id"],
                "version": manifest["version"],
                "package_sha256": manifest["package_sha256"],
            }
        )
    return published


def _safe_report(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: audit[key] for key in ("drafts", "ready", "quarantined")},
        "items": [
            {key: value for key, value in item.items() if key != "release"}
            for item in audit["items"]
        ],
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-root", type=Path, default=PUBLIC_ROOT)
    parser.add_argument("--private-root", type=Path, default=PRIVATE_ROOT)
    parser.add_argument("--publish-ready", action="store_true")
    return parser.parse_args()


def main() -> None:
    options = arguments()
    packages = validate_public_packages(options.public_root)
    audit = audit_private_drafts(options.private_root)
    published = (
        publish_ready_drafts(audit, options.public_root)
        if options.publish_ready
        else []
    )
    report = {
        "passed": audit["quarantined"] == 0,
        "published_packages": packages,
        "private_editor": _safe_report(audit),
        "newly_published": published,
    }
    options.private_root.mkdir(parents=True, exist_ok=True)
    (options.private_root / "latest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if audit["quarantined"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
