"""Value-for-money expansion for the multipurpose-building research release."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.research_editor import build_consumption_index
from engine.budget_watchdog.research_package import (
    ACTIVE_STATUSES,
    FISCAL_YEARS,
    build_multipurpose_release,
    is_multipurpose_building,
)

DPWH_SOURCE_ID = "dpwh-delivery-snapshot-2026-01-22"


def _budget_centavos(row: dict[str, Any]) -> int:
    value = row.get("budget")
    normalized = Decimal(str(value)) if isinstance(value, float) else value
    return parse_centavos(normalized)


def _classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("infraYear")) in FISCAL_YEARS
        and is_multipurpose_building(row.get("description"))
    ]


def _validated_benchmarks(
    values: list[dict[str, Any]], source_ids: set[str]
) -> list[dict[str, Any]]:
    if not values:
        raise ValueError("at least one opportunity-cost benchmark is required")
    validated = []
    identifiers: set[str] = set()
    for item in values:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError("opportunity-cost benchmark id is missing or duplicated")
        identifiers.add(identifier)
        budget = item.get("budget_centavos")
        target = item.get("physical_target")
        if (
            not isinstance(budget, int)
            or isinstance(budget, bool)
            or budget <= 0
            or not isinstance(target, int)
            or isinstance(target, bool)
            or target <= 0
        ):
            raise ValueError(f"benchmark {identifier} must use positive integer controls")
        if item.get("source_id") not in source_ids:
            raise ValueError(f"benchmark {identifier} references an unknown source")
        if not all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in ("label", "unit")
        ):
            raise ValueError(f"benchmark {identifier} label or unit is missing")
        validated.append(dict(item))
    return validated


def _claim(
    identifier: str,
    statement: str,
    value: int,
    unit: str,
    *,
    source_ids: list[str],
    evidence_state: str = "source_reported",
    limitations: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "value": value,
        "unit": unit,
        "scope": "Conservatively classified DPWH FY2024 to FY2026 delivery records",
        "evidence_state": evidence_state,
        "calculation_id": "mpb-public-value-v1",
        "source_ids": source_ids,
        "limitations": list(limitations),
    }


def _assessment_gates() -> list[dict[str, Any]]:
    return [
        {
            "id": "need",
            "title": "Need and public function",
            "state": "not_in_snapshot",
            "required_evidence": [
                "Named public function and intended users",
                "Catchment population and demand",
                "Nearby equivalent facilities and their utilization",
                "Least-cost option comparison",
            ],
        },
        {
            "id": "location",
            "title": "Location and hazards",
            "state": "not_in_snapshot",
            "required_evidence": [
                "Verified parcel and land rights",
                "Access, utilities, and drainage",
                "Government hazard assessment and ground validation",
            ],
        },
        {
            "id": "design",
            "title": "Design and accessibility",
            "state": "not_in_snapshot",
            "required_evidence": [
                "Floor area, capacity, plans, and specifications",
                "Structural, climate, sanitation, and accessibility review",
                "Design matched to the intended public function",
            ],
        },
        {
            "id": "delivery",
            "title": "Cost and delivery",
            "state": "partial",
            "required_evidence": [
                "Bill of quantities and comparable unit costs",
                "Award, variation, payment, acceptance, and final cost",
                "Utilization and maintenance after completion",
            ],
        },
    ]


def _append_story_sections(
    release: dict[str, Any],
    *,
    all_budget: int,
    active_budget: int,
    comparisons: list[dict[str, Any]],
) -> None:
    new_classrooms = [
        item["equivalent_units"]
        for item in comparisons
        if item["unit"] == "new classrooms"
    ]
    low, high = min(new_classrooms), max(new_classrooms)
    release["story"]["deck"] = (
        "A reproducible count and budget reconciliation, with explicit tests for need, "
        "location, design, cost, and delivery."
    )
    release["story"]["sections"].extend(
        [
            {
                "id": "public-value",
                "section_type": "finding",
                "heading": "The active pipeline carries a large recorded amount",
                "copy": [
                    f"The active pipeline carries {active_budget:,} centavos in recorded budgets.",
                    f"All classified FY2024 to FY2026 records carry {all_budget:,} centavos, including completed work.",
                    "Recorded budgets are not payments, final cost, unique-building counts, or proof of value.",
                ],
                "claim_ids": [
                    "mpb-active-budget",
                    "mpb-all-recorded-budget",
                    "mpb-completed-budget",
                ],
                "source_ids": [DPWH_SOURCE_ID],
                "visual_refs": ["chart_data.budget_reconciliation"],
                "limitation_ids": ["record-count", "budget-meaning"],
                "narration_eligible": True,
            },
            {
                "id": "opportunity-cost",
                "section_type": "finding",
                "heading": "Official education targets provide scale, not a cancellation plan",
                "copy": [
                    f"The same nominal active amount equals roughly {low:,} to {high:,} new classrooms under two official 2026 budget benchmarks.",
                    "The comparison does not make projects interchangeable and is not a cancellation recommendation.",
                ],
                "claim_ids": [
                    "mpb-classroom-equivalent-low",
                    "mpb-classroom-equivalent-high",
                ],
                "source_ids": [
                    item["source_id"]
                    for item in comparisons
                    if item["unit"] == "new classrooms"
                ],
                "visual_refs": ["chart_data.opportunity_cost"],
                "limitation_ids": ["opportunity-cost-boundary"],
                "narration_eligible": True,
            },
            {
                "id": "necessity-gate",
                "section_type": "investigation_lead",
                "heading": "The current snapshot cannot determine whether each project is necessary",
                "copy": [
                    "The snapshot lacks needs assessments, nearby-facility utilization, verified parcels, hazard reports, plans, floor area, bills of quantities, and post-completion use.",
                    "Missing evidence is not evidence that a project is unnecessary or improperly designed.",
                ],
                "claim_ids": ["mpb-necessity-assessment"],
                "source_ids": [DPWH_SOURCE_ID],
                "visual_refs": ["chart_data.assessment_gates"],
                "limitation_ids": [
                    "necessity-boundary",
                    "siting-design-boundary",
                ],
                "narration_eligible": False,
            },
        ]
    )


def build_multipurpose_value_release(
    all_rows: list[dict[str, Any]],
    *,
    source_sha256: str,
    source_modified: str,
    published_at: str,
    benchmark_sources: list[dict[str, Any]],
    classroom_benchmarks: list[dict[str, Any]],
    supersedes: dict[str, Any],
) -> dict[str, Any]:
    """Build version 3 with budget scale, opportunity cost, and evidence gates."""

    release = build_multipurpose_release(
        all_rows,
        source_sha256=source_sha256,
        source_modified=source_modified,
        published_at=published_at,
        version=3,
        supersedes=supersedes,
    )
    source_ids = {item.get("id") for item in benchmark_sources}
    benchmarks = _validated_benchmarks(classroom_benchmarks, source_ids)
    records = _classified_rows(all_rows)
    active = [row for row in records if row.get("status") in ACTIVE_STATUSES]
    completed = [row for row in records if row.get("status") == "Completed"]
    all_budget = sum(_budget_centavos(row) for row in records)
    active_budget = sum(_budget_centavos(row) for row in active)
    completed_budget = sum(_budget_centavos(row) for row in completed)
    comparisons = [
        {
            **item,
            "reference_amount_centavos": active_budget,
            "equivalent_units": active_budget * item["physical_target"]
            // item["budget_centavos"],
            "rounding": "floor",
            "interpretation": "Nominal funding-scale comparison only",
        }
        for item in benchmarks
    ]
    new_classrooms = [
        item["equivalent_units"]
        for item in comparisons
        if item["unit"] == "new classrooms"
    ]
    if not new_classrooms:
        raise ValueError("at least one new-classroom benchmark is required")

    release["metadata"]["methodology_version"] = "mpb-public-value-v1"
    release["sources"].extend(benchmark_sources)
    release["claims"].extend(
        [
            _claim(
                "mpb-all-recorded-budget",
                "All classified FY2024 to FY2026 records carry the recorded budget total stated in this package.",
                all_budget,
                "PHP centavos",
                source_ids=[DPWH_SOURCE_ID],
                limitations=("The total includes completed work and can include separate phases.",),
            ),
            _claim(
                "mpb-completed-budget",
                "Records marked Completed carry the recorded budget total stated in this package.",
                completed_budget,
                "PHP centavos",
                source_ids=[DPWH_SOURCE_ID],
                limitations=("Completed is source-reported and does not establish payment or acceptance.",),
            ),
            _claim(
                "mpb-classroom-equivalent-low",
                "The active recorded amount equals the lower new-classroom equivalent stated in this package under official 2026 benchmarks.",
                min(new_classrooms),
                "new classrooms",
                source_ids=sorted({item["source_id"] for item in comparisons}),
                limitations=("This is a nominal funding-scale comparison, not a project estimate.",),
            ),
            _claim(
                "mpb-classroom-equivalent-high",
                "The active recorded amount equals the higher new-classroom equivalent stated in this package under official 2026 benchmarks.",
                max(new_classrooms),
                "new classrooms",
                source_ids=sorted({item["source_id"] for item in comparisons}),
                limitations=("This is a nominal funding-scale comparison, not a project estimate.",),
            ),
            _claim(
                "mpb-necessity-assessment",
                "The current snapshot cannot determine whether each project is necessary, properly located, or appropriately designed.",
                0,
                "supported project-level necessity determinations",
                source_ids=[DPWH_SOURCE_ID],
                evidence_state="not_supported",
                limitations=("The required planning and design evidence is outside the snapshot.",),
            ),
        ]
    )
    release["findings"].append(
        {
            "id": "budget-scale",
            "title": "The active pipeline carries a large recorded budget",
            "result": "Budget scale is established, while necessity and value remain unproven.",
            "claim_ids": ["mpb-active-budget", "mpb-all-recorded-budget"],
            "evidence_state": "source_reported",
        }
    )
    release["investigations"].extend(
        [
            {
                "question": "Is every active multipurpose-building project necessary?",
                "result": "Not established by the current snapshot.",
                "state": "evidence_gap",
                "calculation_id": "mpb-public-value-v1",
            },
            {
                "question": "Is each location and design appropriate for its intended function?",
                "result": "Not established without verified sites, hazards, plans, specifications, and utilization evidence.",
                "state": "evidence_gap",
                "calculation_id": "mpb-public-value-v1",
            },
        ]
    )
    release["chart_data"].update(
        {
            "budget_reconciliation": {
                "all_records": len(records),
                "all_recorded_budget_centavos": all_budget,
                "active_records": len(active),
                "active_recorded_budget_centavos": active_budget,
                "completed_records": len(completed),
                "completed_recorded_budget_centavos": completed_budget,
            },
            "opportunity_cost": comparisons,
            "assessment_gates": _assessment_gates(),
        }
    )
    release["limitations"].extend(
        [
            {
                "id": "opportunity-cost-boundary",
                "text": "Classroom equivalents compare nominal funding scale only; different land, design, location, procurement, and operating needs make projects non-interchangeable.",
            },
            {
                "id": "necessity-boundary",
                "text": "Missing needs evidence in this snapshot does not prove that a project is unnecessary.",
            },
            {
                "id": "siting-design-boundary",
                "text": "Coordinates and titles do not establish safe siting, compliant design, construction quality, accessibility, or fitness for purpose.",
            },
        ]
    )
    for item in release["project_examples"]["largest_active_recorded_budgets"]:
        item["necessity_state"] = "not_assessable_from_snapshot"
        item["siting_design_state"] = "not_assessable_from_snapshot"
    _append_story_sections(
        release,
        all_budget=all_budget,
        active_budget=active_budget,
        comparisons=comparisons,
    )
    release["editorial_package"] = build_consumption_index(
        release["metadata"], release["sources"]
    )
    return release
