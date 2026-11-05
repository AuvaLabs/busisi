import json
from pathlib import Path

import pytest

from engine.budget_watchdog.research_history import build_release_history


def _package(path: Path, *, story_id: str, slug: str, version: int, supersedes: dict | None) -> None:
    path.mkdir(parents=True)
    manifest = {
        "story_id": story_id,
        "slug": slug,
        "headline": "Question",
        "version": version,
        "status": "published",
        "published_at": "2026-11-05",
        "data_cutoff": "2026-11-03",
        "methodology_version": "test-v1",
        "source_artifact_sha256": "a" * 64,
        "canonical_url": f"https://busisi.org/research/{slug}/",
        "supersedes": supersedes,
        "files": [{"path": "claims.json", "sha256": "b" * 64, "bytes": 3}],
        "package_sha256": "c" * 64,
    }
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_release_history_orders_versions_and_explains_non_corrections(tmp_path: Path) -> None:
    root = tmp_path / "research"
    _package(root / "story" / "v1", story_id="story-1", slug="story", version=1, supersedes=None)
    _package(
        root / "story" / "v2",
        story_id="story-1",
        slug="story",
        version=2,
        supersedes={
            "version": 1,
            "manifest_url": "https://busisi.org/data/research/story/v1/manifest.json",
            "package_sha256": "c" * 64,
        },
    )
    notes = [
        {"story_id": "story-1", "version": 1, "change_type": "initial", "summary": "Initial release.", "affects_findings": False},
        {"story_id": "story-1", "version": 2, "change_type": "editorial_expansion", "summary": "Added consumption files.", "affects_findings": False},
    ]

    result = build_release_history(root, notes, verify_packages=False)

    assert result["release_count"] == 2
    assert result["story_count"] == 1
    assert result["correction_count"] == 0
    assert [item["version"] for item in result["releases"]] == [2, 1]
    assert result["releases"][0]["supersedes_version"] == 1


def test_release_history_rejects_missing_notes_or_broken_chain(tmp_path: Path) -> None:
    root = tmp_path / "research"
    _package(root / "story" / "v1", story_id="story-1", slug="story", version=1, supersedes=None)
    with pytest.raises(ValueError, match="release note"):
        build_release_history(root, [], verify_packages=False)

    notes = [{"story_id": "story-1", "version": 1, "change_type": "initial", "summary": "Initial.", "affects_findings": False}]
    manifest_path = root / "story" / "v1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["supersedes"] = {"version": 9, "package_sha256": "d" * 64, "manifest_url": "https://busisi.org/data/research/story/v9/manifest.json"}
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="supersedes"):
        build_release_history(root, notes, verify_packages=False)


def test_release_history_rejects_empty_and_duplicate_notes(tmp_path: Path) -> None:
    root = tmp_path / "research"
    with pytest.raises(ValueError, match="no research packages"):
        build_release_history(root, [], verify_packages=False)

    _package(root / "story" / "v1", story_id="story-1", slug="story", version=1, supersedes=None)
    note = {
        "story_id": "story-1",
        "version": 1,
        "change_type": "initial",
        "summary": "Initial.",
        "affects_findings": False,
    }
    with pytest.raises(ValueError, match="duplicate release note"):
        build_release_history(root, [note, note], verify_packages=False)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("change_type", "rewrite", "change type"),
        ("summary", "", "summary"),
        ("affects_findings", "no", "findings state"),
    ],
)
def test_release_history_rejects_malformed_notes(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    root = tmp_path / "research"
    _package(root / "story" / "v1", story_id="story-1", slug="story", version=1, supersedes=None)
    note = {
        "story_id": "story-1",
        "version": 1,
        "change_type": "initial",
        "summary": "Initial.",
        "affects_findings": False,
        field: value,
    }

    with pytest.raises(ValueError, match=message):
        build_release_history(root, [note], verify_packages=False)


def test_release_history_rejects_invalid_digest_and_noninitial_gap(tmp_path: Path) -> None:
    root = tmp_path / "research"
    package = root / "story" / "v2"
    _package(package, story_id="story-1", slug="story", version=2, supersedes=None)
    note = {
        "story_id": "story-1",
        "version": 2,
        "change_type": "data_update",
        "summary": "Updated data.",
        "affects_findings": True,
    }
    with pytest.raises(ValueError, match="non-initial"):
        build_release_history(root, [note], verify_packages=False)

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["package_sha256"] = "invalid"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="digest"):
        build_release_history(root, [note], verify_packages=False)


def test_release_history_rejects_supersedes_digest_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "research"
    _package(root / "story" / "v1", story_id="story-1", slug="story", version=1, supersedes=None)
    _package(
        root / "story" / "v2",
        story_id="story-1",
        slug="story",
        version=2,
        supersedes={"version": 1, "package_sha256": "d" * 64},
    )
    notes = [
        {"story_id": "story-1", "version": 1, "change_type": "initial", "summary": "Initial.", "affects_findings": False},
        {"story_id": "story-1", "version": 2, "change_type": "correction", "summary": "Corrected.", "affects_findings": True},
    ]

    with pytest.raises(ValueError, match="digest"):
        build_release_history(root, notes, verify_packages=False)


def test_published_release_history_matches_all_authenticated_packages() -> None:
    root = Path(__file__).resolve().parents[3]
    public_root = root / "cloudflare" / "busisi" / "public" / "data" / "research"
    notes = json.loads(
        (root / "ops" / "harness" / "fixtures" / "research_release_notes.json").read_text()
    )
    observed = json.loads((public_root / "release-history.json").read_text())

    assert observed == build_release_history(public_root, notes)
    assert observed["release_count"] == 8
    assert observed["story_count"] == 3
    assert observed["correction_count"] == 0
