"""Targeted evidence acquisition for public-value research candidates."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.contract_evidence import STAGES

SHA256 = re.compile(r"[0-9a-f]{64}")
LIFECYCLE_STAGES = tuple(STAGES)
GATE_ORDER = ("identity", "need", "location", "design", "cost_delivery")
TASK_DEFINITIONS = (
    ("facility_registry", "identity", "Facility or asset registry record"),
    ("parcel_land_rights", "identity", "Parcel, ownership, and land-right record"),
    ("phase_history", "identity", "Prior work and related phase history"),
    ("needs_assessment", "need", "Needs assessment and named public function"),
    ("catchment_demand", "need", "Catchment population and intended users"),
    ("nearby_facility_utilization", "need", "Nearby equivalent facilities and use"),
    ("verified_site", "location", "Verified site and project coordinates"),
    ("hazard_assessment", "location", "Official hazard and ground assessment"),
    ("site_access_utilities", "location", "Access, utilities, drainage, and right of way"),
    ("plans_specifications", "design", "Approved plans and specifications"),
    ("capacity_floor_area", "design", "Capacity, floor area, and intended function"),
    ("accessibility_compliance", "design", "Accessibility and design compliance"),
    ("procurement_plan", "cost_delivery", "Procurement plan"),
    ("bid_notice", "cost_delivery", "Bid notice"),
    (
        "procurement_monitoring_report",
        "cost_delivery",
        "Procurement monitoring report",
    ),
    ("award_notice", "cost_delivery", "Award notice"),
    ("signed_contract", "cost_delivery", "Signed contract"),
    ("notice_to_proceed", "cost_delivery", "Notice to proceed"),
    ("completion_certificate", "cost_delivery", "Completion certificate"),
    ("inspection_acceptance", "cost_delivery", "Inspection and acceptance record"),
    ("payment_record", "cost_delivery", "Payment and disbursement record"),
    (
        "utilization_maintenance",
        "cost_delivery",
        "Utilization and maintenance after completion",
    ),
)
TASK_INDEX = {task_id: (gate, label) for task_id, gate, label in TASK_DEFINITIONS}
ALLOWED_LIFECYCLE_STATUSES = frozenset(
    {
        "pending",
        "secondary_exact",
        "verified_archived",
        "retry",
        "blocked",
        "not_located",
        "quarantined",
    }
)


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("checked_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("checked_at must include a timezone")
    return value


def _candidate_ids(candidates: list[dict[str, Any]]) -> tuple[str, ...]:
    identifiers = tuple(str(item.get("contract_id") or "").strip() for item in candidates)
    if not identifiers or any(not item for item in identifiers):
        raise ValueError("candidate identifiers must be non-empty")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("candidate identifiers must be unique")
    return identifiers


def _validate_lifecycle_task(row: dict[str, Any], candidate_ids: set[str]) -> None:
    contract_id = row.get("contract_id")
    stage = row.get("stage")
    status = row.get("status")
    if contract_id not in candidate_ids or stage not in LIFECYCLE_STAGES:
        raise ValueError("lifecycle task is outside the targeted queue")
    if status not in ALLOWED_LIFECYCLE_STATUSES:
        raise ValueError(f"unsupported lifecycle status: {status}")
    if status == "secondary_exact" and stage != "award_notice":
        raise ValueError("secondary exact state is allowed only for award notices")
    if status == "verified_archived":
        sha256 = row.get("artifact_sha256")
        if not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None:
            raise ValueError("verified task requires an archived official artifact")
        if not isinstance(row.get("source_url"), str) or not row["source_url"].strip():
            raise ValueError("verified task requires an official source URL")


def _lifecycle_index(
    rows: list[dict[str, Any]], candidate_ids: tuple[str, ...]
) -> dict[tuple[str, str], dict[str, Any]]:
    candidates = set(candidate_ids)
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        _validate_lifecycle_task(row, candidates)
        key = (row["contract_id"], row["stage"])
        if key in indexed:
            raise ValueError(f"duplicate lifecycle task: {key[0]}:{key[1]}")
        indexed[key] = row
    expected = {(contract_id, stage) for contract_id in candidates for stage in STAGES}
    if set(indexed) != expected:
        raise ValueError("lifecycle task set is incomplete for the targeted queue")
    return indexed


def _base_task(
    contract_id: str,
    task_id: str,
    gate: str,
    label: str,
    order: int,
) -> dict[str, Any]:
    return {
        "task_id": f"{contract_id}:{task_id}",
        "contract_id": contract_id,
        "evidence_type": task_id,
        "gate": gate,
        "label": label,
        "task_order": order,
        "status": "pending",
        "source_url": None,
        "artifact_sha256": None,
        "evidence_note": "Required evidence has not yet been archived and validated.",
    }


def _lifecycle_task(task: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    status = lifecycle["status"]
    notes = {
        "pending": "No accepted lifecycle artifact is attached to this task.",
        "secondary_exact": (
            "An exact row exists in the secondary award mirror. It is a discovery "
            "lead, not an archived official award notice."
        ),
        "verified_archived": "An official artifact passed archive and identity checks.",
        "retry": "The source check is scheduled for another attempt.",
        "blocked": "The source could not be acquired under the current method.",
        "not_located": "No qualifying source was located in the completed search.",
        "quarantined": "A possible record is held because its identity is ambiguous.",
    }
    return {
        **task,
        "status": status,
        "source_url": lifecycle.get("source_url"),
        "artifact_sha256": lifecycle.get("artifact_sha256"),
        "evidence_note": notes[status],
    }


def _apply_project_media(
    tasks: list[dict[str, Any]], media: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if not media or media.get("coverage_state") != "verified_exact":
        return tasks
    sha256 = media.get("artifact_sha256")
    if not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None:
        raise ValueError("verified project media requires an archived artifact digest")
    result = []
    for task in tasks:
        if task["evidence_type"] != "verified_site":
            result.append(task)
            continue
        result.append(
            {
                **task,
                "status": "source_media_archived",
                "artifact_sha256": sha256,
                "source_url": media.get("source_url"),
                "reader_url": media.get("reader_url"),
                "evidence_note": (
                    "DPWH source media passed file and count checks. It does not "
                    "independently prove the exact site, capture time, or completion."
                ),
            }
        )
    return result


def _official_status(status: str) -> str:
    return {
        "official_artifact_archived": "verified_archived",
        "official_summary_archived": "official_summary_archived",
        "indexed_unarchived": "indexed_unarchived",
        "source_conflict_quarantined": "quarantined",
    }.get(status, "")


def _official_note(record: dict[str, Any], status: str) -> str:
    if status == "verified_archived":
        return "The exact official artifact was archived and passed identity checks."
    if status == "official_summary_archived":
        return (
            "An archived official summary reports this stage. It is not the underlying "
            "notice, signed contract, certificate, or receipt."
        )
    if status == "indexed_unarchived":
        return (
            "The official document is indexed, but its source bytes could not be "
            "archived. This remains an acquisition lead."
        )
    return str(record.get("limitation") or "Conflicting official identity evidence is quarantined.")


def _official_records(
    review: dict[str, Any] | None,
    candidate_ids: tuple[str, ...],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if review is None:
        return {}
    contracts = review.get("contracts")
    records = review.get("records")
    if not isinstance(contracts, dict) or set(contracts) != set(candidate_ids):
        raise ValueError("official review contract set must match the targeted queue")
    if not isinstance(records, list):
        raise ValueError("official review records must be a list")
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("official review records must be objects")
        key = (record.get("contract_id"), record.get("evidence_type"))
        if key[0] not in candidate_ids or key[1] not in TASK_INDEX:
            raise ValueError("official review record is outside the targeted queue")
        status = _official_status(str(record.get("status") or ""))
        source_url = record.get("source_url")
        sha256 = record.get("artifact_sha256")
        if not status or not isinstance(source_url, str) or not source_url.startswith("https://"):
            raise ValueError("official review record has an invalid state or source URL")
        requires_digest = status in {"verified_archived", "official_summary_archived"}
        if requires_digest and (not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None):
            raise ValueError("archived official review record requires an artifact digest")
        if status == "indexed_unarchived" and sha256 is not None:
            raise ValueError("unarchived official review record cannot claim an artifact digest")
        if (
            status == "quarantined"
            and sha256 is not None
            and (not isinstance(sha256, str) or SHA256.fullmatch(sha256) is None)
        ):
            raise ValueError("quarantined official review digest is invalid")
        indexed[(str(key[0]), str(key[1]))].append(record)
    return indexed


def _apply_official_records(
    tasks: list[dict[str, Any]],
    records: dict[tuple[str, str], list[dict[str, Any]]],
    contract_id: str,
) -> list[dict[str, Any]]:
    priority = {
        "indexed_unarchived": 1,
        "verified_archived": 2,
        "official_summary_archived": 3,
        "quarantined": 4,
    }
    result = []
    for task in tasks:
        matches = records.get((contract_id, task["evidence_type"]), [])
        if not matches:
            result.append(task)
            continue
        selected = max(matches, key=lambda row: priority[_official_status(row["status"])])
        status = _official_status(selected["status"])
        result.append(
            {
                **task,
                "status": status,
                "source_url": selected["source_url"],
                "artifact_sha256": selected["artifact_sha256"],
                "evidence_note": _official_note(selected, status),
            }
        )
    return result


def _project_tasks(
    contract_id: str,
    lifecycle: dict[tuple[str, str], dict[str, Any]],
    media: dict[str, Any] | None,
    official_records: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    tasks = []
    for order, (task_id, gate, label) in enumerate(TASK_DEFINITIONS, start=1):
        task = _base_task(contract_id, task_id, gate, label, order)
        if task_id in LIFECYCLE_STAGES:
            task = _lifecycle_task(task, lifecycle[(contract_id, task_id)])
        tasks.append(task)
    with_media = _apply_project_media(tasks, media)
    return _apply_official_records(with_media, official_records, contract_id)


def _counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item["status"] for item in tasks)
    ordered = (
        "verified_archived",
        "official_summary_archived",
        "indexed_unarchived",
        "secondary_exact",
        "source_media_archived",
        "pending",
        "retry",
        "blocked",
        "not_located",
        "quarantined",
    )
    return {key: counts[key] for key in ordered if counts[key]}


def _candidate_summary(candidate: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    gate_tasks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        gate_tasks[task["gate"]].append(task)
    return {
        "contract_id": candidate["contract_id"],
        "reader_url": candidate.get("reader_url"),
        "selection_reasons": list(candidate.get("selection_reasons", [])),
        "task_count": len(tasks),
        "status_counts": _counts(tasks),
        "gate_counts": {gate: _counts(gate_tasks[gate]) for gate in GATE_ORDER},
        "assessment_state": (
            "source_conflict_quarantined"
            if any(item["status"] == "quarantined" for item in tasks)
            else "cannot_assess_from_current_evidence"
        ),
    }


def build_public_value_acquisition(
    candidates: list[dict[str, Any]],
    lifecycle_tasks: list[dict[str, Any]],
    *,
    project_media: dict[str, dict[str, Any]],
    checked_at: str,
    source_identities: dict[str, str],
    official_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the private task inventory and its public-safe coverage summary."""

    candidate_ids = _candidate_ids(candidates)
    lifecycle = _lifecycle_index(lifecycle_tasks, candidate_ids)
    unknown_media = set(project_media) - set(candidate_ids)
    if unknown_media:
        raise ValueError(f"project media is outside the targeted queue: {sorted(unknown_media)}")
    official_records = _official_records(official_review, candidate_ids)
    all_tasks: list[dict[str, Any]] = []
    summaries = []
    for candidate in candidates:
        contract_id = candidate["contract_id"]
        tasks = _project_tasks(
            contract_id,
            lifecycle,
            project_media.get(contract_id),
            official_records,
        )
        all_tasks.extend(tasks)
        summaries.append(_candidate_summary(candidate, tasks))
    gate_tasks = {gate: [task for task in all_tasks if task["gate"] == gate] for gate in GATE_ORDER}
    return {
        "schema_version": 1,
        "checked_at": _timestamp(checked_at),
        "source_identities": dict(sorted(source_identities.items())),
        "task_definitions": [
            {"id": task_id, "gate": gate, "label": label}
            for task_id, gate, label in TASK_DEFINITIONS
        ],
        "summary": {
            "candidate_count": len(candidates),
            "task_count": len(all_tasks),
            "verified_archived": _counts(all_tasks).get("verified_archived", 0),
            "official_summary_archived": _counts(all_tasks).get("official_summary_archived", 0),
            "indexed_unarchived": _counts(all_tasks).get("indexed_unarchived", 0),
            "secondary_exact": _counts(all_tasks).get("secondary_exact", 0),
            "source_media_archived": _counts(all_tasks).get("source_media_archived", 0),
            "pending": _counts(all_tasks).get("pending", 0),
            "quarantined": _counts(all_tasks).get("quarantined", 0),
        },
        "gate_counts": {gate: _counts(gate_tasks[gate]) for gate in GATE_ORDER},
        "candidates": sorted(summaries, key=lambda item: item["contract_id"]),
        "tasks": all_tasks,
        "limitations": [
            "A queued task records work still required. It is not evidence that the document exists or that the project failed a check.",
            "An exact secondary award row is a discovery lead, not an archived official award notice.",
            "Archived source media does not independently prove exact location, capture time, completion, quality, payment, or public value.",
            "An indexed official URL is a discovery lead until the source bytes are archived, hashed, and identity-checked.",
            "Conflicting contract identities are quarantined and are not counted as verified evidence.",
        ],
    }


PRIVATE_QUEUE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE queue_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE queue_candidates (
    contract_id TEXT PRIMARY KEY,
    reader_url TEXT,
    assessment_state TEXT NOT NULL
);
CREATE TABLE acquisition_tasks (
    task_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES queue_candidates(contract_id),
    evidence_type TEXT NOT NULL,
    gate_id TEXT NOT NULL,
    task_order INTEGER NOT NULL,
    status TEXT NOT NULL,
    source_url TEXT,
    artifact_sha256 TEXT,
    evidence_note TEXT NOT NULL,
    UNIQUE(contract_id, evidence_type)
);
CREATE INDEX acquisition_tasks_status ON acquisition_tasks(status, gate_id, task_order);
"""


def write_private_acquisition_queue(path: Path, snapshot: dict[str, Any]) -> None:
    """Atomically write the targeted queue. This database is not a public artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    building = path.with_name(f".{path.name}.building")
    building.unlink(missing_ok=True)
    connection = sqlite3.connect(building)
    try:
        connection.executescript(PRIVATE_QUEUE_SCHEMA)
        metadata = {
            "checked_at": snapshot["checked_at"],
            "schema_version": str(snapshot["schema_version"]),
            "source_identities": json.dumps(
                snapshot["source_identities"], sort_keys=True, separators=(",", ":")
            ),
            "task_count": str(snapshot["summary"]["task_count"]),
        }
        connection.executemany("INSERT INTO queue_metadata VALUES (?, ?)", sorted(metadata.items()))
        connection.executemany(
            "INSERT INTO queue_candidates VALUES (?, ?, ?)",
            [
                (
                    item["contract_id"],
                    item.get("reader_url"),
                    item["assessment_state"],
                )
                for item in snapshot["candidates"]
            ],
        )
        connection.executemany(
            "INSERT INTO acquisition_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item["task_id"],
                    item["contract_id"],
                    item["evidence_type"],
                    item["gate"],
                    item["task_order"],
                    item["status"],
                    item.get("source_url"),
                    item.get("artifact_sha256"),
                    item["evidence_note"],
                )
                for item in snapshot["tasks"]
            ],
        )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("public-value acquisition queue integrity check failed")
        connection.commit()
    finally:
        connection.close()
    building.replace(path)
