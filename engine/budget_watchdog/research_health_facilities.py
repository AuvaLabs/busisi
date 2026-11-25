"""Question-led research release for FY2027 health-facility list changes."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from engine.budget_watchdog.research_editor import build_consumption_index
from engine.budget_watchdog.research_stage_changes import OVERVIEW_SOURCE_ID
from engine.budget_watchdog.stage_changes import StageChange

HEALTH_DATASET = "hfep"
METHODOLOGY_VERSION = "fy2027-health-facility-changes-v1"
DOCUMENT_KEYS = (
    "nep2027-hfep",
    "hb10858-2r-vol-ib",
    "hb10858-3r-vol-ib",
)
CHANGE_ORDER = ("house_only", "nep_only", "increased", "decreased", "unchanged")


def _format_centavos(value: int) -> str:
    whole, fraction = divmod(abs(value), 100)
    return f"{whole:,}.{fraction:02d}"


def _source_ids() -> list[str]:
    return [OVERVIEW_SOURCE_ID, *(f"document-{key}" for key in DOCUMENT_KEYS)]


def _claim(
    claim_id: str,
    statement: str,
    value: int,
    unit: str,
    *,
    evidence_state: str = "verified",
    limitations: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "statement": statement,
        "value": value,
        "unit": unit,
        "scope": "FY2027 Health Facilities Enhancement Program, NEP versus House list",
        "evidence_state": evidence_state,
        "calculation_id": METHODOLOGY_VERSION,
        "source_ids": _source_ids(),
        "limitations": list(limitations),
    }


def _sources(overview: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    retrieved = str(manifest["retrieved_at"])[:10]
    sources = [
        {
            "id": OVERVIEW_SOURCE_ID,
            "publisher": "BetterGov PH",
            "access_provider": "BetterGov",
            "source_kind": "curated_official_extract",
            "scope": "FY2027 health-facility comparison rows and control totals",
            "retrieved_at": retrieved,
            "source_url": "https://budget.bettergov.ph/api/v1/hgab/2027/datasets/hfep",
            "origin_url": overview.get("meta", {}).get("source_repo"),
            "sha256": manifest["overview_sha256"],
        }
    ]
    source_documents = {item["key"]: item for item in overview.get("data", {}).get("documents", [])}
    archived_documents = {item["key"]: item for item in manifest.get("documents", [])}
    for key in DOCUMENT_KEYS:
        document = source_documents.get(key)
        archived = archived_documents.get(key)
        if not isinstance(document, dict) or not isinstance(archived, dict):
            raise ValueError(f"health-facility source document is unavailable: {key}")
        item = {
            "id": f"document-{key}",
            "publisher": (
                "Department of Budget and Management"
                if document.get("stage") == "nep"
                else "House of Representatives"
            ),
            "access_provider": "BetterGov",
            "source_kind": "curated_official_extract",
            "scope": document["title"],
            "retrieved_at": retrieved,
            "source_url": archived.get("mirror_url") or document["pdf_url"],
            "sha256": archived["sha256"],
        }
        if document.get("source_url"):
            item["origin_url"] = document["source_url"]
        sources.append(item)
    return sources


def _limitations() -> list[dict[str, str]]:
    return [
        {
            "id": "document-stage-only",
            "text": "The result compares the FY2027 NEP list with the House second-reading list. It is not the enacted budget.",
        },
        {
            "id": "rows-not-facilities",
            "text": "A facility can have separate construction, equipment, and vehicle rows. Row counts are not unique-facility counts.",
        },
        {
            "id": "matching-boundary",
            "text": "A House-only or NEP-only row can reflect a new line, removal, renaming, regrouping, or unmatched text.",
        },
        {
            "id": "source-control-gap",
            "text": "The source reports that the NEP line sum is PHP 140,000 below its published annex control. This release uses the reconciled line sum.",
        },
        {
            "id": "amounts-not-spending",
            "text": "The amounts are proposed budget authority, not allotment releases, obligations, payments, final costs, or completed facilities.",
        },
        {
            "id": "regional-boundary",
            "text": "Recorded regional labels show document distribution. They do not measure population need, facility condition, or health outcomes.",
        },
        {
            "id": "missing-later-stages",
            "text": "Senate, bicameral, enacted GAA, release, procurement, payment, completion, and audit stages are not established here.",
        },
        {
            "id": "source-extraction",
            "text": "BetterGov performed the row extraction and initial matching. Busisi verifies saved bytes, schemas, row counts, arithmetic, and controls.",
        },
    ]


def _change_chart(records: list[StageChange]) -> dict[str, dict[str, int]]:
    chart: dict[str, dict[str, int]] = {}
    for change_type in CHANGE_ORDER:
        selected = [record for record in records if record.change_type == change_type]
        chart[change_type] = {
            "count": len(selected),
            "nep_centavos": sum(record.nep_centavos for record in selected),
            "house_centavos": sum(record.house_centavos for record in selected),
            "net_difference_centavos": sum(record.difference_centavos for record in selected),
        }
    return chart


def _region_chart(records: list[StageChange]) -> list[dict[str, Any]]:
    grouped: dict[str, list[StageChange]] = defaultdict(list)
    for record in records:
        grouped[record.region.strip() or "Not stated"].append(record)
    rows = []
    for region, selected in grouped.items():
        rows.append(
            {
                "region": region,
                "records": len(selected),
                "nep_centavos": sum(record.nep_centavos for record in selected),
                "house_centavos": sum(record.house_centavos for record in selected),
                "net_difference_centavos": sum(record.difference_centavos for record in selected),
                "change_counts": dict(
                    sorted(Counter(record.change_type for record in selected).items())
                ),
            }
        )
    return sorted(
        rows,
        key=lambda item: (-abs(item["net_difference_centavos"]), item["region"]),
    )


def _examples(records: list[StageChange]) -> dict[str, list[dict[str, Any]]]:
    selected = sorted(
        records,
        key=lambda record: (-abs(record.difference_centavos), record.record_id),
    )[:20]
    return {
        "largest_absolute_changes": [
            {
                "record_id": record.record_id,
                "title": record.title,
                "region": record.region or "Not stated",
                "office": record.office or "Not stated",
                "change_type": record.change_type,
                "nep_centavos": record.nep_centavos,
                "house_centavos": record.house_centavos,
                "difference_centavos": record.difference_centavos,
                "reader_url": f"/records/change/{quote(record.record_id, safe='')}/",
                "source_url": record.source_url,
                "evidence_state": "source_reported",
            }
            for record in selected
        ]
    }


def _story(
    metadata: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    largest_region: dict[str, Any],
) -> dict[str, Any]:
    sources = _source_ids()
    return {
        "schema_version": "1.1",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "editorial_status": "ready",
        "editorial_format": "question-led-v1",
        "headline": metadata["headline"],
        "deck": "A checked comparison of the FY2027 health-facility lists, where their rows differ, and what later records are still needed.",
        "audience": "Filipino public",
        "language": "en-PH",
        "canonical_url": metadata["canonical_url"],
        "data_cutoff": metadata["data_cutoff"],
        "source_ids": sources,
        "method_summary": {
            "question_definition": "A change is a difference between the saved FY2027 NEP health-facility list and the House second-reading list after source matching.",
            "reference_years": ["FY2027"],
            "units": ["project-list rows", "PHP centavos"],
            "denominators": [],
        },
        "next_checks": [
            {
                "office": "Senate of the Philippines",
                "record": "FY2027 Senate health-facility project schedule",
                "question": "Which House-stage changes remain in the Senate-approved documents?",
            },
            {
                "office": "Congress of the Philippines",
                "record": "FY2027 bicameral health-facility project schedule",
                "question": "Which document-stage differences survived the bicameral conference?",
            },
            {
                "office": "Department of Budget and Management",
                "record": "FY2027 enacted GAA health-facility schedule and allotment releases",
                "question": "Which enacted health-facility items later received allotment releases?",
            },
        ],
        "sections": [
            {
                "id": "short-answer",
                "editorial_role": "short_answer",
                "section_type": "finding",
                "heading": "The short answer",
                "copy": [
                    claims["health-net-movement"]["statement"],
                    "This is a difference between two budget documents, not proof of a final cut, release, payment, or completed facility.",
                ],
                "claim_ids": [
                    "health-nep-total",
                    "health-house-total",
                    "health-net-movement",
                ],
                "source_ids": sources,
                "visual_refs": ["chart_data.totals"],
                "limitation_ids": ["document-stage-only", "amounts-not-spending"],
                "narration_eligible": True,
            },
            {
                "id": "row-movements",
                "editorial_role": "finding",
                "section_type": "finding",
                "heading": "The difference comes from five kinds of row movement",
                "copy": [
                    claims["health-house-only"]["statement"],
                    claims["health-nep-only"]["statement"],
                    claims["health-amount-changes"]["statement"],
                    claims["health-unchanged"]["statement"],
                ],
                "claim_ids": [
                    "health-house-only",
                    "health-nep-only",
                    "health-amount-changes",
                    "health-unchanged",
                ],
                "source_ids": sources,
                "visual_refs": ["chart_data.change_types"],
                "limitation_ids": ["matching-boundary", "rows-not-facilities"],
                "narration_eligible": True,
            },
            {
                "id": "regional-movement",
                "editorial_role": "comparison",
                "section_type": "finding",
                "heading": "Regional labels do not all move in the same direction",
                "copy": [claims["health-largest-regional-movement"]["statement"]],
                "claim_ids": ["health-largest-regional-movement"],
                "source_ids": sources,
                "visual_refs": ["chart_data.regions"],
                "limitation_ids": ["regional-boundary"],
                "narration_eligible": True,
            },
            {
                "id": "limits",
                "editorial_role": "limits",
                "section_type": "finding",
                "heading": "What this does not show",
                "copy": [
                    "The records do not establish who requested a change, whether it was justified, whether it survived later budget stages, or whether money was released or spent.",
                    "A row that appears on only one list is a document-matching result, not proof of an insertion, deletion, wrongdoing, or a unique facility.",
                ],
                "claim_ids": ["health-total-records"],
                "source_ids": sources,
                "visual_refs": [],
                "limitation_ids": [
                    "document-stage-only",
                    "rows-not-facilities",
                    "matching-boundary",
                    "source-control-gap",
                    "missing-later-stages",
                ],
                "narration_eligible": True,
            },
        ],
    }


def build_health_facility_release(
    records: Iterable[StageChange],
    *,
    overview: dict[str, Any],
    snapshot_manifest: dict[str, Any],
    published_at: str,
) -> dict[str, Any]:
    """Build one authenticated health-facility article from reconciled rows."""

    rows = [record for record in records if record.dataset == HEALTH_DATASET]
    if not rows:
        raise ValueError("stage-change snapshot contains no health-facility rows")
    if any(record.review_status == "quarantine" or record.held for record in rows):
        raise ValueError("stage-change snapshot contains held health-facility rows")

    counts = Counter(record.change_type for record in rows)
    unknown_changes = set(counts) - set(CHANGE_ORDER)
    if unknown_changes:
        raise ValueError(f"health-facility rows use unsupported change types: {unknown_changes}")
    nep_total = sum(record.nep_centavos for record in rows)
    house_total = sum(record.house_centavos for record in rows)
    net = house_total - nep_total
    regions = _region_chart(rows)
    largest_region = regions[0]
    built_at = str(overview["meta"]["built_at"])[:10]
    checked_at = str(snapshot_manifest["retrieved_at"])[:10]
    metadata = {
        "schema_version": "1.1",
        "story_id": "fy2027-health-facility-changes-2026",
        "slug": "fy2027-health-facility-changes",
        "version": 1,
        "status": "published",
        "editorial_ready": True,
        "headline": "What changed in the FY2027 health-facility project list?",
        "canonical_url": "https://busisi.org/research/fy2027-health-facility-changes/",
        "published_at": published_at,
        "data_cutoff": built_at,
        "source_checked_at": checked_at,
        "max_source_age_days": 7,
        "methodology_version": METHODOLOGY_VERSION,
        "source_artifact_sha256": snapshot_manifest["overview_sha256"],
        "source_commit": snapshot_manifest["source_commit"],
        "supersedes": None,
    }
    direction = "lower" if net < 0 else "higher"
    claims = [
        _claim(
            "health-total-records",
            f"Busisi validated {len(rows):,} rows in the FY2027 health-facility comparison.",
            len(rows),
            "project-list rows",
        ),
        _claim(
            "health-nep-total",
            f"The reconciled NEP health-facility list totals PHP {_format_centavos(nep_total)}.",
            nep_total,
            "PHP centavos",
        ),
        _claim(
            "health-house-total",
            f"The reconciled House health-facility list totals PHP {_format_centavos(house_total)}.",
            house_total,
            "PHP centavos",
        ),
        _claim(
            "health-net-movement",
            f"The recorded House-list total is PHP {_format_centavos(net)} {direction} than the reconciled NEP line total.",
            net,
            "PHP centavos",
            limitations=("This is a document-stage difference, not a final budget cut.",),
        ),
        _claim(
            "health-house-only",
            f"{counts['house_only']:,} rows appear only in the compared House list.",
            counts["house_only"],
            "project-list rows",
            evidence_state="source_reported",
            limitations=("House-only does not establish insertion or authorship.",),
        ),
        _claim(
            "health-nep-only",
            f"{counts['nep_only']:,} rows appear only in the compared NEP list.",
            counts["nep_only"],
            "project-list rows",
            evidence_state="source_reported",
        ),
        _claim(
            "health-amount-changes",
            f"{counts['increased']:,} matched rows increased and {counts['decreased']:,} decreased in the House list.",
            counts["increased"] + counts["decreased"],
            "project-list rows",
            evidence_state="source_reported",
        ),
        _claim(
            "health-unchanged",
            f"{counts['unchanged']:,} matched rows carry the same amount in both lists.",
            counts["unchanged"],
            "project-list rows",
            evidence_state="source_reported",
        ),
        _claim(
            "health-largest-regional-movement",
            f"Among recorded regional labels, {largest_region['region']} has the largest absolute net document movement at PHP {_format_centavos(largest_region['net_difference_centavos'])}.",
            largest_region["net_difference_centavos"],
            "PHP centavos",
            evidence_state="source_reported",
            limitations=("Regional document movement is not a measure of health need.",),
        ),
    ]
    source_list = _sources(overview, snapshot_manifest)
    claim_index = {item["id"]: item for item in claims}
    release = {
        "metadata": metadata,
        "claims": claims,
        "findings": [
            {
                "id": "net-document-change",
                "title": "The compared House-list total is lower",
                "result": claim_index["health-net-movement"]["statement"],
                "claim_ids": [
                    "health-nep-total",
                    "health-house-total",
                    "health-net-movement",
                ],
                "evidence_state": "verified",
            },
            {
                "id": "separate-row-movements",
                "title": "The lists differ through several row movements",
                "result": claim_index["health-amount-changes"]["statement"],
                "claim_ids": [
                    "health-house-only",
                    "health-nep-only",
                    "health-amount-changes",
                    "health-unchanged",
                ],
                "evidence_state": "source_reported",
            },
        ],
        "investigations": [
            {
                "question": "What changed between the FY2027 NEP and House health-facility lists?",
                "result": claim_index["health-net-movement"]["statement"],
                "state": "partial",
                "calculation_id": METHODOLOGY_VERSION,
            },
            {
                "question": "Did the document-stage difference become a final cut, release, or payment?",
                "result": "Not established. Later official stages are outside this release.",
                "state": "evidence_gap",
                "calculation_id": METHODOLOGY_VERSION,
            },
        ],
        "chart_data": {
            "totals": {
                "records": len(rows),
                "nep_centavos": nep_total,
                "house_centavos": house_total,
                "net_difference_centavos": net,
            },
            "change_types": _change_chart(rows),
            "regions": regions,
        },
        "project_examples": _examples(rows),
        "sources": source_list,
        "limitations": _limitations(),
    }
    release["story"] = _story(metadata, claim_index, largest_region)
    release["editorial_package"] = build_consumption_index(metadata, source_list)
    return release
