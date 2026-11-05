"""Project-level evidence coverage for the multipurpose-building investigation."""

from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.research_editor import build_consumption_index
from engine.budget_watchdog.research_multipurpose_value import (
    build_multipurpose_value_release,
)

DPWH_SOURCE_ID = "dpwh-delivery-snapshot-2026-01-22"
GATE_ORDER = ("identity", "need", "location", "design", "cost_delivery")


def _row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        contract_id = row.get("contractId")
        if not isinstance(contract_id, str) or not contract_id.strip():
            continue
        contract_id = contract_id.strip()
        if contract_id in indexed:
            raise ValueError(f"duplicate contract id in source rows: {contract_id}")
        indexed[contract_id] = row
    return indexed


def _location(row: dict[str, Any], field: str) -> str:
    location = row.get("location")
    if not isinstance(location, dict):
        return "Not stated"
    value = location.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else "Not stated"


def _coordinate_e6(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    coordinate = Decimal(str(value))
    if not coordinate.is_finite():
        return None
    return int(
        (coordinate * Decimal(1_000_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _coordinates(row: dict[str, Any]) -> dict[str, int] | None:
    latitude = _coordinate_e6(row.get("latitude"))
    longitude = _coordinate_e6(row.get("longitude"))
    if latitude is None or longitude is None:
        return None
    return {"latitude": latitude, "longitude": longitude}


def _budget_centavos(row: dict[str, Any]) -> int:
    value = row.get("budget")
    normalized = Decimal(str(value)) if isinstance(value, float) else value
    return parse_centavos(normalized)


def _gate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "identity",
            "title": "Project and facility identity",
            "question": "Is this a distinct facility, another phase, a repair, or a replacement?",
            "required_evidence": [
                "Verified facility or asset identifier",
                "Parcel and ownership record",
                "Prior and related project records",
            ],
        },
        {
            "id": "need",
            "title": "Need and intended public use",
            "question": "What public need will this project address, and who will use it?",
            "required_evidence": [
                "Needs assessment and named public function",
                "Catchment population or intended users",
                "Nearby equivalent facilities and utilization",
            ],
        },
        {
            "id": "location",
            "title": "Location and site suitability",
            "question": "Is the verified site appropriate and safe for the intended use?",
            "required_evidence": [
                "Verified parcel and project coordinates",
                "Official hazard assessment and ground validation",
                "Access, utilities, drainage, and right-of-way evidence",
            ],
        },
        {
            "id": "design",
            "title": "Design, capacity, and accessibility",
            "question": "Does the design fit the intended public function?",
            "required_evidence": [
                "Plans, floor area, capacity, and specifications",
                "Structural, climate, sanitation, and accessibility review",
                "Design approval and professional accountability",
            ],
        },
        {
            "id": "cost_delivery",
            "title": "Cost, delivery, and actual use",
            "question": "Was the project fairly procured, delivered, accepted, and used?",
            "required_evidence": [
                "Bill of quantities and comparable unit costs",
                "Award, variations, payments, inspection, and acceptance",
                "Actual utilization and maintenance after completion",
            ],
        },
    ]


def _selection_maps(
    release: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    coordinate_candidates = {
        item["contract_id"]: item
        for item in release["project_examples"]["prior_coordinate_candidates"]
    }
    largest_ids = {
        item["contract_id"]
        for item in release["project_examples"]["largest_active_recorded_budgets"]
    }
    return coordinate_candidates, largest_ids


def _selection_reasons(
    contract_id: str,
    coordinate_candidates: dict[str, dict[str, Any]],
    largest_ids: set[str],
) -> list[str]:
    reasons = []
    if contract_id in coordinate_candidates:
        reasons.append("exact_coordinate_history")
    if contract_id in largest_ids:
        reasons.append("largest_active_recorded_budget")
    return reasons


def _gate_states(
    *, coordinate_history: bool, coordinates: dict[str, int] | None
) -> dict[str, str]:
    if coordinate_history:
        location_state = "review_lead"
    elif coordinates is not None:
        location_state = "partial"
    else:
        location_state = "not_in_snapshot"
    return {
        "identity": "partial",
        "need": "not_in_snapshot",
        "location": location_state,
        "design": "not_in_snapshot",
        "cost_delivery": "partial",
    }


def _candidate(
    contract_id: str,
    row: dict[str, Any],
    coordinate_candidates: dict[str, dict[str, Any]],
    largest_ids: set[str],
) -> dict[str, Any]:
    coordinate_item = coordinate_candidates.get(contract_id)
    coordinates = _coordinates(row)
    year = row.get("infraYear")
    return {
        "contract_id": contract_id,
        "fiscal_year": int(year) if isinstance(year, str) and year.isdigit() else None,
        "description": str(row.get("description") or "Description not stated"),
        "status": str(row.get("status") or "Not stated"),
        "recorded_budget_centavos": _budget_centavos(row),
        "district_office": _location(row, "province"),
        "region": _location(row, "region"),
        "coordinates_e6": coordinates,
        "source_image_state": (
            "reported_available" if row.get("hasSatelliteImage") is True else "not_reported"
        ),
        "selection_reasons": _selection_reasons(
            contract_id, coordinate_candidates, largest_ids
        ),
        "related_completed_records": (
            coordinate_item.get("completed_contracts", []) if coordinate_item else []
        ),
        "gate_states": _gate_states(
            coordinate_history=coordinate_item is not None,
            coordinates=coordinates,
        ),
        "assessment_state": "cannot_assess_from_current_evidence",
        "reader_url": f"/contracts/{contract_id}/",
    }


def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    coordinate_priority = int("exact_coordinate_history" not in item["selection_reasons"])
    return (
        coordinate_priority,
        -item["recorded_budget_centavos"],
        item["contract_id"],
    )


def _build_candidates(
    rows: list[dict[str, Any]], release: dict[str, Any]
) -> tuple[list[dict[str, Any]], int, int, int]:
    indexed = _row_index(rows)
    coordinate_candidates, largest_ids = _selection_maps(release)
    candidate_ids = set(coordinate_candidates) | largest_ids
    missing = candidate_ids - indexed.keys()
    if missing:
        raise ValueError(f"candidate contract ids are absent from source rows: {sorted(missing)}")
    candidates = [
        _candidate(contract_id, indexed[contract_id], coordinate_candidates, largest_ids)
        for contract_id in candidate_ids
    ]
    candidates.sort(key=_candidate_sort_key)
    return (
        candidates,
        len(coordinate_candidates),
        len(largest_ids),
        len(set(coordinate_candidates) & largest_ids),
    )


def _gate_counts(candidates: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        gate: dict(
            sorted(Counter(item["gate_states"][gate] for item in candidates).items())
        )
        for gate in GATE_ORDER
    }


def _claim(
    identifier: str,
    statement: str,
    value: int,
    *,
    evidence_state: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "value": value,
        "unit": "project records",
        "scope": "Bounded multipurpose-building public-value evidence queue",
        "evidence_state": evidence_state,
        "calculation_id": "mpb-public-value-evidence-v1",
        "source_ids": [DPWH_SOURCE_ID],
        "limitations": [
            "Selection for evidence review is not a finding that a project is unnecessary, duplicated, improperly located, or overpriced."
        ],
    }


def _extend_release(
    release: dict[str, Any],
    candidates: list[dict[str, Any]],
    coordinate_count: int,
    largest_count: int,
    overlap: int,
) -> None:
    release["claims"].extend(
        [
            _claim(
                "mpb-public-value-candidates",
                "The first public-value evidence queue contains the stated number of distinct project records.",
                len(candidates),
                evidence_state="verified",
            ),
            _claim(
                "mpb-coordinate-history-candidates",
                "The queue includes the stated number of exact-coordinate history review leads.",
                coordinate_count,
                evidence_state="review_candidate",
            ),
            _claim(
                "mpb-largest-budget-candidates",
                "The queue includes the stated number of largest active recorded-budget projects.",
                largest_count,
                evidence_state="verified",
            ),
            _claim(
                "mpb-fully-assessed-candidates",
                "No queued project currently has enough evidence to pass every public-value gate.",
                0,
                evidence_state="not_supported",
            ),
        ]
    )
    release["chart_data"]["public_value_evidence"] = {
        "candidate_count": len(candidates),
        "coordinate_history_candidates": coordinate_count,
        "largest_budget_candidates": largest_count,
        "selection_overlap": overlap,
        "fully_assessed": 0,
        "gate_definitions": _gate_definitions(),
        "gate_counts": _gate_counts(candidates),
    }
    release["project_examples"]["public_value_candidates"] = candidates
    release["investigations"].append(
        {
            "question": "Which queued projects have enough evidence for a public-value judgment?",
            "result": f"0 of {len(candidates)} pass every evidence gate in this release.",
            "state": "evidence_gap",
            "calculation_id": "mpb-public-value-evidence-v1",
        }
    )
    release["limitations"].append(
        {
            "id": "public-value-selection-boundary",
            "text": "The queue is selected from exact-coordinate history and the largest active recorded budgets. It is not a risk score, accusation, or representative sample of all projects.",
        }
    )
    release["story"]["sections"].append(
        {
            "id": "public-value-evidence-queue",
            "section_type": "investigation_lead",
            "heading": "A project-level evidence queue makes the missing proof visible",
            "copy": [
                f"The first queue contains {len(candidates):,} distinct records: {coordinate_count:,} exact-coordinate history leads and {largest_count:,} largest recorded-budget projects, with {overlap:,} record or records appearing in both selections.",
                "No queued project currently has enough acquired evidence for a complete judgment about need, location, design, cost, delivery, and actual use.",
                "Selection identifies where evidence collection starts. It is not a finding that a project is unnecessary, duplicated, improperly located, overpriced, or associated with wrongdoing.",
            ],
            "claim_ids": [
                "mpb-public-value-candidates",
                "mpb-coordinate-history-candidates",
                "mpb-largest-budget-candidates",
                "mpb-fully-assessed-candidates",
            ],
            "source_ids": [DPWH_SOURCE_ID],
            "visual_refs": [
                "chart_data.public_value_evidence",
                "project_examples.public_value_candidates",
            ],
            "limitation_ids": [
                "public-value-selection-boundary",
                "necessity-boundary",
                "siting-design-boundary",
            ],
            "narration_eligible": False,
        }
    )


def build_public_value_evidence_release(
    all_rows: list[dict[str, Any]],
    *,
    source_sha256: str,
    source_modified: str,
    published_at: str,
    benchmark_sources: list[dict[str, Any]],
    classroom_benchmarks: list[dict[str, Any]],
    supersedes: dict[str, Any],
) -> dict[str, Any]:
    """Build version 4 with a bounded project-level public-value evidence queue."""

    release = build_multipurpose_value_release(
        all_rows,
        source_sha256=source_sha256,
        source_modified=source_modified,
        published_at=published_at,
        benchmark_sources=benchmark_sources,
        classroom_benchmarks=classroom_benchmarks,
        supersedes=supersedes,
    )
    release["metadata"].update(
        {
            "version": 4,
            "methodology_version": "mpb-public-value-evidence-v1",
            "supersedes": supersedes,
        }
    )
    release["story"]["version"] = 4
    candidates, coordinate_count, largest_count, overlap = _build_candidates(
        all_rows, release
    )
    _extend_release(release, candidates, coordinate_count, largest_count, overlap)
    release["editorial_package"] = build_consumption_index(
        release["metadata"], release["sources"]
    )
    return release
