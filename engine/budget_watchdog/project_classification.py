"""Deterministic, multi-label classifications for DPWH project records."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from engine.budget_watchdog.research_package import is_multipurpose_building

RULE_VERSION = 1
NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True, slots=True)
class ProjectClassification:
    dimension: str
    tag: str
    label: str
    evidence_kind: str
    rule_id: str
    rule_version: int = RULE_VERSION


@dataclass(frozen=True, slots=True)
class _Rule:
    dimension: str
    tag: str
    label: str
    title_patterns: tuple[str, ...] = ()
    category_patterns: tuple[str, ...] = ()

    @property
    def rule_id(self) -> str:
        return f"{self.dimension}:{self.tag}"


RULES = (
    _Rule(
        "project_type",
        "road",
        "Road",
        (r"\bROAD\b", r"\bROADS\b", r"\bHIGHWAY\b", r"\bEXPRESSWAY\b"),
        (r"\bROAD\b", r"\bROADS\b", r"\bFMR\b"),
    ),
    _Rule(
        "project_type",
        "bridge",
        "Bridge",
        (r"\bBRIDGE\b", r"\bBRIDGES\b", r"\bFLYOVER\b", r"\bOVERPASS\b"),
        (r"\bBRIDGE\b", r"\bBRIDGES\b"),
    ),
    _Rule(
        "project_type",
        "flood_control",
        "Flood control or drainage",
        (
            r"\bFLOOD\s+(?:CONTROL|MITIGATION|PROTECTION)\b",
            r"\bRIVER\s+CONTROL\b",
            r"\bDRAINAGE\b",
            r"\bDIKE\b",
            r"\bDIKES\b",
            r"\bLEVEE\b",
            r"\bSEAWALL\b",
        ),
        (r"\bFLOOD\b", r"\bDRAINAGE\b"),
    ),
    _Rule(
        "project_type",
        "school",
        "School or classroom",
        (r"\bSCHOOLS?\b", r"\bCLASSROOMS?\b"),
        (r"\bDEPED\b", r"\bBEFF\b", r"\bSCHOOLS?\b"),
    ),
    _Rule(
        "project_type",
        "health_facility",
        "Hospital or health facility",
        (
            r"\bHOSPITALS?\b",
            r"\bHEALTH\s+(?:CENTERS?|CENTRES?|FACILIT(?:Y|IES))\b",
            r"\bINFIRMARY\b",
        ),
        (r"\bDOH\b", r"\bHFEP\b", r"\bHEALTH\s+FACIL"),
    ),
    _Rule(
        "project_type",
        "water_system",
        "Water system",
        (
            r"\bWATER\s+(?:SUPPLY|SYSTEMS?|FACILIT(?:Y|IES)|TANKS?)\b",
            r"\bPOTABLE\s+WATER\b",
            r"\bRAINWATER\s+COLLECTOR",
        ),
        (r"\bWATER\s+(?:PROVISION|SUPPLY|SYSTEM)\b",),
    ),
    _Rule(
        "project_type",
        "evacuation_center",
        "Evacuation center",
        (r"\bEVACUATION\s+(?:CENTERS?|CENTRES?)\b",),
    ),
    _Rule(
        "project_type",
        "port_harbor",
        "Port or harbor",
        (r"\bPORTS?\b", r"\bHARBORS?\b", r"\bHARBOURS?\b", r"\bWHAR(?:F|VES)\b"),
        (r"\bPORTS?\b", r"\bHARBORS?\b", r"\bHARBOURS?\b"),
    ),
    _Rule(
        "project_type",
        "public_building",
        "Public building or facility",
        (r"\bBUILDING\b", r"\bBUILDINGS\b"),
        (r"\bBUILDING\b", r"\bBUILDINGS\b", r"\bFACILITIES\b"),
    ),
    _Rule(
        "purpose",
        "farm_to_market",
        "Farm-to-market access",
        (r"\bFARM\s+TO\s+MARKET\b",),
        (r"\bDA\s+FMR\b", r"\bFARM\s+TO\s+MARKET\b"),
    ),
    _Rule(
        "purpose",
        "transport",
        "Transport access",
        (r"\bROAD\b", r"\bROADS\b", r"\bBRIDGE\b", r"\bHIGHWAY\b", r"\bPORT\b"),
        (r"\bROAD\b", r"\bROADS\b", r"\bBRIDGE\b", r"\bBRIDGES\b", r"\bFMR\b"),
    ),
    _Rule(
        "purpose",
        "flood_protection",
        "Flood protection",
        (r"\bFLOOD\b", r"\bRIVER\s+CONTROL\b", r"\bDRAINAGE\b", r"\bDIKE\b"),
        (r"\bFLOOD\b", r"\bDRAINAGE\b"),
    ),
    _Rule(
        "purpose",
        "education",
        "Education",
        (r"\bSCHOOLS?\b", r"\bCLASSROOMS?\b"),
        (r"\bDEPED\b", r"\bBEFF\b"),
    ),
    _Rule(
        "purpose",
        "health",
        "Health services",
        (r"\bHOSPITALS?\b", r"\bHEALTH\b", r"\bINFIRMAR(?:Y|IES)\b"),
        (r"\bDOH\b", r"\bHFEP\b"),
    ),
    _Rule(
        "purpose",
        "disaster_response",
        "Disaster response",
        (r"\bEVACUATION\s+(?:CENTERS?|CENTRES?)\b",),
    ),
    _Rule(
        "purpose",
        "water_access",
        "Water access",
        (r"\bWATER\s+(?:SUPPLY|SYSTEMS?|FACILIT(?:Y|IES)|TANKS?)\b", r"\bPOTABLE\s+WATER\b"),
        (r"\bWATER\s+(?:PROVISION|SUPPLY|SYSTEM)\b",),
    ),
    _Rule("work_type", "construction", "Construction", (r"\bCONSTRUCT\w*\b",)),
    _Rule("work_type", "later_phase", "Later phase", (r"\bPHASE\s*(?:[IVX]+|\d+)\b",)),
    _Rule("work_type", "completion", "Completion", (r"\bCOMPLETION\b", r"\bCOMPLETED\b")),
    _Rule("work_type", "rehabilitation", "Rehabilitation", (r"\bREHAB\w*\b",)),
    _Rule("work_type", "repair", "Repair", (r"\bREPAIR\w*\b",)),
    _Rule("work_type", "improvement", "Improvement", (r"\bIMPROV\w*\b", r"\bUPGRAD\w*\b")),
    _Rule("work_type", "maintenance", "Maintenance", (r"\bMAINTENANCE\b",)),
    _Rule(
        "work_type",
        "replacement",
        "Replacement or reconstruction",
        (r"\bREPLAC\w*\b", r"\bRECONSTRUCT\w*\b"),
    ),
    _Rule("work_type", "retrofitting", "Retrofitting", (r"\bRETROFIT\w*\b",)),
    _Rule("work_type", "restoration", "Restoration", (r"\bRESTOR\w*\b",)),
    _Rule(
        "funding_program", "da_fmr", "DA farm-to-market roads", category_patterns=(r"\bDA\s+FMR\b",)
    ),
    _Rule(
        "funding_program",
        "deped_beff",
        "DepEd school facilities",
        category_patterns=(r"\bDEPED\s+BEFF\b",),
    ),
    _Rule(
        "funding_program",
        "doh_hfep",
        "DOH health facilities",
        category_patterns=(r"\bDOH\s+HFEP\b",),
    ),
    _Rule("funding_program", "ssp", "Special support program", category_patterns=(r"\bSSP\b",)),
    _Rule(
        "funding_program",
        "locally_funded",
        "Locally funded program",
        category_patterns=(r"\bLFP\b",),
    ),
    _Rule(
        "funding_program",
        "foreign_assisted",
        "Foreign-assisted project",
        category_patterns=(r"\bFAPS?\b",),
    ),
    _Rule("funding_program", "pamana", "PAMANA", category_patterns=(r"\bPAMANA\b",)),
    _Rule(
        "funding_program",
        "unprogrammed",
        "Unprogrammed appropriations",
        category_patterns=(r"\bUNPROGRAMMED\b",),
    ),
    _Rule(
        "funding_program", "trust_fund", "Trust fund", category_patterns=(r"\bTRUST\s+FUNDS?\b",)
    ),
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.upper())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(NON_ALPHANUMERIC.sub(" ", ascii_text).split())


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _classification(rule: _Rule, *, title: bool, category: bool) -> ProjectClassification:
    evidence = (
        "source_category_and_title"
        if title and category
        else "project_title"
        if title
        else "source_category"
    )
    return ProjectClassification(
        dimension=rule.dimension,
        tag=rule.tag,
        label=rule.label,
        evidence_kind=evidence,
        rule_id=rule.rule_id,
    )


def classify_project(*, description: str, category: str) -> tuple[ProjectClassification, ...]:
    """Return supported tags without forcing every record into one category."""

    title_text = _normalize(description)
    category_text = _normalize(category)
    classifications: list[ProjectClassification] = []
    for rule in RULES:
        title_match = _matches(title_text, rule.title_patterns)
        category_match = _matches(category_text, rule.category_patterns)
        if title_match or category_match:
            classifications.append(
                _classification(rule, title=title_match, category=category_match)
            )
    if is_multipurpose_building(description):
        classifications.append(
            ProjectClassification(
                dimension="project_type",
                tag="multipurpose_building",
                label="Multipurpose building",
                evidence_kind="project_title",
                rule_id="project_type:multipurpose_building",
            )
        )
    return tuple(sorted(classifications, key=lambda item: (item.dimension, item.tag)))
