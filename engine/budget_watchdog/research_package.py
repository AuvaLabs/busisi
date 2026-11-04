"""Deterministic public research packages derived from archived source rows."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.research_sources import validate_release_evidence

FISCAL_YEARS = frozenset({"2024", "2025", "2026"})
ACTIVE_STATUSES = frozenset({"On-Going", "For Procurement", "Not Yet Started"})

NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9Ñ]+")
PROGRAM_HEADING = re.compile(
    r"\bMULTI\s+PURPOSE\s+BUILDINGS?\s+FACIL(?:ITY|ITIES|ITEIS)\s+"
    r"TO\s+SUPPORT\s*SOCIAL\s+SERVICES?"
)
NATIONAL_BUILDING_HEADING = re.compile(
    r"\bBUILDINGS?\s+AND\s+OTHER\s+STRUCTURES\s+MULTI\s*PURPOSES?\s+FACILITIES\b"
)
MULTIPURPOSE_BUILDING = re.compile(r"\bMULTI\s+PURPOSE\s+BUILDINGS?\b")

REPLACEMENT = re.compile(r"\bREPLAC\w*\b|\bRECONSTRUCTION\b|\bDEMOLITION\b")
REPAIR = re.compile(
    r"\bREPAIR\w*\b|\bREHAB\w*\b|\bRENOVAT\w*\b|\bRETROFIT\w*\b|"
    r"\bRESTOR\w*\b|\bIMPROVEMENT\b|\bUPGRAD\w*\b"
)
CONTINUATION = re.compile(
    r"\bCOMPLETION\b|\bCONTINUAT\w*\b|\bPHASE\s*(?:[IVX]+|\d+)\b|\bEXTENSION\b"
)
EXPLICIT_NEW = re.compile(r"\bNEW\b")
CONSTRUCTION = re.compile(r"\bCONSTRUCT\w*\b|\bCONST\b")

WORK_TYPES = (
    "construction_newness_unstated",
    "completion_or_later_phase",
    "repair_or_improvement",
    "explicitly_new",
    "replacement_or_reconstruction",
    "unclear",
)


def _normalize(value: object) -> str:
    return " ".join(NON_ALPHANUMERIC.sub(" ", str(value or "").upper()).split())


def _without_program_headings(description: object) -> str:
    normalized = _normalize(description)
    normalized = PROGRAM_HEADING.sub(" ", normalized)
    return NATIONAL_BUILDING_HEADING.sub(" ", normalized)


def is_multipurpose_building(description: object) -> bool:
    """Return true only when the project itself names a multipurpose building.

    Generic program headings are removed first because the DPWH source also places
    unrelated airports, classrooms, and other assets under that heading.
    """

    return bool(MULTIPURPOSE_BUILDING.search(_without_program_headings(description)))


def classify_work_type(description: object) -> str:
    normalized = _normalize(description)
    if REPLACEMENT.search(normalized):
        return "replacement_or_reconstruction"
    if REPAIR.search(normalized):
        return "repair_or_improvement"
    if CONTINUATION.search(normalized):
        return "completion_or_later_phase"
    if EXPLICIT_NEW.search(normalized):
        return "explicitly_new"
    if CONSTRUCTION.search(normalized):
        return "construction_newness_unstated"
    return "unclear"


def _budget_centavos(row: dict[str, Any]) -> int:
    value = row.get("budget")
    normalized = Decimal(str(value)) if isinstance(value, float) else value
    return parse_centavos(normalized)


def _location(row: dict[str, Any], field: str, fallback: str = "Not stated") -> str:
    location = row.get("location")
    if not isinstance(location, dict):
        return fallback
    value = location.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _coordinate(row: dict[str, Any]) -> tuple[float, float] | None:
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return float(latitude), float(longitude)
    return None


def _year(row: dict[str, Any]) -> int | None:
    value = row.get("infraYear")
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _city(description: object) -> str | None:
    chunks = [
        " ".join(part.strip(" .-").upper().split()) for part in str(description or "").split(",")
    ]
    found: list[str] = []
    for chunk in chunks:
        city_of = re.search(r"\bCITY OF\s+([A-ZÑ][A-ZÑ .'\-]{1,50})$", chunk)
        if city_of:
            found.append(f"{city_of.group(1).strip()} CITY")
        city = re.search(r"\b([A-ZÑ][A-ZÑ .'\-]{1,40}\s+CITY)\b", chunk)
        if city:
            found.append(city.group(1).strip())
    if not found:
        return None
    label = found[-1]
    for prefix in ("BARANGAY ", "BRGY. ", "BRGY ", "PUROK "):
        if label.startswith(prefix):
            return label.removeprefix(prefix)
    return label


def _quantile(values: list[int], proportion: Decimal) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * proportion).to_integral_value())
    return ordered[index]


def _amount_summary(rows: list[dict[str, Any]]) -> dict[str, int | None]:
    amounts = [_budget_centavos(row) for row in rows]
    positive = [amount for amount in amounts if amount > 0]
    return {
        "recorded_budget_centavos": sum(amounts),
        "positive_budget_records": len(positive),
        "zero_budget_records": len(amounts) - len(positive),
        "p25_centavos": _quantile(positive, Decimal("0.25")),
        "median_centavos": _quantile(positive, Decimal("0.50")),
        "p75_centavos": _quantile(positive, Decimal("0.75")),
        "p90_centavos": _quantile(positive, Decimal("0.90")),
        "maximum_centavos": max(positive) if positive else None,
    }


def _claim(
    claim_id: str,
    statement: str,
    value: int,
    unit: str,
    *,
    calculation_id: str,
    evidence_state: str = "source_reported",
    limitations: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "statement": statement,
        "value": value,
        "unit": unit,
        "scope": "Conservatively classified DPWH FY2024 to FY2026 delivery records",
        "evidence_state": evidence_state,
        "calculation_id": calculation_id,
        "source_ids": ["dpwh-delivery-snapshot-2026-01-22"],
        "limitations": list(limitations),
    }


def _prior_coordinate_candidates(
    active: list[dict[str, Any]], all_multipurpose: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    completed: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for row in all_multipurpose:
        coordinate = _coordinate(row)
        if row.get("status") == "Completed" and coordinate is not None:
            completed[coordinate].append(row)

    candidates: list[dict[str, Any]] = []
    coordinates: set[tuple[float, float]] = set()
    for row in active:
        coordinate, year = _coordinate(row), _year(row)
        if coordinate is None or year is None:
            continue
        prior = [
            item
            for item in completed.get(coordinate, [])
            if item.get("contractId") != row.get("contractId")
            and _year(item) is not None
            and _year(item) <= year  # type: ignore[operator]
        ]
        if not prior:
            continue
        coordinates.add(coordinate)
        candidates.append(
            {
                "contract_id": row.get("contractId"),
                "fiscal_year": year,
                "description": row.get("description"),
                "latitude": coordinate[0],
                "longitude": coordinate[1],
                "completed_contracts": [
                    {"contract_id": item.get("contractId"), "fiscal_year": _year(item)}
                    for item in sorted(prior, key=lambda item: str(item.get("contractId")))
                ],
                "evidence_state": "review_candidate",
                "limitation": "Exact coordinate reuse can describe a phase, nearby work, or a source error.",
            }
        )
    return candidates, len(coordinates)


def _ranked_groups(
    rows: list[dict[str, Any]], key: str, *, limit: int | None = None
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_location(row, key)].append(row)
    ranked = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    if limit is not None:
        ranked = ranked[:limit]
    return [
        {
            "label": label,
            "active_pipeline": len(group),
            "recorded_budget_centavos": sum(_budget_centavos(row) for row in group),
        }
        for label, group in ranked
    ]


def build_multipurpose_release(
    all_rows: list[dict[str, Any]],
    *,
    source_sha256: str,
    source_modified: str,
    published_at: str,
) -> dict[str, Any]:
    """Build the complete first Busisi research release from DPWH source rows."""

    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    all_multipurpose = [row for row in all_rows if is_multipurpose_building(row.get("description"))]
    records = [row for row in all_multipurpose if str(row.get("infraYear")) in FISCAL_YEARS]
    active = [row for row in records if row.get("status") in ACTIVE_STATUSES]
    ongoing = [row for row in records if row.get("status") == "On-Going"]
    completed = [row for row in records if row.get("status") == "Completed"]
    pricing = _amount_summary(active)

    work_groups = {
        kind: [row for row in active if classify_work_type(row.get("description")) == kind]
        for kind in WORK_TYPES
    }
    existing_wording = sum(
        len(work_groups[kind])
        for kind in (
            "completion_or_later_phase",
            "repair_or_improvement",
            "replacement_or_reconstruction",
        )
    )
    coordinate_candidates, candidate_coordinates = _prior_coordinate_candidates(
        active, all_multipurpose
    )

    city_counts = Counter(filter(None, (_city(row.get("description")) for row in active)))
    regions = []
    for region in sorted({_location(row, "region") for row in records}):
        region_active = [row for row in active if _location(row, "region") == region]
        regions.append(
            {
                "region": region,
                "ongoing": sum(row.get("status") == "On-Going" for row in region_active),
                "active_pipeline": len(region_active),
                "completed": sum(
                    row.get("status") == "Completed"
                    for row in records
                    if _location(row, "region") == region
                ),
                "recorded_budget_centavos": sum(_budget_centavos(row) for row in region_active),
            }
        )

    claims = [
        _claim(
            "mpb-total-records",
            f"{len(records):,} FY2024 to FY2026 records conservatively name a multipurpose building as the project itself.",
            len(records),
            "records",
            calculation_id="mpb-classifier-v1",
            evidence_state="verified",
        ),
        _claim(
            "mpb-ongoing",
            f"{len(ongoing):,} classified records are marked On-Going in the archived source.",
            len(ongoing),
            "records",
            calculation_id="mpb-status-v1",
            limitations=("Source status is not independent physical-site verification.",),
        ),
        _claim(
            "mpb-active-pipeline",
            f"{len(active):,} classified records are On-Going, For Procurement, or Not Yet Started.",
            len(active),
            "records",
            calculation_id="mpb-status-v1",
        ),
        _claim(
            "mpb-completed",
            f"{len(completed):,} classified records are marked Completed in the archived source.",
            len(completed),
            "records",
            calculation_id="mpb-status-v1",
            limitations=("Completed is a source field, not an acquired acceptance certificate.",),
        ),
        _claim(
            "mpb-active-budget",
            "The active pipeline carries the recorded budget total stated in this package.",
            int(pricing["recorded_budget_centavos"] or 0),
            "PHP centavos",
            calculation_id="mpb-budget-v1",
            limitations=("Recorded budget is not payment, final cost, or price reasonableness.",),
        ),
        _claim(
            "mpb-positive-active-budget",
            f"{pricing['positive_budget_records']:,} active records contain a positive recorded budget.",
            int(pricing["positive_budget_records"] or 0),
            "records",
            calculation_id="mpb-budget-v1",
        ),
        _claim(
            "mpb-existing-work-wording",
            f"{existing_wording:,} active titles explicitly describe completion, a later phase, repair, improvement, replacement, or reconstruction.",
            existing_wording,
            "records",
            calculation_id="mpb-work-type-v1",
        ),
        _claim(
            "mpb-prior-coordinate-candidates",
            f"{len(coordinate_candidates):,} active records share an exact coordinate with a completed multipurpose-building record from the same or an earlier infrastructure year.",
            len(coordinate_candidates),
            "review candidates",
            calculation_id="mpb-coordinate-v1",
            evidence_state="review_candidate",
            limitations=(
                "Exact coordinate reuse does not prove a duplicate or an existing structure.",
            ),
        ),
    ]

    project_examples = [
        {
            "contract_id": row.get("contractId"),
            "description": row.get("description"),
            "status": row.get("status"),
            "fiscal_year": _year(row),
            "region": _location(row, "region"),
            "district_office": _location(row, "province"),
            "recorded_budget_centavos": _budget_centavos(row),
            "reader_url": f"/contracts/{row.get('contractId')}/",
        }
        for row in sorted(active, key=_budget_centavos, reverse=True)[:12]
    ]

    return {
        "metadata": {
            "schema_version": "1.0",
            "story_id": "multipurpose-buildings-2026",
            "slug": "multipurpose-buildings",
            "version": 1,
            "status": "published",
            "video_ready": True,
            "headline": "How many multipurpose buildings are being built?",
            "canonical_url": "https://busisi.org/research/multipurpose-buildings/",
            "published_at": published_at,
            "data_cutoff": source_modified,
            "methodology_version": "mpb-classifier-v1",
            "source_artifact_sha256": source_sha256,
            "supersedes": None,
        },
        "claims": claims,
        "findings": [
            {
                "id": "national-count",
                "title": "Thousands are marked ongoing, but the status is source-reported",
                "result": f"{len(ongoing):,} records are marked On-Going and {len(active):,} sit in the active pipeline.",
                "claim_ids": ["mpb-ongoing", "mpb-active-pipeline"],
                "evidence_state": "source_reported",
            },
            {
                "id": "existing-work",
                "title": "Many titles describe work on an existing or partly built asset",
                "result": f"{existing_wording:,} active titles describe completion, later phases, repair, improvement, replacement, or reconstruction.",
                "claim_ids": ["mpb-existing-work-wording"],
                "evidence_state": "verified",
            },
            {
                "id": "same-coordinate",
                "title": "Exact coordinate reuse creates a bounded review queue",
                "result": f"{len(coordinate_candidates):,} active records at {candidate_coordinates:,} exact coordinates have a completed comparison record.",
                "claim_ids": ["mpb-prior-coordinate-candidates"],
                "evidence_state": "review_candidate",
            },
        ],
        "investigations": [
            {
                "question": "How many records actually describe a multipurpose building?",
                "result": "Generic program-heading occurrences were removed before the project phrase was classified.",
                "state": "verified",
                "calculation_id": "mpb-classifier-v1",
            },
            {
                "question": "Is the work new, continuing, repairing, or replacing a structure?",
                "result": "Titles were classified by explicit wording. Construction alone remains newness unstated.",
                "state": "verified",
                "calculation_id": "mpb-work-type-v1",
            },
            {
                "question": "Does a completed building already exist at the same place?",
                "result": "Exact-coordinate comparisons identify candidates only. The snapshot does not prove physical existence.",
                "state": "partial",
                "calculation_id": "mpb-coordinate-v1",
            },
            {
                "question": "Is the recorded amount a fair construction price?",
                "result": "Not established. Comparable floor area, specifications, work scope, award, payment, and final cost are not available for every record.",
                "state": "evidence_gap",
                "calculation_id": "mpb-budget-v1",
            },
        ],
        "chart_data": {
            "status": dict(sorted(Counter(str(row.get("status")) for row in records).items())),
            "regions": regions,
            "district_offices": _ranked_groups(active, "province", limit=25),
            "explicit_cities": [
                {"city": city, "active_pipeline": count}
                for city, count in city_counts.most_common(25)
            ],
            "explicit_city_coverage": {
                "classified": sum(city_counts.values()),
                "active": len(active),
            },
            "work_types": {
                kind: {
                    "count": len(group),
                    "recorded_budget_centavos": sum(_budget_centavos(row) for row in group),
                }
                for kind, group in work_groups.items()
            },
            "pricing": pricing,
            "evidence": {
                "active_with_coordinates": sum(_coordinate(row) is not None for row in active),
                "active_with_source_satellite_flag": sum(
                    bool(row.get("hasSatelliteImage")) for row in active
                ),
                "prior_coordinate_candidates": len(coordinate_candidates),
                "candidate_coordinates": candidate_coordinates,
            },
        },
        "project_examples": {
            "largest_active_recorded_budgets": project_examples,
            "prior_coordinate_candidates": coordinate_candidates,
        },
        "sources": [
            {
                "id": "dpwh-delivery-snapshot-2026-01-22",
                "publisher": "Department of Public Works and Highways",
                "access_provider": "BetterGov",
                "source_kind": "curated_official_extract",
                "scope": "Archived DPWH project and contract snapshot",
                "modified": source_modified,
                "retrieved_at": "2026-11-02",
                "origin_url": "https://transparency.dpwh.gov.ph/",
                "source_url": (
                    "https://huggingface.co/datasets/bettergovph/"
                    "dpwh-transparency-data/resolve/"
                    "648ea96af4f7625d606fda0b78803917913a26b7/"
                    "dpwh_transparency_data.parquet"
                ),
                "sha256": source_sha256,
            }
        ],
        "limitations": [
            "The release counts source records, not independently observed physical buildings.",
            "Source status does not prove present-day activity, completion, acceptance, payment, quality, or public value.",
            "City labels are partial because city and municipality names are embedded in free-text descriptions.",
            "DPWH district-office labels are not geographic or congressional-boundary determinations.",
            "Exact coordinate reuse is a review lead and can describe phases, nearby work, reused coordinates, or source errors.",
            "Recorded budgets are not award amounts, payments, final costs, or unit-price comparisons.",
            "The conservative classifier can omit misspelled or abbreviated multipurpose-building descriptions.",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_release_package(release: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write immutable payloads and a manifest that authenticates every file."""

    validate_release_evidence(release)
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "claims.json": release["claims"],
        "findings.json": release["findings"],
        "investigations.json": release["investigations"],
        "chart-data.json": release["chart_data"],
        "project-examples.json": release["project_examples"],
        "sources.json": release["sources"],
        "limitations.json": release["limitations"],
    }
    files = []
    for path, value in sorted(payloads.items()):
        payload = _json_bytes(value)
        (output_dir / path).write_bytes(payload)
        files.append(
            {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        )
    package_identity = "".join(f"{item['path']}\0{item['sha256']}\n" for item in files).encode()
    manifest = {
        **release["metadata"],
        "files": files,
        "package_sha256": hashlib.sha256(package_identity).hexdigest(),
    }
    (output_dir / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest
