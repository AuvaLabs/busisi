import json
from pathlib import Path

import pytest

from engine.budget_watchdog.public_value_acquisition import (
    LIFECYCLE_STAGES,
    build_public_value_acquisition,
)
from engine.budget_watchdog.research_editor import validate_research_release
from engine.budget_watchdog.research_public_value_acquisition import (
    build_public_value_acquisition_release,
)

ROOT = Path(__file__).resolve().parents[3]
V4 = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v4"
)


def _v4_release() -> dict:
    manifest = json.loads((V4 / "manifest.json").read_text())
    metadata = {
        key: value for key, value in manifest.items() if key not in {"files", "package_sha256"}
    }
    return {
        "metadata": metadata,
        **{
            key.replace("-", "_"): json.loads((V4 / filename).read_text())
            for filename, key in (
                ("chart-data.json", "chart_data"),
                ("claims.json", "claims"),
                ("editorial-package.json", "editorial_package"),
                ("findings.json", "findings"),
                ("investigations.json", "investigations"),
                ("limitations.json", "limitations"),
                ("project-examples.json", "project_examples"),
                ("sources.json", "sources"),
                ("story.json", "story"),
            )
        },
    }


def _acquisition(release: dict) -> dict:
    candidates = release["project_examples"]["public_value_candidates"]
    lifecycle = []
    for position, candidate in enumerate(candidates):
        for stage in LIFECYCLE_STAGES:
            lifecycle.append(
                {
                    "contract_id": candidate["contract_id"],
                    "stage": stage,
                    "status": (
                        "secondary_exact"
                        if position < 38 and stage == "award_notice"
                        else "pending"
                    ),
                    "source_url": None,
                    "artifact_sha256": None,
                }
            )
    return build_public_value_acquisition(
        candidates,
        lifecycle,
        project_media={
            candidates[-1]["contract_id"]: {
                "coverage_state": "verified_exact",
                "artifact_sha256": "a" * 64,
                "reader_url": f"{candidates[-1]['reader_url']}#project-images",
            }
        },
        checked_at="2026-11-05T04:00:00+00:00",
        source_identities={"lifecycle_queue_sha256": "b" * 64},
    )


def _new_sources() -> list[dict]:
    return [
        {
            "id": "bettergov-philgeps-snapshot-2026-01-06",
            "publisher": "Philippine Government Electronic Procurement System",
            "access_provider": "BetterGov.ph",
            "source_kind": "civil_society_research",
            "scope": "Version-pinned mirror used only to locate exact award-row leads",
            "modified": "2026-01-06",
            "retrieved_at": "2026-11-03",
            "origin_url": "https://notices.philgeps.gov.ph/",
            "source_url": "https://huggingface.co/datasets/bettergovph/philgeps-data",
            "sha256": "9" * 64,
        },
        {
            "id": "dpwh-project-media-release-2026-11-05",
            "publisher": "Department of Public Works and Highways",
            "access_provider": "Department of Public Works and Highways",
            "source_kind": "official_dataset",
            "scope": "Gated DPWH project-image acquisition release",
            "modified": "2026-11-05",
            "retrieved_at": "2026-11-05",
            "origin_url": "https://www.dpwh.gov.ph/",
            "source_url": "https://transparency.dpwh.gov.ph/",
            "sha256": "8" * 64,
        },
    ]


def test_extends_release_with_targeted_acquisition_coverage() -> None:
    base = _v4_release()
    release = build_public_value_acquisition_release(
        base,
        _acquisition(base),
        acquisition_sources=_new_sources(),
        supersedes={
            "version": 4,
            "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v4/manifest.json",
            "package_sha256": "4" * 64,
        },
    )

    claims = {item["id"]: item for item in release["claims"]}
    assert release["metadata"]["version"] == 5
    assert release["metadata"]["methodology_version"] == "mpb-public-value-acquisition-v1"
    assert claims["mpb-acquisition-tasks"]["value"] == 946
    assert claims["mpb-secondary-award-leads"]["value"] == 38
    assert claims["mpb-source-media-leads"]["value"] == 1
    assert claims["mpb-official-verified-tasks"]["value"] == 0
    assert claims["mpb-pending-acquisition-tasks"]["value"] == 907
    assert release["chart_data"]["public_value_acquisition"]["task_count"] == 946
    assert all(
        item["acquisition"]["task_count"] == 22
        for item in release["project_examples"]["public_value_candidates"]
    )
    assert release["story"]["sections"][-1]["narration_eligible"] is False
    validate_research_release(release)


def test_rejects_acquisition_candidate_mismatch() -> None:
    base = _v4_release()
    acquisition = _acquisition(base)
    acquisition["candidates"] = acquisition["candidates"][:-1]

    with pytest.raises(ValueError, match="candidate set"):
        build_public_value_acquisition_release(
            base,
            acquisition,
            acquisition_sources=_new_sources(),
            supersedes={
                "version": 4,
                "manifest_url": "https://busisi.org/data/research/multipurpose-buildings/v4/manifest.json",
                "package_sha256": "4" * 64,
            },
        )
