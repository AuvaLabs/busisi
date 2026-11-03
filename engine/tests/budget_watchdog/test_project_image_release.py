from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.budget_watchdog.project_image_bundle import build_project_image_bundle
from engine.budget_watchdog.project_image_queue import ImageCoverageSummary
from engine.budget_watchdog.project_image_release import (
    finalize_coverage_release,
    verify_release_progression,
)
from engine.budget_watchdog.project_images import ProjectImageCoverage


def _manifest(contracts: int, verified: int, media: list[dict[str, object]]) -> dict[str, object]:
    return {
        "contract_count": contracts,
        "verified_image_count": verified,
        "quarantined_image_count": 0,
        "media": media,
    }


def test_release_gate_accepts_monotonic_coverage() -> None:
    previous = _manifest(2, 1, [{"archive_key": "a", "sha256": "a" * 64, "byte_size": 1}])
    candidate = _manifest(
        3,
        2,
        [
            {"archive_key": "a", "sha256": "a" * 64, "byte_size": 1},
            {"archive_key": "b", "sha256": "b" * 64, "byte_size": 2},
        ],
    )
    verify_release_progression(previous, candidate)


def test_release_gate_accepts_the_legacy_keyed_media_manifest() -> None:
    previous = _manifest(1, 1, [])
    previous["media"] = {"a" * 64: {"archive_key": "a", "byte_size": 1, "width": 1, "height": 1}}
    candidate = _manifest(1, 1, [{"archive_key": "a", "sha256": "a" * 64, "byte_size": 1}])
    verify_release_progression(previous, candidate)


def test_release_gate_rejects_regression_or_changed_media() -> None:
    previous = _manifest(2, 1, [{"archive_key": "a", "sha256": "a" * 64, "byte_size": 1}])
    with pytest.raises(ValueError, match="contract coverage"):
        verify_release_progression(previous, _manifest(1, 1, []))
    changed = _manifest(2, 1, [{"archive_key": "a", "sha256": "b" * 64, "byte_size": 1}])
    with pytest.raises(ValueError, match="immutable media"):
        verify_release_progression(previous, changed)


def test_release_gate_validates_manifest_shape() -> None:
    with pytest.raises(ValueError, match="manifest"):
        verify_release_progression({}, {"contract_count": 1})


def test_finalizes_a_self_verifying_public_coverage_release(tmp_path: Path) -> None:
    coverage = ProjectImageCoverage(
        contract_id="26HI0094",
        summary_count=0,
        endpoint_count=0,
        has_images=False,
        state="no_images",
        detail_sha256="a" * 64,
        list_sha256="b" * 64,
        note="Both source representations report no project images.",
    )
    bundle = tmp_path / "bundle"
    build_project_image_bundle((coverage,), (), "2026-11-04T00:00:00+00:00", bundle)

    release = finalize_coverage_release(
        bundle,
        summary=ImageCoverageSummary(1, {"no_images": 1}),
        source_sha256="c" * 64,
        released_at=datetime(2026, 11, 4, tzinfo=UTC),
        previous_manifest=None,
    )

    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["coverage_release"]["release_id"] == release.release_id
    assert manifest["publish_media"] == []
    assert release.completed_contracts == 1
