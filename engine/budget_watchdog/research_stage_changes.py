"""Evidence-led research release for the FY2027 NEP-to-House project lists."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from engine.budget_watchdog.research_editor import build_consumption_index
from engine.budget_watchdog.stage_changes import (
    StageChange,
    parse_hgab_page,
    reconcile_hgab_dataset,
)

OVERVIEW_SOURCE_ID = "bettergov-hgab-overview-2027"
DATASET_LABELS = {
    "dpwh": "DPWH national infrastructure",
    "fmr": "Farm-to-market roads",
    "hfep": "Health facilities",
    "nia": "Irrigation",
}
CHANGE_ORDER = (
    "house_only",
    "nep_only",
    "increased",
    "decreased",
    "unchanged",
    "scope_review",
)


def _overview_controls(overview: dict[str, Any]) -> dict[str, dict[str, int]]:
    controls = {}
    for dataset in overview.get("data", {}).get("datasets", []):
        groups = dataset["bridge"]["groups"]
        house_stage = dataset["house_stage"]
        controls[dataset["key"]] = {
            "count": sum(int(group["rows"]) for group in groups.values()),
            "nep": int(dataset["totals"]["nep_php"]) * 100,
            "house": int(dataset["totals"][f"{house_stage}_php"]) * 100,
            "quarantine": int(dataset["unconfirmed_rows"])
            + int(groups["scope_review"]["rows"]),
        }
    if not controls:
        raise ValueError("stage-change overview has no dataset controls")
    return controls


def _verify_documents(snapshot_dir: Path, manifest: dict[str, Any]) -> None:
    for document in manifest.get("documents", []):
        path = snapshot_dir / "documents" / f"{document['key']}.pdf"
        if not path.is_file():
            raise ValueError(f"archived stage-change document is missing: {document['key']}")
        payload = path.read_bytes()
        if len(payload) != document["byte_size"] or hashlib.sha256(payload).hexdigest() != (
            document["sha256"]
        ):
            raise ValueError(f"archived stage-change document failed authentication: {document['key']}")


def load_stage_change_snapshot(
    snapshot_dir: Path,
) -> tuple[list[StageChange], dict[str, Any], dict[str, Any]]:
    """Load and reconcile every archived page and source document."""

    manifest = json.loads((snapshot_dir / "snapshot-manifest.json").read_text())
    overview_bytes = (snapshot_dir / "overview.json").read_bytes()
    if hashlib.sha256(overview_bytes).hexdigest() != manifest.get("overview_sha256"):
        raise ValueError("stage-change overview failed authentication")
    overview = json.loads(overview_bytes)
    records: list[StageChange] = []
    for page in manifest.get("pages", []):
        payload = (snapshot_dir / page["path"]).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != page["sha256"]:
            raise ValueError(f"stage-change page failed authentication: {page['path']}")
        parsed = parse_hgab_page(payload, artifact_sha256=digest)
        if len(parsed.records) != page["record_count"]:
            raise ValueError(f"stage-change page count changed: {page['path']}")
        records.extend(parsed.records)
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("stage-change snapshot contains duplicate record identifiers")
    for dataset, expected in _overview_controls(overview).items():
        selected = tuple(record for record in records if record.dataset == dataset)
        reconcile_hgab_dataset(
            selected,
            expected_count=expected["count"],
            expected_nep_centavos=expected["nep"],
            expected_house_centavos=expected["house"],
            expected_quarantine_count=expected["quarantine"],
        )
    if overview.get("meta", {}).get("source_commit") != manifest.get("source_commit"):
        raise ValueError("stage-change source commit changed between archived controls")
    _verify_documents(snapshot_dir, manifest)
    return records, overview, manifest


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
        "scope": "FY2027 NEP-to-House project-list comparison for four acquired programs",
        "evidence_state": evidence_state,
        "calculation_id": "fy2027-stage-change-research-v1",
        "source_ids": [OVERVIEW_SOURCE_ID],
        "limitations": list(limitations),
    }


def _format_centavos(value: int) -> str:
    whole, fraction = divmod(abs(value), 100)
    return f"{whole:,}.{fraction:02d}"


def _limitations() -> list[dict[str, str]]:
    return [
        {
            "id": "stage-scope",
            "text": "The comparison covers four project-level lists, not the entire national budget.",
        },
        {
            "id": "matching-boundary",
            "text": "A House-only or NEP-only row can reflect renaming, regrouping, scope changes, or unmatched text.",
        },
        {
            "id": "not-an-insertion-finding",
            "text": "A House-only row is a documentary review lead, not proof of an insertion, authorship, motive, or wrongdoing.",
        },
        {
            "id": "quarantine-boundary",
            "text": "Held and scope-review rows remain quarantined and are not promoted as findings.",
        },
        {
            "id": "missing-stages",
            "text": "The release does not yet compare Senate, bicameral, enacted GAA, release, procurement, payment, or implementation stages.",
        },
        {
            "id": "source-extraction",
            "text": "BetterGov performed the row extraction and initial comparison; Busisi validates schemas, hashes, arithmetic, and control totals.",
        },
        {
            "id": "missing-original-links",
            "text": "Three NEP annex extracts lack original-source URLs in the source manifest, although their archived bytes and hashes are retained.",
        },
        {
            "id": "amounts-not-spending",
            "text": "Document amounts are proposed authority, not releases, obligations, payments, final costs, or outcomes.",
        },
    ]


def _sources(overview: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    retrieved = str(manifest["retrieved_at"])[:10]
    sources = [
        {
            "id": OVERVIEW_SOURCE_ID,
            "publisher": "BetterGov PH",
            "access_provider": "BetterGov",
            "source_kind": "curated_official_extract",
            "scope": "FY2027 NEP-to-House comparison overview and control totals",
            "retrieved_at": retrieved,
            "source_url": "https://budget.bettergov.ph/api/v1/hgab/2027",
            "origin_url": overview.get("meta", {}).get("source_repo"),
            "sha256": manifest["overview_sha256"],
        }
    ]
    archived = {item["key"]: item for item in manifest.get("documents", [])}
    for document in overview.get("data", {}).get("documents", []):
        evidence = archived.get(document["key"], document)
        item = {
            "id": f"document-{document['key']}",
            "publisher": (
                "Department of Budget and Management"
                if document.get("stage") == "nep"
                else "House of Representatives"
            ),
            "access_provider": "BetterGov",
            "source_kind": "curated_official_extract",
            "scope": document["title"],
            "retrieved_at": retrieved,
            "source_url": evidence.get("mirror_url") or document["pdf_url"],
            "sha256": evidence["sha256"],
        }
        if document.get("source_url"):
            item["origin_url"] = document["source_url"]
        sources.append(item)
    return sources


def _change_chart(records: list[StageChange]) -> dict[str, dict[str, int]]:
    chart = {}
    for change_type in CHANGE_ORDER:
        selected = [record for record in records if record.change_type == change_type]
        chart[change_type] = {
            "count": len(selected),
            "nep_centavos": sum(record.nep_centavos for record in selected),
            "house_centavos": sum(record.house_centavos for record in selected),
            "net_difference_centavos": sum(record.difference_centavos for record in selected),
            "quarantined": sum(record.review_status == "quarantine" for record in selected),
        }
    return chart


def _dataset_chart(records: list[StageChange]) -> list[dict[str, Any]]:
    groups: dict[str, list[StageChange]] = defaultdict(list)
    for record in records:
        groups[record.dataset].append(record)
    result = []
    for dataset in sorted(groups):
        selected = groups[dataset]
        result.append(
            {
                "dataset": dataset,
                "label": DATASET_LABELS.get(dataset, dataset.upper()),
                "records": len(selected),
                "nep_centavos": sum(record.nep_centavos for record in selected),
                "house_centavos": sum(record.house_centavos for record in selected),
                "net_difference_centavos": sum(
                    record.difference_centavos for record in selected
                ),
                "quarantined": sum(
                    record.review_status == "quarantine" for record in selected
                ),
                "change_counts": dict(
                    sorted(Counter(record.change_type for record in selected).items())
                ),
            }
        )
    return result


def _region_chart(records: list[StageChange]) -> list[dict[str, Any]]:
    groups: dict[str, list[StageChange]] = defaultdict(list)
    for record in records:
        label = record.region.strip() or "Not stated"
        groups[label].append(record)
    rows = []
    for region, selected in groups.items():
        house_only = [record for record in selected if record.change_type == "house_only"]
        rows.append(
            {
                "region": region,
                "records": len(selected),
                "house_only": len(house_only),
                "publishable_house_only": sum(
                    record.review_status != "quarantine" for record in house_only
                ),
                "house_only_centavos": sum(record.house_centavos for record in house_only),
            }
        )
    return sorted(rows, key=lambda item: (-item["house_only"], item["region"]))


def _examples(records: list[StageChange]) -> dict[str, list[dict[str, Any]]]:
    selected = sorted(
        (record for record in records if record.review_status != "quarantine"),
        key=lambda record: (-abs(record.difference_centavos), record.record_id),
    )[:20]
    return {
        "largest_absolute_changes": [
            {
                "record_id": record.record_id,
                "title": record.title,
                "dataset": record.dataset,
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


def _story(metadata: dict[str, Any], claims: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sections = [
        {
            "id": "direct-answer",
            "section_type": "finding",
            "heading": "The four project lists became larger in total, but not every row moved the same way",
            "copy": [claims["stage-total-records"]["statement"], claims["stage-net-movement"]["statement"]],
            "claim_ids": ["stage-total-records", "stage-net-movement"],
            "source_ids": [OVERVIEW_SOURCE_ID],
            "visual_refs": ["chart_data.datasets"],
            "limitation_ids": ["stage-scope", "amounts-not-spending"],
            "narration_eligible": True,
        },
        {
            "id": "change-types",
            "section_type": "finding",
            "heading": "The comparison separates additions, removals, amount changes, and unchanged rows",
            "copy": [
                claims["stage-house-only"]["statement"],
                claims["stage-nep-only"]["statement"],
                claims["stage-amount-changes"]["statement"],
            ],
            "claim_ids": ["stage-house-only", "stage-nep-only", "stage-amount-changes"],
            "source_ids": [OVERVIEW_SOURCE_ID],
            "visual_refs": ["chart_data.change_types"],
            "limitation_ids": ["matching-boundary", "stage-scope"],
            "narration_eligible": True,
        },
        {
            "id": "house-only-review",
            "section_type": "investigation_lead",
            "heading": "House-only rows are questions to check, not insertion findings",
            "copy": [
                claims["stage-publishable-house-only"]["statement"],
                "Each row still needs both document pages, naming, scope, and later budget stages checked before any attribution or conclusion.",
            ],
            "claim_ids": ["stage-publishable-house-only"],
            "source_ids": [OVERVIEW_SOURCE_ID],
            "visual_refs": ["chart_data.regions", "project_examples.largest_absolute_changes"],
            "limitation_ids": ["not-an-insertion-finding", "matching-boundary"],
            "narration_eligible": False,
        },
        {
            "id": "quarantine",
            "section_type": "finding",
            "heading": "Ambiguous rows are held back",
            "copy": [claims["stage-quarantined"]["statement"]],
            "claim_ids": ["stage-quarantined"],
            "source_ids": [OVERVIEW_SOURCE_ID],
            "visual_refs": ["chart_data.review_gate"],
            "limitation_ids": ["quarantine-boundary", "source-extraction"],
            "narration_eligible": True,
        },
        {
            "id": "coverage-boundary",
            "section_type": "finding",
            "heading": "This is a House-stage comparison, not the final budget trail",
            "copy": [
                "The release covers the NEP and the declared House stage for four project lists.",
                "Senate, bicameral, enacted GAA, release, procurement, payment, and implementation evidence remain outside this result.",
            ],
            "claim_ids": ["stage-dataset-count"],
            "source_ids": [OVERVIEW_SOURCE_ID],
            "visual_refs": ["chart_data.datasets"],
            "limitation_ids": ["missing-stages", "stage-scope"],
            "narration_eligible": True,
        },
    ]
    return {
        "schema_version": "1.0",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "editorial_status": "ready",
        "headline": metadata["headline"],
        "deck": "A controlled comparison of four FY2027 project lists, the rows that changed, and the evidence limits that prevent political attribution.",
        "audience": "Filipino public",
        "language": "en-PH",
        "canonical_url": metadata["canonical_url"],
        "data_cutoff": metadata["data_cutoff"],
        "source_ids": [OVERVIEW_SOURCE_ID],
        "sections": sections,
    }


def build_stage_change_release(
    records: Iterable[StageChange],
    *,
    overview: dict[str, Any],
    snapshot_manifest: dict[str, Any],
    published_at: str,
) -> dict[str, Any]:
    """Build the public story and editor package from reconciled stage-change rows."""

    rows = list(records)
    counts = Counter(record.change_type for record in rows)
    quarantined = sum(record.review_status == "quarantine" for record in rows)
    publishable_house_only = sum(
        record.change_type == "house_only" and record.review_status != "quarantine"
        for record in rows
    )
    net = sum(record.difference_centavos for record in rows)
    built_at = str(overview["meta"]["built_at"])[:10]
    checked_at = str(snapshot_manifest["retrieved_at"])[:10]
    metadata = {
        "schema_version": "1.1",
        "story_id": "fy2027-nep-house-changes-2026",
        "slug": "fy2027-nep-house-changes",
        "version": 1,
        "status": "published",
        "editorial_ready": True,
        "headline": "What changed between the FY2027 NEP and House project lists?",
        "canonical_url": "https://busisi.org/research/fy2027-nep-house-changes/",
        "published_at": published_at,
        "data_cutoff": built_at,
        "source_checked_at": checked_at,
        "max_source_age_days": 7,
        "methodology_version": "fy2027-stage-change-research-v1",
        "source_artifact_sha256": snapshot_manifest["overview_sha256"],
        "source_commit": snapshot_manifest["source_commit"],
        "supersedes": None,
    }
    claims = [
        _claim(
            "stage-total-records",
            f"Busisi validated {len(rows):,} comparison rows across the four acquired FY2027 project lists.",
            len(rows),
            "records",
        ),
        _claim(
            "stage-dataset-count",
            f"The release covers {len({record.dataset for record in rows}):,} project-list datasets.",
            len({record.dataset for record in rows}),
            "datasets",
        ),
        _claim(
            "stage-house-only",
            f"{counts['house_only']:,} rows are classified as appearing only in the compared House project list.",
            counts["house_only"],
            "records",
            evidence_state="source_reported",
            limitations=("House-only does not establish insertion, authorship, motive, or wrongdoing.",),
        ),
        _claim(
            "stage-publishable-house-only",
            f"{publishable_house_only:,} House-only rows remain available as documentary review leads after quarantine.",
            publishable_house_only,
            "review candidates",
            evidence_state="review_candidate",
            limitations=("Each candidate requires document and scope review before any conclusion.",),
        ),
        _claim(
            "stage-nep-only",
            f"{counts['nep_only']:,} rows are classified as appearing only in the compared NEP project list.",
            counts["nep_only"],
            "records",
            evidence_state="source_reported",
            limitations=("NEP-only can reflect removal, renaming, merging, or unmatched text.",),
        ),
        _claim(
            "stage-amount-changes",
            f"{counts['increased']:,} matched rows increased and {counts['decreased']:,} decreased in the compared House list.",
            counts["increased"] + counts["decreased"],
            "records",
            evidence_state="source_reported",
        ),
        _claim(
            "stage-net-movement",
            f"Across the four scoped lists, the recorded House total is PHP {_format_centavos(net)} {'higher' if net >= 0 else 'lower'} than the NEP total.",
            net,
            "PHP centavos",
            limitations=("This is a project-list total, not spending or the whole national budget.",),
        ),
        _claim(
            "stage-quarantined",
            f"{quarantined:,} ambiguous or scope-review rows are held in quarantine.",
            quarantined,
            "records",
        ),
    ]
    sources = _sources(overview, snapshot_manifest)
    claim_index = {item["id"]: item for item in claims}
    release = {
        "metadata": metadata,
        "claims": claims,
        "findings": [
            {
                "id": "net-change",
                "title": "The four scoped project lists grew in net terms",
                "result": claim_index["stage-net-movement"]["statement"],
                "claim_ids": ["stage-net-movement"],
                "evidence_state": "verified",
            },
            {
                "id": "separate-change-types",
                "title": "Rows are separated by document-stage change type",
                "result": claim_index["stage-amount-changes"]["statement"],
                "claim_ids": ["stage-house-only", "stage-nep-only", "stage-amount-changes"],
                "evidence_state": "source_reported",
            },
            {
                "id": "held-review",
                "title": "Ambiguous rows are not promoted",
                "result": claim_index["stage-quarantined"]["statement"],
                "claim_ids": ["stage-quarantined"],
                "evidence_state": "verified",
            },
        ],
        "investigations": [
            {
                "question": "Which rows appear only in the compared House project list?",
                "result": claim_index["stage-house-only"]["statement"],
                "state": "partial",
                "calculation_id": "fy2027-stage-change-research-v1",
            },
            {
                "question": "Who authored or caused a document-stage change?",
                "result": "Not established by the acquired records.",
                "state": "evidence_gap",
                "calculation_id": "fy2027-stage-change-research-v1",
            },
            {
                "question": "Did a changed amount become a release, payment, or completed project?",
                "result": "Not established. Later budget and implementation stages are outside this release.",
                "state": "evidence_gap",
                "calculation_id": "fy2027-stage-change-research-v1",
            },
        ],
        "chart_data": {
            "change_types": _change_chart(rows),
            "datasets": _dataset_chart(rows),
            "regions": _region_chart(rows),
            "review_gate": {
                "total_records": len(rows),
                "quarantined": quarantined,
                "publishable_records": len(rows) - quarantined,
                "publishable_house_only": publishable_house_only,
            },
        },
        "project_examples": _examples(rows),
        "sources": sources,
        "limitations": _limitations(),
    }
    release["story"] = _story(metadata, claim_index)
    release["editorial_package"] = build_consumption_index(metadata, sources)
    return release
