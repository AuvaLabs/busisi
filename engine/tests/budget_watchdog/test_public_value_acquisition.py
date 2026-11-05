import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.public_value_acquisition import (
    LIFECYCLE_STAGES,
    TASK_DEFINITIONS,
    build_public_value_acquisition,
    write_private_acquisition_queue,
)


def _candidate(contract_id: str) -> dict:
    return {
        "contract_id": contract_id,
        "reader_url": f"/contracts/{contract_id}/",
        "selection_reasons": ["largest_active_recorded_budget"],
    }


def _lifecycle(contract_id: str, *, award_status: str = "pending") -> list[dict]:
    return [
        {
            "contract_id": contract_id,
            "stage": stage,
            "status": award_status if stage == "award_notice" else "pending",
            "source_url": None,
            "artifact_sha256": None,
        }
        for stage in LIFECYCLE_STAGES
    ]


def test_builds_complete_targeted_queue_without_promoting_leads() -> None:
    lifecycle = _lifecycle("25AA0001", award_status="secondary_exact")
    lifecycle.extend(_lifecycle("25AA0002"))
    snapshot = build_public_value_acquisition(
        [_candidate("25AA0001"), _candidate("25AA0002")],
        lifecycle,
        project_media={
            "25AA0002": {
                "coverage_state": "verified_exact",
                "artifact_sha256": "a" * 64,
                "reader_url": "/contracts/25AA0002/#project-images",
            }
        },
        checked_at="2026-11-05T04:00:00+00:00",
        source_identities={
            "lifecycle_queue_sha256": "b" * 64,
            "project_image_release_id": "c" * 64,
        },
    )

    assert len(TASK_DEFINITIONS) == 22
    assert snapshot["summary"] == {
        "candidate_count": 2,
        "task_count": 44,
        "verified_archived": 0,
        "secondary_exact": 1,
        "source_media_archived": 1,
        "pending": 42,
    }
    candidates = {item["contract_id"]: item for item in snapshot["candidates"]}
    assert candidates["25AA0001"]["gate_counts"]["cost_delivery"] == {
        "pending": 9,
        "secondary_exact": 1,
    }
    assert candidates["25AA0002"]["gate_counts"]["location"] == {
        "pending": 2,
        "source_media_archived": 1,
    }
    assert snapshot["gate_counts"]["identity"] == {"pending": 6}
    assert snapshot["limitations"][0].startswith("A queued task")


def test_rejects_verified_task_without_archived_official_evidence() -> None:
    rows = _lifecycle("25AA0001")
    rows[0]["status"] = "verified_archived"

    with pytest.raises(ValueError, match="verified task requires"):
        build_public_value_acquisition(
            [_candidate("25AA0001")],
            rows,
            project_media={},
            checked_at="2026-11-05T04:00:00+00:00",
            source_identities={"lifecycle_queue_sha256": "b" * 64},
        )


def test_rejects_duplicate_candidates_and_incomplete_lifecycle_rows() -> None:
    candidate = _candidate("25AA0001")
    with pytest.raises(ValueError, match="candidate identifiers must be unique"):
        build_public_value_acquisition(
            [candidate, dict(candidate)],
            _lifecycle("25AA0001"),
            project_media={},
            checked_at="2026-11-05T04:00:00+00:00",
            source_identities={"lifecycle_queue_sha256": "b" * 64},
        )

    with pytest.raises(ValueError, match="lifecycle task set is incomplete"):
        build_public_value_acquisition(
            [candidate],
            _lifecycle("25AA0001")[:-1],
            project_media={},
            checked_at="2026-11-05T04:00:00+00:00",
            source_identities={"lifecycle_queue_sha256": "b" * 64},
        )


def test_writes_private_queue_with_integrity_metadata(tmp_path: Path) -> None:
    lifecycle = _lifecycle("25AA0001", award_status="secondary_exact")
    snapshot = build_public_value_acquisition(
        [_candidate("25AA0001")],
        lifecycle,
        project_media={},
        checked_at="2026-11-05T04:00:00+00:00",
        source_identities={"lifecycle_queue_sha256": "b" * 64},
    )
    path = tmp_path / "queue.sqlite3"
    write_private_acquisition_queue(path, snapshot)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM acquisition_tasks").fetchone()[0] == 22
        metadata = dict(connection.execute("SELECT key, value FROM queue_metadata"))
        assert json.loads(metadata["source_identities"])["lifecycle_queue_sha256"] == "b" * 64
    finally:
        connection.close()
