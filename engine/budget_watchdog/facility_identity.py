"""Deterministic facility identity matching with conservative publication states."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

FacilityType = Literal["school", "hospital", "health_center"]
SourceType = Literal["budget", "delivery"]
MatchState = Literal["official_exact", "group_only", "ambiguous", "unlinked"]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    text = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


@dataclass(frozen=True, slots=True)
class FacilityRegistryRecord:
    facility_id: str
    facility_type: FacilityType
    official_id: str
    official_name: str
    municipality: str
    province: str
    region: str
    source_id: str
    division: str = ""
    latitude_e6: int | None = None
    longitude_e6: int | None = None
    source_row: int | None = None
    demolition_required: bool = False
    geotechnical_report: bool = False
    site_development_plan: bool = False
    ownership_documents: bool = False

    def __post_init__(self) -> None:
        required = (
            self.facility_id,
            self.official_id,
            self.official_name,
            self.source_id,
        )
        if self.facility_type not in {"school", "hospital", "health_center"}:
            raise ValueError("facility type is invalid")
        if any(not value.strip() for value in required):
            raise ValueError("facility registry identity fields are required")


@dataclass(frozen=True, slots=True)
class FacilityMention:
    source_type: SourceType
    record_id: str
    facility_type: FacilityType
    facility_name: str
    municipality: str = ""
    province: str = ""
    region: str = ""
    official_id: str = ""

    def __post_init__(self) -> None:
        if self.source_type not in {"budget", "delivery"}:
            raise ValueError("source type is invalid")
        if self.facility_type not in {"school", "hospital", "health_center"}:
            raise ValueError("facility type is invalid")
        if not self.record_id.strip():
            raise ValueError("record ID is required")


@dataclass(frozen=True, slots=True)
class FacilityTitleRecord:
    source_type: SourceType
    record_id: str
    title: str
    location: str = ""

    def __post_init__(self) -> None:
        if self.source_type not in {"budget", "delivery"}:
            raise ValueError("source type is invalid")
        if not self.record_id.strip() or not self.title.strip():
            raise ValueError("record ID and title are required")


@dataclass(frozen=True, slots=True)
class FacilityLink:
    source_type: SourceType
    record_id: str
    match_state: MatchState
    facility_id: str | None
    record_group_key: str | None
    record_group_label: str
    match_method: str
    confidence: int
    signals: tuple[str, ...]
    limitation: str


def _place_state(mention: FacilityMention, record: FacilityRegistryRecord) -> str:
    compared = 0
    for mentioned, registered in (
        (mention.municipality, record.municipality),
        (mention.province, record.province),
        (mention.region, record.region),
    ):
        if not mentioned.strip():
            continue
        compared += 1
        if not registered.strip() or _normalize(mentioned) != _normalize(registered):
            return "conflict"
    return "match" if compared else "missing"


def _link(
    mention: FacilityMention,
    state: MatchState,
    *,
    facility_id: str | None = None,
    group_key: str | None = None,
    method: str,
    confidence: int,
    signals: tuple[str, ...],
    limitation: str,
) -> FacilityLink:
    return FacilityLink(
        source_type=mention.source_type,
        record_id=mention.record_id,
        match_state=state,
        facility_id=facility_id,
        record_group_key=group_key,
        record_group_label=mention.facility_name.strip(),
        match_method=method,
        confidence=confidence,
        signals=signals,
        limitation=limitation,
    )


def _official_id_link(
    mention: FacilityMention, registry: tuple[FacilityRegistryRecord, ...]
) -> FacilityLink | None:
    official_id = _normalize(mention.official_id)
    if not official_id:
        return None
    candidates = tuple(
        record
        for record in registry
        if record.facility_type == mention.facility_type
        and _normalize(record.official_id) == official_id
    )
    if len(candidates) != 1:
        return _link(
            mention,
            "ambiguous",
            method="official_id_review",
            confidence=0,
            signals=("official_id", "identifier_not_unique"),
            limitation="The stated official ID did not resolve to one registry identity.",
        )
    candidate = candidates[0]
    place = _place_state(mention, candidate)
    if place != "match":
        signal = "place_conflict" if place == "conflict" else "place_missing"
        return _link(
            mention,
            "ambiguous",
            method="official_id_review",
            confidence=0,
            signals=("official_id", signal),
            limitation="The official ID could not be reconciled with a compatible stated place.",
        )
    return _link(
        mention,
        "official_exact",
        facility_id=candidate.facility_id,
        method="official_id_and_place",
        confidence=100,
        signals=("official_id", "facility_type", "place"),
        limitation="The link identifies a facility, not a separate building or completed project.",
    )


def _name_link(
    mention: FacilityMention, registry: tuple[FacilityRegistryRecord, ...]
) -> FacilityLink | None:
    name = _normalize(mention.facility_name)
    if not name:
        return None
    candidates = tuple(
        record
        for record in registry
        if record.facility_type == mention.facility_type
        and _normalize(record.official_name) == name
    )
    compatible = tuple(record for record in candidates if _place_state(mention, record) == "match")
    if len(compatible) == 1:
        return _link(
            mention,
            "official_exact",
            facility_id=compatible[0].facility_id,
            method="exact_name_and_place",
            confidence=95,
            signals=("exact_name", "facility_type", "place"),
            limitation="The link identifies a facility, not a separate building or completed project.",
        )
    if candidates:
        signal = "multiple_exact_names" if len(candidates) > 1 else "place_conflict"
        if all(_place_state(mention, record) == "missing" for record in candidates):
            place_signal = "place_missing"
        else:
            place_signal = "place_conflict"
        return _link(
            mention,
            "ambiguous",
            method="exact_name_review",
            confidence=0,
            signals=(signal, place_signal),
            limitation="The exact facility name did not resolve to one compatible registry place.",
        )
    return None


def _group_link(mention: FacilityMention) -> FacilityLink:
    name = _normalize(mention.facility_name)
    place = _normalize(mention.municipality or mention.province or mention.region)
    if not name or not place:
        return _link(
            mention,
            "unlinked",
            method="insufficient_identity_fields",
            confidence=0,
            signals=("name_or_place_missing",),
            limitation="A facility name and place are required before records can be grouped safely.",
        )
    digest = hashlib.sha256(f"{mention.facility_type}\x1f{name}\x1f{place}".encode()).hexdigest()
    return _link(
        mention,
        "group_only",
        group_key=f"facility-group:{digest}",
        method="normalized_name_and_place",
        confidence=70,
        signals=("normalized_name", "normalized_place"),
        limitation="This is a record group, not an official facility identity or building count.",
    )


def link_facility(
    mention: FacilityMention,
    registry: tuple[FacilityRegistryRecord, ...],
) -> FacilityLink:
    """Link one mention without fuzzy matching or forced identity selection."""

    return (
        _official_id_link(mention, registry)
        or _name_link(mention, registry)
        or _group_link(mention)
    )


def _school_name(value: str) -> str:
    normalized = _normalize(value)
    replacements = (
        (r"\bes\b", "elementary school"),
        (r"\bnhs\b", "national high school"),
        (r"\bhs\b", "high school"),
        (r"\bcs\b", "central school"),
        (r"\bis\b", "integrated school"),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    return " ".join(normalized.split())


def _place_aliases(value: str) -> tuple[str, ...]:
    normalized = _normalize(value)
    without_capital = re.sub(r"\bcapital\b", "", normalized).strip()
    aliases = {normalized, without_capital}
    if without_capital.startswith("city of "):
        name = without_capital.removeprefix("city of ").strip()
        aliases.update((name, f"{name} city"))
    return tuple(sorted(alias for alias in aliases if alias))


def _contains(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def _title_link(
    record: FacilityTitleRecord,
    state: MatchState,
    *,
    name: str,
    facility_id: str | None = None,
    confidence: int = 0,
    signals: tuple[str, ...],
    limitation: str,
) -> FacilityLink:
    return FacilityLink(
        source_type=record.source_type,
        record_id=record.record_id,
        match_state=state,
        facility_id=facility_id,
        record_group_key=None,
        record_group_label=name,
        match_method="exact_registry_name_and_place" if state == "official_exact" else "registry_title_review",
        confidence=confidence,
        signals=signals,
        limitation=limitation,
    )


def link_school_title(
    record: FacilityTitleRecord,
    registry: tuple[FacilityRegistryRecord, ...],
) -> FacilityLink:
    """Match a title only when an exact normalized registry name and place agree."""

    title = _school_name(record.title)
    context = _normalize(f"{record.title} {record.location}")
    name_candidates = tuple(
        facility
        for facility in registry
        if facility.facility_type == "school"
        and _contains(title, _school_name(facility.official_name))
    )
    place_candidates = tuple(
        facility
        for facility in name_candidates
        if any(_contains(context, place) for place in _place_aliases(facility.municipality))
    )
    if len(place_candidates) == 1:
        facility = place_candidates[0]
        return _title_link(
            record, "official_exact", name=facility.official_name,
            facility_id=facility.facility_id, confidence=95,
            signals=("exact_registry_name_in_title", "place_in_record"),
            limitation="The link identifies one listed school, not a building or completed project.",
        )
    if name_candidates:
        return _title_link(
            record, "ambiguous", name=name_candidates[0].official_name,
            signals=("exact_registry_name_in_title", "place_missing_or_ambiguous"),
            limitation="The title matched a registry name but not one compatible place.",
        )
    return _title_link(
        record, "unlinked", name="",
        signals=("no_exact_registry_name",),
        limitation="No exact scoped registry name was found in the record title.",
    )
