"""Add targeted evidence-acquisition coverage to the public-value release."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.budget_watchdog.research_editor import build_consumption_index

DPWH_SOURCE_ID = "dpwh-delivery-snapshot-2026-01-22"
AWARD_SOURCE_ID = "bettergov-philgeps-snapshot-2026-01-06"
MEDIA_SOURCE_ID = "dpwh-project-media-release-2026-11-05"
CALCULATION_ID = "mpb-public-value-acquisition-v1"


def _claim(
    identifier: str,
    statement: str,
    value: int,
    *,
    evidence_state: str,
    source_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "value": value,
        "unit": "evidence checks",
        "scope": "Targeted acquisition queue for 43 multipurpose-building records",
        "evidence_state": evidence_state,
        "calculation_id": CALCULATION_ID,
        "source_ids": source_ids,
        "limitations": [
            "A task state describes evidence coverage, not whether a project is necessary, properly located, fairly priced, completed, or associated with wrongdoing."
        ],
    }


def _validate_candidate_set(
    release: dict[str, Any], acquisition: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    release_ids = {
        item["contract_id"] for item in release["project_examples"]["public_value_candidates"]
    }
    acquired = {item["contract_id"]: item for item in acquisition["candidates"]}
    if set(acquired) != release_ids or len(acquired) != len(acquisition["candidates"]):
        raise ValueError("acquisition candidate set must match the public-value queue")
    expected_tasks = len(release_ids) * len(acquisition["task_definitions"])
    if acquisition["summary"]["task_count"] != expected_tasks:
        raise ValueError("acquisition task total does not reconcile to the candidate set")
    return acquired


def _append_sources(release: dict[str, Any], acquisition_sources: list[dict[str, Any]]) -> None:
    identifiers = {item["id"] for item in release["sources"]}
    for source in acquisition_sources:
        source_id = source.get("id")
        if source_id in identifiers:
            raise ValueError(f"duplicate acquisition source: {source_id}")
        release["sources"].append(deepcopy(source))
        identifiers.add(source_id)
    required = {AWARD_SOURCE_ID, MEDIA_SOURCE_ID}
    if not required.issubset(identifiers):
        raise ValueError("acquisition sources are incomplete")


def _extend_claims(release: dict[str, Any], summary: dict[str, int]) -> None:
    release["claims"].extend(
        [
            _claim(
                "mpb-acquisition-tasks",
                "The targeted queue contains the stated number of distinct evidence checks.",
                summary["task_count"],
                evidence_state="verified",
                source_ids=[DPWH_SOURCE_ID, AWARD_SOURCE_ID, MEDIA_SOURCE_ID],
            ),
            _claim(
                "mpb-official-verified-tasks",
                "No targeted evidence check yet has a complete archived official artifact that proves its requirement.",
                summary["verified_archived"],
                evidence_state="not_supported",
                source_ids=[DPWH_SOURCE_ID, MEDIA_SOURCE_ID],
            ),
            _claim(
                "mpb-secondary-award-leads",
                "The stated number of award checks have exact rows in the secondary award mirror.",
                summary["secondary_exact"],
                evidence_state="review_candidate",
                source_ids=[AWARD_SOURCE_ID],
            ),
            _claim(
                "mpb-source-media-leads",
                "The stated number of site checks have archived DPWH source media but still require independent location evidence.",
                summary["source_media_archived"],
                evidence_state="source_reported",
                source_ids=[MEDIA_SOURCE_ID],
            ),
            _claim(
                "mpb-pending-acquisition-tasks",
                "The stated number of targeted evidence checks still have no accepted artifact or discovery lead.",
                summary["pending"],
                evidence_state="verified",
                source_ids=[DPWH_SOURCE_ID, AWARD_SOURCE_ID, MEDIA_SOURCE_ID],
            ),
        ]
    )


def _extend_story(release: dict[str, Any], summary: dict[str, int]) -> None:
    release["limitations"].extend(
        [
            {
                "id": "acquisition-queue-boundary",
                "text": "A queued evidence check is work still required. It does not show that a document exists or that a project failed the check.",
            },
            {
                "id": "secondary-award-boundary",
                "text": "An exact secondary award row is a discovery lead and is not treated as an archived official award notice.",
            },
            {
                "id": "source-media-boundary",
                "text": "Archived source media does not independently prove exact location, capture time, completion, quality, payment, or public value.",
            },
        ]
    )
    release["investigations"].append(
        {
            "question": "How much of the 43-project evidence queue has been acquired?",
            "result": (
                f"{summary['verified_archived']} of {summary['task_count']} checks have "
                "a complete archived official artifact. "
                f"{summary['secondary_exact']} exact secondary award rows and "
                f"{summary['source_media_archived']} archived source-media record remain leads."
            ),
            "state": "evidence_gap",
            "calculation_id": CALCULATION_ID,
        }
    )
    release["story"]["sections"].append(
        {
            "id": "public-value-acquisition",
            "section_type": "investigation_lead",
            "heading": "The evidence checklist is now a tracked acquisition queue",
            "copy": [
                f"The 43 selected records produce {summary['task_count']:,} distinct evidence checks across identity, need, location, design, cost, delivery, and use.",
                f"The first reconciliation found {summary['secondary_exact']:,} exact secondary award rows and {summary['source_media_archived']:,} archived DPWH source-media record. Neither state is promoted to complete official evidence.",
                f"{summary['pending']:,} checks remain pending and no project is ready for a complete public-value judgment.",
            ],
            "claim_ids": [
                "mpb-acquisition-tasks",
                "mpb-official-verified-tasks",
                "mpb-secondary-award-leads",
                "mpb-source-media-leads",
                "mpb-pending-acquisition-tasks",
            ],
            "source_ids": [DPWH_SOURCE_ID, AWARD_SOURCE_ID, MEDIA_SOURCE_ID],
            "visual_refs": [
                "chart_data.public_value_acquisition",
                "project_examples.public_value_candidates",
            ],
            "limitation_ids": [
                "acquisition-queue-boundary",
                "secondary-award-boundary",
                "source-media-boundary",
                "public-value-selection-boundary",
            ],
            "narration_eligible": False,
        }
    )


def build_public_value_acquisition_release(
    base_release: dict[str, Any],
    acquisition: dict[str, Any],
    *,
    acquisition_sources: list[dict[str, Any]],
    supersedes: dict[str, Any],
) -> dict[str, Any]:
    """Build version 5 without exposing private queue records or source URLs."""

    release = deepcopy(base_release)
    acquired = _validate_candidate_set(release, acquisition)
    _append_sources(release, acquisition_sources)
    release["metadata"].update(
        {
            "version": 5,
            "methodology_version": CALCULATION_ID,
            "supersedes": deepcopy(supersedes),
        }
    )
    release["story"]["version"] = 5
    summary = acquisition["summary"]
    _extend_claims(release, summary)
    release["chart_data"]["public_value_acquisition"] = {
        **deepcopy(summary),
        "checked_at": acquisition["checked_at"],
        "source_identities": deepcopy(acquisition["source_identities"]),
        "task_definitions": deepcopy(acquisition["task_definitions"]),
        "gate_counts": deepcopy(acquisition["gate_counts"]),
        "limitations": list(acquisition["limitations"]),
    }
    for candidate in release["project_examples"]["public_value_candidates"]:
        candidate["acquisition"] = deepcopy(acquired[candidate["contract_id"]])
    _extend_story(release, summary)
    release["editorial_package"] = build_consumption_index(release["metadata"], release["sources"])
    return release
