"""Research release for concentration in FY2027 project-list changes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from engine.budget_watchdog.research_editor import build_consumption_index
from engine.budget_watchdog.research_stage_changes import build_stage_change_release
from engine.budget_watchdog.stage_changes import StageChange

SOURCE_ID = "bettergov-hgab-overview-2027"
MATCHED_CHANGE_TYPES = frozenset({"increased", "decreased"})


def _share_basis_points(part: int, whole: int) -> int:
    return 0 if whole == 0 else (part * 10_000 + whole // 2) // whole


def _dimension_rows(
    records: list[StageChange], field: str, *, limit: int | None = None
) -> list[dict[str, Any]]:
    groups: dict[str, list[StageChange]] = defaultdict(list)
    for record in records:
        label = str(getattr(record, field)).strip() or "Not stated"
        groups[label].append(record)
    total_house_only = sum(record.change_type == "house_only" for record in records)
    values: list[dict[str, Any]] = []
    for label, selected in groups.items():
        house_only = [record for record in selected if record.change_type == "house_only"]
        matched = [record for record in selected if record.change_type in MATCHED_CHANGE_TYPES]
        values.append(
            {
                "label": label,
                "records": len(selected),
                "changed_records": sum(record.change_type != "unchanged" for record in selected),
                "house_only": len(house_only),
                "publishable_house_only": sum(
                    record.review_status != "quarantine" for record in house_only
                ),
                "house_only_share_basis_points": _share_basis_points(
                    len(house_only), total_house_only
                ),
                "house_only_centavos": sum(record.house_centavos for record in house_only),
                "matched_change_records": len(matched),
                "matched_absolute_movement_centavos": sum(
                    abs(record.difference_centavos) for record in matched
                ),
                "matched_net_movement_centavos": sum(
                    record.difference_centavos for record in matched
                ),
                "quarantined": sum(record.review_status == "quarantine" for record in selected),
            }
        )
    ordered = sorted(
        values,
        key=lambda item: (-int(item["house_only"]), str(item["label"])),
    )
    return ordered if limit is None else ordered[:limit]


def _claim(
    identifier: str,
    statement: str,
    value: int,
    unit: str,
    *,
    evidence_state: str = "verified",
    limitations: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": identifier,
        "statement": statement,
        "value": value,
        "unit": unit,
        "scope": "FY2027 NEP-to-House comparison for four acquired project lists",
        "evidence_state": evidence_state,
        "calculation_id": "fy2027-change-concentration-v1",
        "source_ids": [SOURCE_ID],
        "limitations": list(limitations),
    }


def _examples(records: list[StageChange]) -> dict[str, list[dict[str, Any]]]:
    matched = sorted(
        (
            record
            for record in records
            if record.change_type in MATCHED_CHANGE_TYPES and record.review_status != "quarantine"
        ),
        key=lambda record: (-abs(record.difference_centavos), record.record_id),
    )[:20]
    house_only = sorted(
        (
            record
            for record in records
            if record.change_type == "house_only" and record.review_status != "quarantine"
        ),
        key=lambda record: (-record.house_centavos, record.record_id),
    )[:20]

    def item(record: StageChange) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "title": record.title,
            "dataset": record.dataset,
            "region": record.region or "Not stated",
            "office": record.office or "Not stated",
            "program": record.program or "Not stated",
            "change_type": record.change_type,
            "nep_centavos": record.nep_centavos,
            "house_centavos": record.house_centavos,
            "difference_centavos": record.difference_centavos,
            "reader_url": f"/records/change/{quote(record.record_id, safe='')}/",
            "source_url": record.source_url,
            "evidence_state": "source_reported",
        }

    return {
        "largest_matched_amount_changes": [item(record) for record in matched],
        "largest_publishable_house_only_amounts": [item(record) for record in house_only],
    }


def _limitations() -> list[dict[str, str]]:
    return [
        {
            "id": "stage-scope",
            "text": "The comparison covers four project-level lists, not the entire national budget.",
        },
        {
            "id": "overlapping-dimensions",
            "text": "Program, region, office, and dataset rankings describe overlapping dimensions and must not be added together.",
        },
        {
            "id": "recorded-labels",
            "text": "Regions and offices are reproduced from source labels and are not determinations of political sponsorship or responsibility.",
        },
        {
            "id": "not-an-insertion-finding",
            "text": "A House-only row can reflect naming, grouping, or scope differences and is not proof of an insertion or wrongdoing.",
        },
        {
            "id": "concentration-boundary",
            "text": "A concentration is a review priority, not evidence that an allocation is unfair, improper, or politically motivated.",
        },
        {
            "id": "quarantine-boundary",
            "text": "Ambiguous and scope-review rows remain quarantined and are not promoted as findings.",
        },
        {
            "id": "missing-stages",
            "text": "The release does not establish Senate, bicameral, enacted GAA, release, payment, implementation, or outcome stages.",
        },
        {
            "id": "amounts-not-spending",
            "text": "Document amounts are proposed authority, not releases, payments, final costs, or outcomes.",
        },
    ]


def _story(metadata: dict[str, Any], claims: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "editorial_status": "ready",
        "headline": metadata["headline"],
        "deck": "Where FY2027 project-list differences cluster, and what those rankings cannot prove.",
        "audience": "Filipino public",
        "language": "en-PH",
        "canonical_url": metadata["canonical_url"],
        "data_cutoff": metadata["data_cutoff"],
        "source_ids": [SOURCE_ID],
        "sections": [
            {
                "id": "direct-answer",
                "section_type": "finding",
                "heading": "Most rows did not change, while differences cluster unevenly",
                "copy": [
                    claims["concentration-total-rows"]["statement"],
                    claims["concentration-changed-rows"]["statement"],
                ],
                "claim_ids": ["concentration-total-rows", "concentration-changed-rows"],
                "source_ids": [SOURCE_ID],
                "visual_refs": ["chart_data.datasets"],
                "limitation_ids": ["stage-scope", "amounts-not-spending"],
                "narration_eligible": True,
            },
            {
                "id": "concentration-leads",
                "section_type": "investigation_lead",
                "heading": "The largest clusters are priorities for document review",
                "copy": [
                    claims["concentration-top-region"]["statement"],
                    claims["concentration-top-program"]["statement"],
                ],
                "claim_ids": ["concentration-top-region", "concentration-top-program"],
                "source_ids": [SOURCE_ID],
                "visual_refs": ["chart_data.regions", "chart_data.programs"],
                "limitation_ids": [
                    "concentration-boundary",
                    "not-an-insertion-finding",
                    "recorded-labels",
                ],
                "narration_eligible": False,
            },
            {
                "id": "quarantine",
                "section_type": "finding",
                "heading": "Ambiguous rows remain outside the rankings used as leads",
                "copy": [claims["concentration-quarantined"]["statement"]],
                "claim_ids": ["concentration-quarantined"],
                "source_ids": [SOURCE_ID],
                "visual_refs": ["chart_data.review_gate"],
                "limitation_ids": ["quarantine-boundary"],
                "narration_eligible": True,
            },
            {
                "id": "next-evidence",
                "section_type": "finding",
                "heading": "Later budget and implementation stages remain necessary",
                "copy": [
                    "Concentration can prioritize document review but cannot establish who caused a change or whether it survived later stages."
                ],
                "claim_ids": ["concentration-total-rows"],
                "source_ids": [SOURCE_ID],
                "visual_refs": ["project_examples.largest_matched_amount_changes"],
                "limitation_ids": ["missing-stages", "concentration-boundary"],
                "narration_eligible": True,
            },
        ],
    }


def build_change_concentration_release(
    records: Iterable[StageChange],
    *,
    overview: dict[str, Any],
    snapshot_manifest: dict[str, Any],
    published_at: str,
) -> dict[str, Any]:
    """Build a bounded concentration analysis from authenticated stage rows."""

    rows = list(records)
    base = build_stage_change_release(
        rows,
        overview=overview,
        snapshot_manifest=snapshot_manifest,
        published_at=published_at,
    )
    changed = [record for record in rows if record.change_type != "unchanged"]
    house_only = [record for record in rows if record.change_type == "house_only"]
    quarantined = sum(record.review_status == "quarantine" for record in rows)
    regions = _dimension_rows(rows, "region")
    programs = _dimension_rows(rows, "program")
    offices = _dimension_rows(rows, "office", limit=50)
    datasets = _dimension_rows(rows, "dataset")
    top_region = regions[0]
    top_program = programs[0]
    metadata = {
        **base["metadata"],
        "story_id": "fy2027-change-concentration-2026",
        "slug": "fy2027-change-concentration",
        "version": 1,
        "headline": "Where are FY2027 House-stage project-list changes concentrated?",
        "canonical_url": "https://busisi.org/research/fy2027-change-concentration/",
        "methodology_version": "fy2027-change-concentration-v1",
        "supersedes": None,
    }
    claims = [
        _claim(
            "concentration-total-rows",
            f"Busisi compared {len(rows):,} rows across four FY2027 project lists.",
            len(rows),
            "records",
        ),
        _claim(
            "concentration-changed-rows",
            f"{len(changed):,} rows are not classified as unchanged in the source comparison.",
            len(changed),
            "records",
        ),
        _claim(
            "concentration-house-only",
            f"{len(house_only):,} rows are classified as House-list only.",
            len(house_only),
            "records",
            evidence_state="source_reported",
            limitations=("House-only is a comparison label, not an insertion finding.",),
        ),
        _claim(
            "concentration-top-region",
            f"{top_region['label']} has the largest House-only row count in the scoped regional labels at {top_region['house_only']:,}.",
            top_region["house_only"],
            "review candidates",
            evidence_state="review_candidate",
            limitations=("The rank does not establish unfairness, sponsorship, or wrongdoing.",),
        ),
        _claim(
            "concentration-top-program",
            f"{top_program['label']} has the largest House-only row count among recorded program labels at {top_program['house_only']:,}.",
            top_program["house_only"],
            "review candidates",
            evidence_state="review_candidate",
            limitations=("Program concentration is a review lead, not a finding of impropriety.",),
        ),
        _claim(
            "concentration-quarantined",
            f"{quarantined:,} ambiguous or scope-review rows remain quarantined.",
            quarantined,
            "records",
        ),
    ]
    claim_index = {item["id"]: item for item in claims}
    release = {
        "metadata": metadata,
        "claims": claims,
        "findings": [
            {
                "id": "changed-row-count",
                "title": "Document differences affect a minority of compared rows",
                "result": claim_index["concentration-changed-rows"]["statement"],
                "claim_ids": ["concentration-total-rows", "concentration-changed-rows"],
                "evidence_state": "verified",
            },
            {
                "id": "quarantine-preserved",
                "title": "Ambiguous rows remain held back",
                "result": claim_index["concentration-quarantined"]["statement"],
                "claim_ids": ["concentration-quarantined"],
                "evidence_state": "verified",
            },
        ],
        "investigations": [
            {
                "question": "Where do House-only rows cluster in the scoped source labels?",
                "result": "Ranked by recorded program, region, office, and dataset labels.",
                "state": "partial",
                "calculation_id": "fy2027-change-concentration-v1",
            },
            {
                "question": "Does a cluster prove an insertion or improper allocation?",
                "result": "No. It identifies a bounded set for document review.",
                "state": "evidence_gap",
                "calculation_id": "fy2027-change-concentration-v1",
            },
            {
                "question": "Did the changes survive later budget and spending stages?",
                "result": "Not established by this NEP-to-House release.",
                "state": "evidence_gap",
                "calculation_id": "fy2027-change-concentration-v1",
            },
        ],
        "chart_data": {
            "regions": regions,
            "programs": programs,
            "offices": offices,
            "datasets": datasets,
            "review_gate": {
                "total_records": len(rows),
                "changed_records": len(changed),
                "house_only": len(house_only),
                "quarantined": quarantined,
            },
        },
        "project_examples": _examples(rows),
        "sources": base["sources"],
        "limitations": _limitations(),
    }
    release["story"] = _story(metadata, claim_index)
    release["editorial_package"] = build_consumption_index(metadata, release["sources"])
    return release
