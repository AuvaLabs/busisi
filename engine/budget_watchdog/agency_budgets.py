"""Deterministic FY2027 appropriation-head extraction and comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FISCAL_YEAR = 2027
BASELINE_YEAR = 2026
APPROPRIATION_HEAD_COUNT = 39
CONGRESS_INSTITUTION_COUNT = 5


@dataclass(frozen=True, slots=True)
class HouseHeadSpec:
    record_id: str
    public_name: str
    source_label: str
    document_key: str
    pdf_page: int


@dataclass(frozen=True, slots=True)
class HouseTotal:
    record_id: str
    public_name: str
    amount_pesos: int
    document_key: str
    pdf_page: int


@dataclass(frozen=True, slots=True)
class AgencyBudgetRecord:
    record_id: str
    fiscal_year: int
    baseline_year: int
    level: str
    parent_id: str | None
    code: str
    name: str
    base_centavos: int
    nep_centavos: int
    house_centavos: int | None
    difference_centavos: int | None
    change_bps: int | None
    stage_status: str
    house_document_key: str | None
    house_pages: tuple[int, ...]


HOUSE_HEAD_SPECS = (
    HouseHeadSpec(
        "01", "Congress of the Philippines", "CONGRESS OF THE PHILIPPINES", "house-ia", 25
    ),
    HouseHeadSpec("02", "Office of the President", "OFFICE OF THE PRESIDENT", "house-ia", 30),
    HouseHeadSpec(
        "03", "Office of the Vice-President", "OFFICE OF THE VICE-PRESIDENT", "house-ia", 34
    ),
    HouseHeadSpec(
        "04", "Department of Agrarian Reform", "DEPARTMENT OF AGRARIAN REFORM", "house-ia", 86
    ),
    HouseHeadSpec("05", "Department of Agriculture", "DEPARTMENT OF AGRICULTURE", "house-ia", 196),
    HouseHeadSpec(
        "06",
        "Department of Budget and Management",
        "DEPARTMENT OF BUDGET AND MANAGEMENT",
        "house-ia",
        207,
    ),
    HouseHeadSpec("07", "Department of Education", "DEPARTMENT OF EDUCATION", "house-ia", 476),
    HouseHeadSpec(
        "08", "State Universities and Colleges", "STATE UNIVERSITIES AND COLLEGES", "house-ia", 866
    ),
    HouseHeadSpec("09", "Department of Energy", "DEPARTMENT OF ENERGY", "house-ia", 872),
    HouseHeadSpec(
        "10",
        "Department of Environment and Natural Resources",
        "DEPARTMENT OF ENVIRONMENT AND NATURAL RESOURCES",
        "house-ia",
        976,
    ),
    HouseHeadSpec("11", "Department of Finance", "DEPARTMENT OF FINANCE", "house-ia", 1018),
    HouseHeadSpec(
        "12", "Department of Foreign Affairs", "DEPARTMENT OF FOREIGN AFFAIRS", "house-ia", 1037
    ),
    HouseHeadSpec("13", "Department of Health", "DEPARTMENT OF HEALTH", "house-ia", 1089),
    HouseHeadSpec(
        "14",
        "Department of the Interior and Local Government",
        "DEPARTMENT OF THE INTERIOR AND LOCAL GOVERNMENT",
        "house-ia",
        1196,
    ),
    HouseHeadSpec("15", "Department of Justice", "DEPARTMENT OF JUSTICE", "house-ia", 1234),
    HouseHeadSpec(
        "16",
        "Department of Labor and Employment",
        "DEPARTMENT OF LABOR AND EMPLOYMENT",
        "house-ia",
        1285,
    ),
    HouseHeadSpec(
        "17", "Department of National Defense", "DEPARTMENT OF NATIONAL DEFENSE", "house-ia", 1339
    ),
    HouseHeadSpec(
        "18",
        "Department of Public Works and Highways",
        "DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS",
        "house-ib",
        113,
    ),
    HouseHeadSpec(
        "19",
        "Department of Science and Technology",
        "DEPARTMENT OF SCIENCE AND TECHNOLOGY",
        "house-ib",
        177,
    ),
    HouseHeadSpec(
        "20",
        "Department of Social Welfare and Development",
        "DEPARTMENT OF SOCIAL WELFARE AND DEVELOPMENT",
        "house-ib",
        211,
    ),
    HouseHeadSpec("21", "Department of Tourism", "DEPARTMENT OF TOURISM", "house-ib", 231),
    HouseHeadSpec(
        "22",
        "Department of Trade and Industry",
        "DEPARTMENT OF TRADE AND INDUSTRY",
        "house-ib",
        273,
    ),
    HouseHeadSpec(
        "24",
        "Department of Economy, Planning, and Development",
        "DEPARTMENT OF ECONOMY, PLANNING, AND DEVELOPMENT",
        "house-ia",
        269,
    ),
    HouseHeadSpec(
        "25",
        "Presidential Communications Office",
        "PRESIDENTIAL COMMUNICATIONS OFFICE",
        "house-ib",
        346,
    ),
    HouseHeadSpec("26", "Other Executive Offices", "OTHER EXECUTIVE OFFICES", "house-ib", 454),
    HouseHeadSpec("29", "The Judiciary", "THE JUDICIARY", "house-ib", 472),
    HouseHeadSpec("30", "Civil Service Commission", "CIVIL SERVICE COMMISSION", "house-ib", 488),
    HouseHeadSpec("31", "Commission on Audit", "COMMISSION ON AUDIT", "house-ib", 502),
    HouseHeadSpec("32", "Commission on Elections", "COMMISSION ON ELECTIONS", "house-ib", 510),
    HouseHeadSpec("33", "Office of the Ombudsman", "OFFICE OF THE OMBUDSMAN", "house-ib", 516),
    HouseHeadSpec(
        "34", "Commission on Human Rights", "COMMISSION ON HUMAN RIGHTS", "house-ib", 523
    ),
    HouseHeadSpec(
        "35",
        "Budgetary Support to Government Corporations",
        "BUDGETARY SUPPORT TO GOVERNMENT CORPORATIONS",
        "house-ib",
        583,
    ),
    HouseHeadSpec(
        "36",
        "Allocations to Local Government Units",
        "ALLOCATIONS TO LOCAL GOVERNMENT UNITS",
        "house-ib",
        598,
    ),
    HouseHeadSpec(
        "37",
        "Department of Information and Communications Technology",
        "DEPARTMENT OF INFORMATION AND COMMUNICATIONS TECHNOLOGY",
        "house-ia",
        1122,
    ),
    HouseHeadSpec(
        "38", "Department of Transportation", "DEPARTMENT OF TRANSPORTATION", "house-ib", 326
    ),
    HouseHeadSpec(
        "39",
        "Department of Human Settlements and Urban Development",
        "DEPARTMENT OF HUMAN SETTLEMENTS AND URBAN DEVELOPMENT",
        "house-ia",
        1106,
    ),
    HouseHeadSpec(
        "40", "Department of Migrant Workers", "DEPARTMENT OF MIGRANT WORKERS", "house-ia", 1299
    ),
)

HOUSE_SPF_SPECS = (
    HouseHeadSpec("SPF:CF", "Contingent Fund", "CONTINGENT FUND", "house-ib", 601),
    HouseHeadSpec(
        "SPF:MPBF",
        "Miscellaneous Personnel Benefits Fund",
        "MISCELLANEOUS PERSONNEL BENEFITS FUND",
        "house-ib",
        604,
    ),
    HouseHeadSpec(
        "SPF:NDRRMF",
        "National Disaster Risk Reduction and Management Fund",
        "NATIONAL DISASTER RISK REDUCTION AND MANAGEMENT FUND",
        "house-ib",
        608,
    ),
    HouseHeadSpec(
        "SPF:PGF", "Pension and Gratuity Fund", "PENSION AND GRATUITY FUND", "house-ib", 611
    ),
    HouseHeadSpec(
        "SPF:RAFPMP",
        "Revised AFP Modernization Program",
        "REVISED AFP MODERNIZATION PROGRAM",
        "house-ib",
        614,
    ),
    HouseHeadSpec(
        "SPF:UA", "Unprogrammed Appropriations", "UNPROGRAMMED APPROPRIATIONS", "house-ib", 618
    ),
)

HOUSE_CONGRESS_SPECS = (
    HouseHeadSpec("01:001", "Senate", "A. SENATE", "house-ia", 12),
    HouseHeadSpec(
        "01:002", "Senate Electoral Tribunal", "B. SENATE ELECTORAL TRIBUNAL", "house-ia", 14
    ),
    HouseHeadSpec(
        "01:003",
        "Commission on Appointments",
        "PRESIDENTIAL APPOINTMENTS CONFIRMATION PROGRAM",
        "house-ia",
        17,
    ),
    HouseHeadSpec(
        "01:004", "House of Representatives", "D. HOUSE OF REPRESENTATIVES", "house-ia", 19
    ),
    HouseHeadSpec(
        "01:005",
        "House of Representatives Electoral Tribunal",
        "E. HOUSE OF REPRESENTATIVES ELECTORAL TRIBUNAL",
        "house-ia",
        22,
    ),
)

_AMOUNT = re.compile(r"P\s*([0-9][0-9,]*)")


def _normalized(value: str) -> str:
    return " ".join(value.upper().replace("–", "-").split())


def _content_line(value: str) -> str:
    value = re.sub(r"^\s*\d+\s+", "", value)
    return re.sub(r"\s+\d+\s*$", "", value)


def _page_total(page: str, spec: HouseHeadSpec) -> int:
    lines = page.splitlines()
    normalized_page = _normalized(" ".join(_content_line(line) for line in lines))
    if _normalized(spec.source_label) not in normalized_page:
        raise ValueError(f"House source label is missing on page {spec.pdf_page}: {spec.record_id}")
    totals: set[int] = set()
    for index, line in enumerate(lines):
        if "TOTAL NEW APPROPRIATIONS" not in _normalized(line):
            continue
        following = []
        for candidate in lines[index : index + 3]:
            if following and "TOTAL NEW APPROPRIATIONS" in _normalized(candidate):
                break
            following.append(candidate)
        segment = " ".join(following)
        amounts = _AMOUNT.findall(segment)
        if amounts:
            totals.add(int(amounts[-1].replace(",", "")))
    if len(totals) != 1:
        raise ValueError(
            f"House page must contain exactly one distinct peso total: {spec.record_id}"
        )
    return totals.pop()


def parse_house_totals(
    documents: dict[str, str], specs: tuple[HouseHeadSpec, ...]
) -> tuple[HouseTotal, ...]:
    """Extract a declared total from each exact PDF page and reject ambiguity."""

    pages_by_document = {key: value.split("\f") for key, value in documents.items()}
    records = []
    for spec in specs:
        pages = pages_by_document.get(spec.document_key)
        if pages is None or len(pages) < spec.pdf_page:
            raise ValueError(f"House source page is unavailable: {spec.record_id}")
        records.append(
            HouseTotal(
                spec.record_id,
                spec.public_name,
                _page_total(pages[spec.pdf_page - 1], spec),
                spec.document_key,
                spec.pdf_page,
            )
        )
    return tuple(records)


def _require_nep_payload(payload: dict[str, Any], *, department_id: str | None = None) -> None:
    meta = payload.get("meta", {})
    if (
        meta.get("dataset") != "nep"
        or meta.get("fiscal_year") != FISCAL_YEAR
        or meta.get("baseline_year") != BASELINE_YEAR
        or meta.get("currency") != "PHP"
        or meta.get("scale") != "pesos"
    ):
        raise ValueError("NEP metadata boundary is invalid")
    if department_id is not None and meta.get("department_id") != department_id:
        raise ValueError("NEP department boundary is invalid")


def _basis_points(difference: int, base: int) -> int | None:
    if base == 0:
        return None
    magnitude = (abs(difference) * 10_000 + base // 2) // base
    return magnitude if difference >= 0 else -magnitude


def _house_context(
    department_id: str, house_by_id: dict[str, HouseTotal]
) -> tuple[int | None, tuple[int, ...], str | None]:
    if department_id == "SPF":
        components = [house_by_id.get(spec.record_id) for spec in HOUSE_SPF_SPECS]
        if any(component is None for component in components):
            raise ValueError("House special purpose fund controls are incomplete")
        totals = tuple(component for component in components if component is not None)
        return (
            sum(component.amount_pesos for component in totals),
            tuple(component.pdf_page for component in totals),
            "house-ib",
        )
    if department_id == "AUTO":
        return None, (), None
    house = house_by_id.get(department_id)
    if house is None:
        raise ValueError(f"House appropriation head is missing: {department_id}")
    return house.amount_pesos, (house.pdf_page,), house.document_key


def _head_records(
    by_id: dict[str, dict[str, Any]], house_by_id: dict[str, HouseTotal]
) -> list[AgencyBudgetRecord]:
    records = []
    for department_id in sorted(by_id):
        row = by_id[department_id]
        house_pesos, pages, document_key = _house_context(department_id, house_by_id)
        nep_centavos = int(row["amount"]) * 100
        house_centavos = None if house_pesos is None else house_pesos * 100
        difference = None if house_centavos is None else house_centavos - nep_centavos
        records.append(
            AgencyBudgetRecord(
                f"head:{department_id}",
                FISCAL_YEAR,
                BASELINE_YEAR,
                "appropriation_head",
                None,
                department_id,
                str(row["description"]),
                int(row["base_amount"]) * 100,
                nep_centavos,
                house_centavos,
                difference,
                None if difference is None else _basis_points(difference, nep_centavos),
                "not_applicable" if house_centavos is None else "compared",
                document_key,
                pages,
            )
        )
    return records


def _congress_records(
    agencies: list[dict[str, Any]], house_by_id: dict[str, HouseTotal]
) -> list[AgencyBudgetRecord]:
    agency_by_code = {str(row.get("code")): row for row in agencies}
    if set(agency_by_code) != {"001", "002", "003", "004", "005"}:
        raise ValueError("NEP Congress institution identities are invalid")
    records = []
    for spec in HOUSE_CONGRESS_SPECS:
        code = spec.record_id.rsplit(":", 1)[-1]
        row = agency_by_code[code]
        house = house_by_id.get(spec.record_id)
        if house is None:
            raise ValueError(f"House Congress institution is missing: {code}")
        nep_centavos = int(row["amount"]) * 100
        house_centavos = house.amount_pesos * 100
        difference = house_centavos - nep_centavos
        records.append(
            AgencyBudgetRecord(
                f"congress:{code}",
                FISCAL_YEAR,
                BASELINE_YEAR,
                "congress_institution",
                "head:01",
                code,
                str(row["description"]),
                int(row["base_amount"]) * 100,
                nep_centavos,
                house_centavos,
                difference,
                _basis_points(difference, nep_centavos),
                "compared",
                house.document_key,
                (house.pdf_page,),
            )
        )
    return records


def build_agency_budget_records(
    departments_payload: dict[str, Any],
    congress_payload: dict[str, Any],
    house_totals: tuple[HouseTotal, ...],
) -> tuple[AgencyBudgetRecord, ...]:
    """Join exact appropriation-head identities and preserve unavailable stages."""

    _require_nep_payload(departments_payload)
    _require_nep_payload(congress_payload, department_id="01")
    departments = departments_payload.get("data")
    if not isinstance(departments, list) or len(departments) != APPROPRIATION_HEAD_COUNT:
        raise ValueError("NEP must contain all 39 appropriation heads")
    by_id = {str(row.get("id")): row for row in departments}
    if len(by_id) != len(departments):
        raise ValueError("NEP contains duplicate appropriation heads")
    expected_ids = {spec.record_id for spec in HOUSE_HEAD_SPECS} | {"SPF", "AUTO"}
    if set(by_id) != expected_ids:
        raise ValueError("NEP appropriation-head identity set is incomplete")
    house_by_id = {record.record_id: record for record in house_totals}
    if len(house_by_id) != len(house_totals):
        raise ValueError("House source contains duplicate comparison identities")

    agencies = congress_payload.get("data", {}).get("agencies")
    if not isinstance(agencies, list) or len(agencies) != CONGRESS_INSTITUTION_COUNT:
        raise ValueError("NEP Congress institution set is incomplete")
    return (*_head_records(by_id, house_by_id), *_congress_records(agencies, house_by_id))
