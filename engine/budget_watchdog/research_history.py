"""Build the public, evidence-checked research release history."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.budget_watchdog.research_editor import verify_published_package

CHANGE_TYPES = frozenset({"initial", "editorial_expansion", "correction", "data_update"})
SHA256 = re.compile(r"[a-f0-9]{64}")


def _load_manifests(public_root: Path, *, verify_packages: bool) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in sorted(public_root.glob("*/v*/manifest.json")):
        manifest = (
            verify_published_package(path.parent)
            if verify_packages
            else json.loads(path.read_text(encoding="utf-8"))
        )
        if not isinstance(manifest, dict):
            raise ValueError("research package manifest must be an object")
        manifests.append(manifest)
    if not manifests:
        raise ValueError("release history has no research packages")
    return manifests


def _note_index(notes: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for note in notes:
        story_id = note.get("story_id")
        version = note.get("version")
        if (
            not isinstance(story_id, str)
            or not story_id.strip()
            or not isinstance(version, int)
            or isinstance(version, bool)
        ):
            raise ValueError("release note identity is invalid")
        key = (story_id, version)
        if key in indexed:
            raise ValueError(f"duplicate release note: {key}")
        if note.get("change_type") not in CHANGE_TYPES:
            raise ValueError(f"release note has unsupported change type: {key}")
        if not isinstance(note.get("summary"), str) or not note["summary"].strip():
            raise ValueError(f"release note summary is missing: {key}")
        if not isinstance(note.get("affects_findings"), bool):
            raise ValueError(f"release note findings state is invalid: {key}")
        indexed[key] = note
    return indexed


def _validate_supersedes(
    manifest: dict[str, Any], manifests: dict[tuple[str, int], dict[str, Any]]
) -> int | None:
    supersedes = manifest.get("supersedes")
    if supersedes is None:
        if manifest["version"] != 1:
            raise ValueError("non-initial release must identify the version it supersedes")
        return None
    prior_version = supersedes.get("version")
    if not isinstance(prior_version, int) or isinstance(prior_version, bool):
        raise ValueError("release supersedes version is invalid")
    prior = manifests.get((manifest["story_id"], prior_version))
    if prior is None or prior_version != manifest["version"] - 1:
        raise ValueError("release supersedes chain is missing or non-sequential")
    if supersedes.get("package_sha256") != prior.get("package_sha256"):
        raise ValueError("release supersedes digest does not match the prior package")
    return prior_version


def build_release_history(
    public_root: Path,
    notes: list[dict[str, Any]],
    *,
    verify_packages: bool = True,
) -> dict[str, Any]:
    """Combine authenticated manifests with explicit human-readable release notes."""

    values = _load_manifests(public_root, verify_packages=verify_packages)
    manifests = {(item["story_id"], item["version"]): item for item in values}
    if len(manifests) != len(values):
        raise ValueError("release history contains duplicate story versions")
    note_by_release = _note_index(notes)
    if set(note_by_release) != set(manifests):
        raise ValueError("every package must have exactly one release note")
    releases = []
    for key, manifest in manifests.items():
        digest = manifest.get("package_sha256")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise ValueError(f"release package digest is invalid: {key}")
        note = note_by_release[key]
        releases.append(
            {
                "story_id": manifest["story_id"],
                "slug": manifest["slug"],
                "headline": manifest["headline"],
                "version": manifest["version"],
                "published_at": manifest["published_at"],
                "data_cutoff": manifest["data_cutoff"],
                "canonical_url": manifest["canonical_url"],
                "manifest_url": (
                    f"https://busisi.org/data/research/{manifest['slug']}"
                    f"/v{manifest['version']}/manifest.json"
                ),
                "package_sha256": digest,
                "supersedes_version": _validate_supersedes(manifest, manifests),
                "change_type": note["change_type"],
                "summary": note["summary"],
                "affects_findings": note["affects_findings"],
            }
        )
    releases.sort(
        key=lambda item: (item["published_at"], item["story_id"], item["version"]),
        reverse=True,
    )
    return {
        "schema_version": "1.0",
        "release_count": len(releases),
        "story_count": len({item["story_id"] for item in releases}),
        "correction_count": sum(item["change_type"] == "correction" for item in releases),
        "releases": releases,
        "policy": (
            "A correction changes an error or supported conclusion. Editorial expansions and "
            "data updates are labelled separately. Older immutable packages remain available."
        ),
    }
