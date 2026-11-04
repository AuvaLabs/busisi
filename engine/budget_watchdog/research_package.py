"""Deterministic public research packages derived from archived source rows."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.budget_watchdog.money import parse_centavos
from engine.budget_watchdog.research_editor import write_research_release

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

PUBLISHABLE_STATES = frozenset({"verified", "source_reported"})
EDITORIAL_PACKAGE_VERSION = 2


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


def _release_limitations() -> list[dict[str, str]]:
    return [
        {
            "id": "record-count",
            "text": "The release counts source records, not independently observed physical buildings.",
        },
        {
            "id": "source-status",
            "text": "Source status does not prove present-day activity, completion, acceptance, payment, quality, or public value.",
        },
        {
            "id": "location-coverage",
            "text": "City labels are partial because city and municipality names are embedded in free-text descriptions.",
        },
        {
            "id": "district-labels",
            "text": "DPWH district-office labels are not geographic or congressional-boundary determinations.",
        },
        {
            "id": "coordinate-reuse",
            "text": "Exact coordinate reuse is a review lead and can describe phases, nearby work, reused coordinates, or source errors.",
        },
        {
            "id": "budget-meaning",
            "text": "Recorded budgets are not award amounts, payments, final costs, or unit-price comparisons.",
        },
        {
            "id": "classifier-omissions",
            "text": "The conservative classifier can omit misspelled or abbreviated multipurpose-building descriptions.",
        },
    ]


def _story_section(
    section_id: str,
    heading: str,
    copy: list[str],
    claim_ids: list[str],
    *,
    visual_refs: list[str],
    limitation_ids: list[str],
    section_type: str = "finding",
    narration_eligible: bool = True,
) -> dict[str, Any]:
    return {
        "id": section_id,
        "section_type": section_type,
        "heading": heading,
        "copy": copy,
        "claim_ids": claim_ids,
        "source_ids": ["dpwh-delivery-snapshot-2026-01-22"],
        "visual_refs": visual_refs,
        "limitation_ids": limitation_ids,
        "narration_eligible": narration_eligible,
    }


def _story_sections(claims: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ongoing = claims["mpb-ongoing"]["value"]
    pipeline = claims["mpb-active-pipeline"]["value"]
    existing = claims["mpb-existing-work-wording"]["value"]
    candidates = claims["mpb-prior-coordinate-candidates"]["value"]
    return [
        _story_section(
            "direct-answer",
            "The source reports a large active pipeline",
            [
                f"{ongoing:,} conservatively classified records are marked On-Going.",
                f"The wider active pipeline contains {pipeline:,} records when For Procurement and Not Yet Started are included.",
                "These are source records and source-reported statuses, not an independent count of physical buildings or active construction sites.",
            ],
            ["mpb-total-records", "mpb-ongoing", "mpb-active-pipeline"],
            visual_refs=["chart_data.status"],
            limitation_ids=["record-count", "source-status", "classifier-omissions"],
        ),
        _story_section(
            "work-type",
            "Many titles describe work on an existing or partly built asset",
            [
                f"{existing:,} active titles explicitly describe completion, a later phase, repair, improvement, replacement, or reconstruction.",
                "A title that only says construction does not establish that the structure is new.",
            ],
            ["mpb-existing-work-wording"],
            visual_refs=["chart_data.work_types"],
            limitation_ids=["record-count", "classifier-omissions"],
        ),
        _story_section(
            "location",
            "The records can be compared by region, district-office label, and some city names",
            [
                "Region totals reconcile to the national classified result.",
                "District-office labels reproduce the source, while city coverage is partial because locality names are embedded in project titles.",
            ],
            ["mpb-active-pipeline", "mpb-ongoing"],
            visual_refs=[
                "chart_data.regions",
                "chart_data.district_offices",
                "chart_data.explicit_cities",
            ],
            limitation_ids=["location-coverage", "district-labels"],
        ),
        _story_section(
            "pricing",
            "Recorded amounts describe scale, not whether a project is fairly priced",
            [
                "The package provides the recorded active budget and price distribution for records with a positive amount.",
                "A fair comparison still needs floor area, specifications, work scope, award, payment, final cost, year, and location.",
            ],
            ["mpb-active-budget", "mpb-positive-active-budget"],
            visual_refs=["chart_data.pricing", "project_examples.largest_active_recorded_budgets"],
            limitation_ids=["budget-meaning"],
        ),
        _story_section(
            "coordinate-review",
            "Some exact-coordinate matches need a closer look",
            [
                f"{candidates:,} active records share an exact coordinate with a completed comparison record.",
                "This is a bounded review queue. It does not prove duplication, a ghost project, or wrongdoing.",
            ],
            ["mpb-prior-coordinate-candidates"],
            visual_refs=["chart_data.evidence", "project_examples.prior_coordinate_candidates"],
            limitation_ids=["coordinate-reuse"],
            section_type="investigation_lead",
            narration_eligible=False,
        ),
    ]


def _build_story(release: dict[str, Any]) -> dict[str, Any]:
    metadata = release["metadata"]
    claims = {item["id"]: item for item in release["claims"]}
    return {
        "schema_version": "1.0",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "editorial_status": "ready",
        "headline": metadata["headline"],
        "deck": "A reproducible count of multipurpose-building records, what their titles and statuses say, and what the available evidence still cannot prove.",
        "audience": "Filipino public",
        "language": "en-PH",
        "canonical_url": metadata["canonical_url"],
        "data_cutoff": metadata["data_cutoff"],
        "source_ids": [item["id"] for item in release["sources"]],
        "sections": _story_sections(claims),
    }


def _build_editorial_package(release: dict[str, Any]) -> dict[str, Any]:
    metadata = release["metadata"]
    base = f"https://busisi.org/data/research/{metadata['slug']}/v{metadata['version']}"
    files = {
        name: f"{base}/{path}"
        for name, path in {
            "claims": "claims.json",
            "findings": "findings.json",
            "investigations": "investigations.json",
            "chart_data": "chart-data.json",
            "project_examples": "project-examples.json",
            "sources": "sources.json",
            "limitations": "limitations.json",
        }.items()
    }
    return {
        "schema_version": "1.0",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "status": "ready_for_consumption",
        "canonical_article_url": metadata["canonical_url"],
        "api_url": "https://busisi.org/api/v1/research/multipurpose-buildings",
        "package_base_url": base,
        "manifest_url": f"{base}/manifest.json",
        "story_url": f"{base}/story.json",
        "files": files,
        "direct_source_urls": [item["source_url"] for item in release["sources"]],
        "integrity": {
            "method": "sha256-manifest",
            "instruction": "Verify every downloaded file against manifest.json before use.",
        },
        "evidence_boundary": "Only verified and source-reported claims are eligible for factual narration. Investigation leads must retain their limitations.",
        "attribution": "Busisi, built and maintained by Auva Labs. Source publishers remain identified in sources.json.",
        "contact": "dev@auvalabs.com",
    }


def _validate_story_section(
    section: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    sources: set[str],
    limitations: set[str],
) -> None:
    if not section.get("copy") or not all(
        isinstance(item, str) and item.strip() for item in section["copy"]
    ):
        raise ValueError("story section copy must be non-empty text")
    claim_ids = section.get("claim_ids", [])
    unknown = set(claim_ids) - claims.keys()
    if unknown:
        raise ValueError(f"story section references unknown claims: {sorted(unknown)}")
    if set(section.get("source_ids", [])) - sources:
        raise ValueError("story section references an unknown source")
    if set(section.get("limitation_ids", [])) - limitations:
        raise ValueError("story section references an unknown limitation")
    review_claims = [
        item for item in claim_ids if claims[item]["evidence_state"] not in PUBLISHABLE_STATES
    ]
    if section.get("narration_eligible") and review_claims:
        raise ValueError("review candidate cannot be eligible for factual narration")
    if review_claims and (
        section.get("section_type") != "investigation_lead" or not section.get("limitation_ids")
    ):
        raise ValueError("review candidate must remain a limited investigation lead")


def _validate_consumption_index(package: dict[str, Any], metadata: dict[str, Any]) -> None:
    expected_files = {
        "claims",
        "findings",
        "investigations",
        "chart_data",
        "project_examples",
        "sources",
        "limitations",
    }
    base = f"https://busisi.org/data/research/{metadata['slug']}/v{metadata['version']}"
    if package.get("package_base_url") != base or package.get("manifest_url") != (
        f"{base}/manifest.json"
    ):
        raise ValueError("consumption index must use the immutable Busisi release URLs")
    if set(package.get("files", {})) != expected_files:
        raise ValueError("consumption index must link every release data file")


def validate_editorial_release(release: dict[str, Any]) -> None:
    """Fail closed when a ready story cannot resolve its evidence references."""

    metadata = release.get("metadata", {})
    if metadata.get("version", 1) < EDITORIAL_PACKAGE_VERSION:
        return
    story = release.get("story")
    package = release.get("editorial_package")
    if not isinstance(story, dict) or story.get("editorial_status") != "ready":
        raise ValueError("v2 release requires a ready editorial story")
    if not isinstance(package, dict) or package.get("status") != "ready_for_consumption":
        raise ValueError("v2 release requires a ready consumption index")
    if story.get("story_id") != metadata.get("story_id") or story.get("version") != metadata.get(
        "version"
    ):
        raise ValueError("story identity must match release metadata")
    _validate_consumption_index(package, metadata)
    claims = {item["id"]: item for item in release["claims"]}
    sources = {item["id"] for item in release["sources"]}
    limitations = {item["id"] for item in release["limitations"]}
    sections = story.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("editorial story must contain ordered sections")
    for section in sections:
        _validate_story_section(section, claims, sources, limitations)


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
    version: int = 1,
    supersedes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete Busisi research release from DPWH source rows."""

    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    if version < 1:
        raise ValueError("version must be a positive integer")
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

    release = {
        "metadata": {
            "schema_version": "1.0",
            "story_id": "multipurpose-buildings-2026",
            "slug": "multipurpose-buildings",
            "version": version,
            "status": "published",
            "video_ready": True,
            "headline": "How many multipurpose buildings are being built?",
            "canonical_url": "https://busisi.org/research/multipurpose-buildings/",
            "published_at": published_at,
            "data_cutoff": source_modified,
            "methodology_version": "mpb-classifier-v1",
            "source_artifact_sha256": source_sha256,
            "supersedes": supersedes,
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
        "limitations": (
            _release_limitations()
            if version >= EDITORIAL_PACKAGE_VERSION
            else [item["text"] for item in _release_limitations()]
        ),
    }
    if version >= EDITORIAL_PACKAGE_VERSION:
        release["story"] = _build_story(release)
        release["editorial_package"] = _build_editorial_package(release)
        validate_editorial_release(release)
    return release


def write_release_package(release: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write through the shared research editor package contract."""

    validate_editorial_release(release)
    return write_research_release(release, output_dir)
