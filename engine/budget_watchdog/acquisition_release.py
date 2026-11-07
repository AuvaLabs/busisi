"""Reconciled public summary for the full-universe acquisition engine."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, cast

from engine.budget_watchdog.acquisition_queue import QueueSummary
from engine.budget_watchdog.acquisition_universe import AcquisitionUniverseSnapshot
from engine.budget_watchdog.contract_evidence import STAGES

SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
MATCH_STATES = (
    "structured_exact",
    "title_exact",
    "multiple_exact_rows",
    "conflict_review",
    "no_exact_row",
    "invalid_identifier",
)


class AcquisitionReleaseError(ValueError):
    """Raised when a public acquisition summary fails reconciliation."""


def _category_group(value: str) -> str:
    text = value.casefold()
    rules = (
        (("gaa ",), "GAA itemized programs"),
        (("unprogrammed",), "Unprogrammed appropriations"),
        (("trust fund",), "Trust funds"),
        (("pamana",), "PAMANA"),
        (("bridge",), "Bridges"),
        (("building", "multi purpose"), "Buildings and facilities"),
        (("flood", "drainage"), "Flood control and drainage"),
        (("road", "fmr"), "Roads"),
        (("water", "dam"), "Water infrastructure"),
        (("port", "harbor"), "Ports and harbors"),
    )
    for keywords, label in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "Other infrastructure"


def _breakdowns(snapshot: AcquisitionUniverseSnapshot, field: str) -> list[dict[str, Any]]:
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for item in snapshot.contracts:
        value = str(getattr(item, field))
        key = _category_group(value) if field == "category" else value
        groups[key][item.match_state] += 1
    return [
        {
            "value": value,
            "total_contracts": sum(counts.values()),
            "state_counts": {state: counts.get(state, 0) for state in MATCH_STATES},
        }
        for value, counts in sorted(groups.items())
    ]


def build_acquisition_release(
    snapshot: AcquisitionUniverseSnapshot,
    queue_summary: QueueSummary,
    *,
    award_byte_size: int,
) -> dict[str, Any]:
    if award_byte_size <= 0:
        raise ValueError("award_byte_size must be positive")
    year_conflicts = sum(item.year_alignment == "conflict" for item in snapshot.contracts)
    valid_identifiers = sum(item.identifier_status == "valid" for item in snapshot.contracts)
    return {
        "schema_version": 1,
        "checked_on": snapshot.checked_on.isoformat(),
        "fiscal_years": list(snapshot.fiscal_years),
        "source": {
            "delivery_sha256": snapshot.delivery_sha256,
            "award_sha256": snapshot.award_sha256,
            "award_revision": snapshot.award_revision,
            "award_byte_size": award_byte_size,
            "award_source_rows": snapshot.summary.source_row_count,
            "award_source_archived": True,
            "evidence_class": "archived_secondary_source",
        },
        "summary": {
            "contract_count": snapshot.summary.contract_count,
            "examined_contracts": snapshot.summary.contract_count,
            "valid_identifiers": valid_identifiers,
            "year_alignment_conflicts": year_conflicts,
            "accepted_match_rows": snapshot.summary.accepted_match_rows,
            "quarantined_source_rows": snapshot.summary.quarantined_rows,
            "lifecycle_task_count": snapshot.summary.lifecycle_task_count,
            "match_state_counts": dict(snapshot.summary.state_counts),
        },
        "queue_status_counts": dict(queue_summary.status_counts),
        "year_breakdowns": _breakdowns(snapshot, "fiscal_year"),
        "category_breakdowns": _breakdowns(snapshot, "category"),
        "limitations": [
            "An exact mirror row is archived secondary evidence, not an official award notice.",
            "Multiple rows are preserved and no single award is selected automatically.",
            "Conflicting exact identifiers are quarantined from automatic publication.",
            "A pending lifecycle task is not evidence that a document does or does not exist.",
            "Category groups are deterministic labels derived from the source category text.",
        ],
    }


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcquisitionReleaseError(f"{field} must be a non-negative integer")
    return cast(int, value)


def _counts(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise AcquisitionReleaseError(f"{field} must be an object")
    return {str(key): _integer(count, f"{field}.{key}") for key, count in value.items()}


def _validate_breakdown(items: Any, expected: int, field: str) -> None:
    if not isinstance(items, list) or not items:
        raise AcquisitionReleaseError(f"{field} must be a non-empty array")
    total = 0
    for item in items:
        if not isinstance(item, dict) or not str(item.get("value", "")).strip():
            raise AcquisitionReleaseError(f"{field} entries must have a value")
        item_total = _integer(item.get("total_contracts"), f"{field}.total_contracts")
        states = _counts(item.get("state_counts"), f"{field}.state_counts")
        if set(states) != set(MATCH_STATES) or sum(states.values()) != item_total:
            raise AcquisitionReleaseError(f"{field} state totals do not reconcile")
        total += item_total
    if total != expected:
        raise AcquisitionReleaseError(f"{field} control total does not reconcile")


def load_acquisition_release(payload: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionReleaseError("acquisition release JSON is invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise AcquisitionReleaseError("unsupported acquisition release schema")
    source = raw.get("source")
    summary = raw.get("summary")
    if not isinstance(source, dict) or not isinstance(summary, dict):
        raise AcquisitionReleaseError("source and summary must be objects")
    if (
        SHA256.fullmatch(str(source.get("delivery_sha256"))) is None
        or SHA256.fullmatch(str(source.get("award_sha256"))) is None
        or REVISION.fullmatch(str(source.get("award_revision"))) is None
    ):
        raise AcquisitionReleaseError("source fingerprints are invalid")
    contract_count = _integer(summary.get("contract_count"), "contract_count")
    examined = _integer(summary.get("examined_contracts"), "examined_contracts")
    states = _counts(summary.get("match_state_counts"), "match_state_counts")
    if contract_count != examined or sum(states.values()) != contract_count:
        raise AcquisitionReleaseError("contract control total does not reconcile")
    tasks = _integer(summary.get("lifecycle_task_count"), "lifecycle_task_count")
    if tasks != contract_count * len(STAGES):
        raise AcquisitionReleaseError("lifecycle task control total does not reconcile")
    queue_counts = _counts(raw.get("queue_status_counts"), "queue_status_counts")
    if sum(queue_counts.values()) != tasks:
        raise AcquisitionReleaseError("queue control total does not reconcile")
    _validate_breakdown(raw.get("year_breakdowns"), contract_count, "year_breakdowns")
    _validate_breakdown(raw.get("category_breakdowns"), contract_count, "category_breakdowns")
    return raw
