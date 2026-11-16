"""Validated PSA population context for community-level public spending review."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

SHA256 = re.compile(r"[0-9a-f]{64}")
PSGC = re.compile(r"[0-9]{10}")
LEVEL_BY_DEPTH = {
    2: "region",
    4: "province_or_huc",
    6: "city_or_municipality",
    8: "barangay",
}
EXPECTED_DIMENSIONS = ["Geographic Location", "Parameter"]
DIMENSION_COUNT = 2
MEASURE_COUNT = 3
REGION_DEPTH = 2
EXPECTED_PARAMETERS = {
    "0": "Total Population",
    "1": "Household Population",
    "2": "Number of Households",
}


@dataclass(frozen=True, slots=True)
class PopulationPlace:
    psgc_code: str
    parent_psgc_code: str | None
    name: str
    geographic_level: str
    total_population: int
    household_population: int
    households: int
    source_sha256: str
    source_url: str


@dataclass(frozen=True, slots=True)
class PopulationHierarchyGap:
    parent_psgc_code: str
    unallocated_population: int
    unallocated_household_population: int
    unallocated_households: int


@dataclass(frozen=True, slots=True)
class PopulationTable:
    region_code: str
    source_sha256: str
    source_url: str
    source_updated_at: str
    records: tuple[PopulationPlace, ...]
    excluded_out_of_region: int
    hierarchy_gaps: tuple[PopulationHierarchyGap, ...]


@dataclass(frozen=True, slots=True)
class PopulationSnapshot:
    records: tuple[PopulationPlace, ...]
    national_population: int
    national_household_population: int
    national_households: int
    national_source_sha256: str
    source_sha256: tuple[str, ...]
    snapshot_sha256: str
    region_count: int
    place_count: int
    barangay_count: int
    excluded_out_of_region: int
    hierarchy_gaps: tuple[PopulationHierarchyGap, ...]
    national_unallocated_population: int
    national_unallocated_household_population: int
    national_unallocated_households: int

    @property
    def total_population(self) -> int:
        return self.national_population


@dataclass(frozen=True, slots=True)
class NationalPopulationControl:
    total_population: int
    household_population: int
    households: int
    source_sha256: str
    source_url: str
    source_updated_at: str


def openstat_population_query() -> dict[str, object]:
    """Return the fixed query used for all regional 2024 population tables."""

    return {
        "query": [
            {
                "code": "Geographic Location",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "Parameter",
                "selection": {"filter": "item", "values": ["0", "1", "2"]},
            },
        ],
        "response": {"format": "json-stat"},
    }


def openstat_national_population_query() -> dict[str, object]:
    """Return the fixed query for the national 2024 population controls."""

    query = openstat_population_query()
    query["query"][0]["selection"] = {
        "filter": "item",
        "values": ["0000000000"],
    }
    return query


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"population {label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"population {label} must be a list")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"population {label} must be non-empty text")
    return value.strip()


def _validate_source(source_sha256: str, source_url: str) -> None:
    if not SHA256.fullmatch(source_sha256):
        raise ValueError("population source hash must be lowercase SHA-256")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != "openstat.psa.gov.ph":
        raise ValueError("population source URL must use PSA OpenSTAT")


def _ordered_codes(category: dict[str, Any]) -> tuple[str, ...]:
    index = _object(category.get("index"), "geography index")
    if not index or any(
        not isinstance(code, str) or not isinstance(position, int) or isinstance(position, bool)
        for code, position in index.items()
    ):
        raise ValueError("population geography index is invalid")
    positions = sorted(index.values())
    if positions != list(range(len(index))):
        raise ValueError("population geography index must be contiguous")
    return tuple(sorted(index, key=index.__getitem__))


def _measure(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"population {label} must be a nonnegative integer")
    return value


def _parse_record(
    code: str,
    raw_label: Any,
    measures: list[Any],
    parents: dict[int, str],
    source_sha256: str,
    source_url: str,
) -> PopulationPlace:
    if not PSGC.fullmatch(code):
        raise ValueError("population geography code must be a 10-digit PSGC")
    label = _text(raw_label, "geography label")
    depth = len(label) - len(label.lstrip("."))
    manila_submunicipality = depth == 0 and code.startswith("13806") and code.endswith("000")
    if manila_submunicipality:
        depth = 6
    level = "submunicipality" if manila_submunicipality else LEVEL_BY_DEPTH.get(depth)
    if level is None:
        raise ValueError("population geography label has an unsupported level")
    name = label if manila_submunicipality else label[depth:].strip()
    if not name:
        raise ValueError("population geography name must not be empty")
    parent_code = None
    if depth > REGION_DEPTH:
        parent_depths = tuple(
            item
            for item, parent in parents.items()
            if item < depth and code.startswith(parent.rstrip("0"))
        )
        if not parent_depths:
            raise ValueError("population geography hierarchy is incomplete")
        parent_code = parents[max(parent_depths)]
    parents[depth] = code
    for child_depth in tuple(parents):
        if child_depth > depth:
            parents.pop(child_depth)
    total = _measure(measures[0], "total population")
    household_population = _measure(measures[1], "household population")
    households = _measure(measures[2], "households")
    if household_population > total:
        raise ValueError("population household population exceeds total population")
    if households > household_population:
        raise ValueError("population households exceed household population")
    return PopulationPlace(
        code,
        parent_code,
        name,
        level,
        total,
        household_population,
        households,
        source_sha256,
        source_url,
    )


def _reconcile_place_hierarchy(
    records: tuple[PopulationPlace, ...],
) -> tuple[PopulationHierarchyGap, ...]:
    children: dict[str, list[PopulationPlace]] = {}
    for record in records:
        if record.parent_psgc_code is not None:
            children.setdefault(record.parent_psgc_code, []).append(record)
    by_code = {record.psgc_code: record for record in records}
    gaps = []
    for parent_code, child_records in children.items():
        parent = by_code[parent_code]
        child_totals = (
            sum(record.total_population for record in child_records),
            sum(record.household_population for record in child_records),
            sum(record.households for record in child_records),
        )
        parent_totals = (
            parent.total_population,
            parent.household_population,
            parent.households,
        )
        if any(
            child > parent_value
            for child, parent_value in zip(child_totals, parent_totals, strict=True)
        ):
            raise ValueError(f"population child totals exceed parent {parent.psgc_code}")
        if child_totals != parent_totals:
            gaps.append(
                PopulationHierarchyGap(
                    parent.psgc_code,
                    parent_totals[0] - child_totals[0],
                    parent_totals[1] - child_totals[1],
                    parent_totals[2] - child_totals[2],
                )
            )
    return tuple(gaps)


def parse_population_table(
    payload: bytes,
    *,
    source_sha256: str,
    source_url: str,
) -> PopulationTable:
    """Parse and validate one regional PSA 2024 population table."""

    _validate_source(source_sha256, source_url)
    try:
        document = _object(json.loads(payload.decode("utf-8-sig")), "document")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("population response must be valid JSON") from exc
    dataset = _object(document.get("dataset"), "dataset")
    dimension = _object(dataset.get("dimension"), "dimension")
    if dimension.get("id") != EXPECTED_DIMENSIONS:
        raise ValueError("population dimensions are invalid")
    size = _list(dimension.get("size"), "dimension size")
    if (
        len(size) != DIMENSION_COUNT
        or size[1] != MEASURE_COUNT
        or not isinstance(size[0], int)
        or size[0] <= 0
    ):
        raise ValueError("population dimension size is invalid")
    geography = _object(dimension.get("Geographic Location"), "geography dimension")
    geography_category = _object(geography.get("category"), "geography category")
    labels = _object(geography_category.get("label"), "geography labels")
    codes = _ordered_codes(geography_category)
    if len(codes) != size[0] or set(labels) != set(codes):
        raise ValueError("population geography labels do not match the index")
    first_label = _text(labels[codes[0]], "first geography label")
    if len(first_label) - len(first_label.lstrip(".")) != REGION_DEPTH:
        raise ValueError("population first place must be a region")
    parameter = _object(dimension.get("Parameter"), "parameter dimension")
    parameter_category = _object(parameter.get("category"), "parameter category")
    if parameter_category.get("index") != {"0": 0, "1": 1, "2": 2}:
        raise ValueError("population parameter order is invalid")
    if parameter_category.get("label") != EXPECTED_PARAMETERS:
        raise ValueError("population parameters are invalid")
    values = _list(dataset.get("value"), "values")
    if len(values) != len(codes) * MEASURE_COUNT:
        raise ValueError("population value count does not match its dimensions")
    parents: dict[int, str] = {}
    region_prefix = codes[0][:2]
    active = tuple(
        (source_index, code)
        for source_index, code in enumerate(codes)
        if code.startswith(region_prefix)
    )
    records = tuple(
        _parse_record(
            code,
            labels[code],
            values[source_index * MEASURE_COUNT : source_index * MEASURE_COUNT + MEASURE_COUNT],
            parents,
            source_sha256,
            source_url,
        )
        for source_index, code in active
    )
    if records[0].geographic_level != "region":
        raise ValueError("population first place must be a region")
    if sum(record.geographic_level == "region" for record in records) != 1:
        raise ValueError("population table must contain exactly one region")
    region_code = records[0].psgc_code
    hierarchy_gaps = _reconcile_place_hierarchy(records)
    return PopulationTable(
        region_code,
        source_sha256,
        source_url,
        _text(dataset.get("updated"), "source update time"),
        records,
        len(codes) - len(active),
        hierarchy_gaps,
    )


def parse_national_population_control(
    payload: bytes,
    *,
    source_sha256: str,
    source_url: str,
) -> NationalPopulationControl:
    """Read the three national controls from the dedicated PSA table response."""

    _validate_source(source_sha256, source_url)
    try:
        document = _object(json.loads(payload.decode("utf-8-sig")), "document")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("population response must be valid JSON") from exc
    dataset = _object(document.get("dataset"), "dataset")
    dimension = _object(dataset.get("dimension"), "dimension")
    if dimension.get("id") != EXPECTED_DIMENSIONS or dimension.get("size") != [1, 3]:
        raise ValueError("population national control dimensions are invalid")
    geography = _object(dimension.get("Geographic Location"), "geography dimension")
    geography_category = _object(geography.get("category"), "geography category")
    if geography_category.get("index") != {"0000000000": 0}:
        raise ValueError("population national control code is invalid")
    parameter = _object(dimension.get("Parameter"), "parameter dimension")
    parameter_category = _object(parameter.get("category"), "parameter category")
    if parameter_category.get("index") != {"0": 0, "1": 1, "2": 2}:
        raise ValueError("population parameter order is invalid")
    if parameter_category.get("label") != EXPECTED_PARAMETERS:
        raise ValueError("population parameters are invalid")
    values = _list(dataset.get("value"), "values")
    if len(values) != MEASURE_COUNT:
        raise ValueError("population national control values are incomplete")
    total, household_population, households = (
        _measure(value, "national control") for value in values
    )
    if household_population > total or households > household_population:
        raise ValueError("population national controls are inconsistent")
    return NationalPopulationControl(
        total,
        household_population,
        households,
        source_sha256,
        source_url,
        _text(dataset.get("updated"), "source update time"),
    )


def build_population_snapshot(
    tables: tuple[PopulationTable, ...],
    *,
    national_population: int,
    national_household_population: int,
    national_households: int,
    national_source_sha256: str,
) -> PopulationSnapshot:
    """Combine regional tables only when their totals match the national controls."""

    if not tables:
        raise ValueError("population tables must not be empty")
    if not SHA256.fullmatch(national_source_sha256):
        raise ValueError("population national source hash must be lowercase SHA-256")
    controls = (
        _measure(national_population, "national total"),
        _measure(national_household_population, "national household total"),
        _measure(national_households, "national household count"),
    )
    region_codes = [table.region_code for table in tables]
    records = tuple(record for table in tables for record in table.records)
    codes = [record.psgc_code for record in records]
    if len(set(region_codes)) != len(region_codes) or len(set(codes)) != len(codes):
        raise ValueError("population region and place codes must be unique")
    regions = tuple(record for record in records if record.geographic_level == "region")
    totals = (
        sum(record.total_population for record in regions),
        sum(record.household_population for record in regions),
        sum(record.households for record in regions),
    )
    if any(total > control for total, control in zip(totals, controls, strict=True)):
        raise ValueError("population regional totals exceed the national control")
    control_gaps = tuple(control - total for total, control in zip(totals, controls, strict=True))
    source_hashes = tuple(table.source_sha256 for table in tables) + (national_source_sha256,)
    snapshot_sha256 = hashlib.sha256("\n".join(source_hashes).encode()).hexdigest()
    return PopulationSnapshot(
        records=records,
        national_population=controls[0],
        national_household_population=controls[1],
        national_households=controls[2],
        national_source_sha256=national_source_sha256,
        source_sha256=source_hashes,
        snapshot_sha256=snapshot_sha256,
        region_count=len(regions),
        place_count=len(records),
        barangay_count=sum(record.geographic_level == "barangay" for record in records),
        excluded_out_of_region=sum(table.excluded_out_of_region for table in tables),
        hierarchy_gaps=tuple(gap for table in tables for gap in table.hierarchy_gaps),
        national_unallocated_population=control_gaps[0],
        national_unallocated_household_population=control_gaps[1],
        national_unallocated_households=control_gaps[2],
    )
