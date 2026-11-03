"""Build an exact, full-universe contract acquisition inventory."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyarrow.parquet as pq

from engine.budget_watchdog.contract_evidence import STAGES
from engine.budget_watchdog.models import validate_fiscal_year
from engine.budget_watchdog.money import parse_centavos

CONTRACT_ID = re.compile(r"\d{2}[A-Z]{1,5}\d{3,6}")
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
DELIVERY_COLUMNS = (
    "contractId",
    "description",
    "category",
    "status",
    "budget",
    "location",
    "infraYear",
)
AWARD_COLUMNS = (
    "id",
    "reference_id",
    "contract_no",
    "award_title",
    "notice_title",
    "awardee_name",
    "organization_name",
    "area_of_delivery",
    "business_category",
    "contract_amount",
    "award_date",
    "award_status",
)


class AcquisitionUniverseError(ValueError):
    """Raised when a source cannot support deterministic universe matching."""


@dataclass(frozen=True, slots=True)
class UniverseContract:
    contract_id: str
    fiscal_year: int
    description: str
    category: str
    delivery_status: str
    budget_centavos: int
    province: str
    region: str
    identifier_status: str
    year_alignment: str
    match_state: str = "no_exact_row"
    accepted_match_rows: int = 0
    quarantined_match_rows: int = 0


@dataclass(frozen=True, slots=True)
class AwardMatch:
    source_row_id: str
    contract_id: str
    match_basis: str
    reference_id: str | None
    contract_no: str | None
    award_title: str | None
    notice_title: str
    awardee_name: str
    organization_name: str
    area_of_delivery: str
    business_category: str
    contract_amount_centavos: int
    award_date: str
    award_status: str
    row_sha256: str


@dataclass(frozen=True, slots=True)
class QuarantinedAwardRow:
    source_row_id: str
    candidate_contract_ids: tuple[str, ...]
    reason: str
    row_sha256: str
    reference_id: str | None
    contract_no: str | None
    award_title: str | None
    notice_title: str


@dataclass(frozen=True, slots=True)
class AcquisitionUniverseSummary:
    contract_count: int
    source_row_count: int
    accepted_match_rows: int
    quarantined_rows: int
    lifecycle_task_count: int
    state_counts: MappingProxyType[str, int]


@dataclass(frozen=True, slots=True)
class AcquisitionUniverseSnapshot:
    checked_on: date
    fiscal_years: tuple[int, ...]
    delivery_sha256: str
    award_sha256: str
    award_revision: str
    contracts: tuple[UniverseContract, ...]
    matches: tuple[AwardMatch, ...]
    quarantine: tuple[QuarantinedAwardRow, ...]
    summary: AcquisitionUniverseSummary


def _text(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AcquisitionUniverseError(f"{field} must be non-empty text")
    return value.strip()


def _digest(value: str, pattern: re.Pattern[str], field: str) -> str:
    if pattern.fullmatch(value) is None:
        raise AcquisitionUniverseError(f"{field} has an invalid digest")
    return value


def _delivery_contract(row: dict[str, Any]) -> UniverseContract:
    contract_id = str(_text(row.get("contractId"), "contractId")).upper()
    year_text = _text(row.get("infraYear"), "infraYear")
    if not str(year_text).isdigit():
        raise AcquisitionUniverseError("infraYear must be numeric text")
    fiscal_year = int(str(year_text))
    validate_fiscal_year(fiscal_year)
    location = row.get("location")
    if not isinstance(location, dict):
        raise AcquisitionUniverseError("location must be an object")
    amount = parse_centavos(Decimal(str(row.get("budget"))))
    identifier_status = "valid" if CONTRACT_ID.fullmatch(contract_id) else "invalid"
    year_alignment = "aligned" if contract_id.startswith(str(fiscal_year)[-2:]) else "conflict"
    return UniverseContract(
        contract_id=contract_id,
        fiscal_year=fiscal_year,
        description=str(_text(row.get("description"), "description")),
        category=str(_text(row.get("category"), "category")),
        delivery_status=str(_text(row.get("status"), "status")),
        budget_centavos=amount,
        province=str(_text(location.get("province"), "province", optional=True) or ""),
        region=str(_text(location.get("region"), "region", optional=True) or ""),
        identifier_status=identifier_status,
        year_alignment=year_alignment,
    )


def _load_contracts(path: Path, fiscal_years: tuple[int, ...]) -> tuple[UniverseContract, ...]:
    try:
        table = pq.read_table(
            path,
            columns=list(DELIVERY_COLUMNS),
            filters=[("infraYear", "in", [str(year) for year in fiscal_years])],
        )
    except Exception as exc:
        raise AcquisitionUniverseError("cannot read delivery universe schema") from exc
    contracts = tuple(_delivery_contract(row) for row in table.to_pylist())
    identifiers = [item.contract_id for item in contracts]
    if len(identifiers) != len(set(identifiers)):
        raise AcquisitionUniverseError("delivery contract identifiers must be unique")
    return tuple(sorted(contracts, key=lambda item: item.contract_id))


def _normalized_candidate(value: Any, universe: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if normalized in universe else None


def _canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in AWARD_COLUMNS:
        value = row.get(key)
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = str(value) if key == "id" and value is not None else value
    return result


def _row_digest(row: dict[str, Any]) -> str:
    payload = json.dumps(
        _canonical_row(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _award_match(row: dict[str, Any], contract_id: str, basis: str) -> AwardMatch:
    award_date = row.get("award_date")
    if not isinstance(award_date, (date, datetime)):
        raise AcquisitionUniverseError("award_date must be a date")
    amount = parse_centavos(Decimal(str(row.get("contract_amount"))))
    return AwardMatch(
        source_row_id=str(row.get("id")),
        contract_id=contract_id,
        match_basis=basis,
        reference_id=_text(row.get("reference_id"), "reference_id", optional=True),
        contract_no=_text(row.get("contract_no"), "contract_no", optional=True),
        award_title=_text(row.get("award_title"), "award_title", optional=True),
        notice_title=str(_text(row.get("notice_title"), "notice_title", optional=True) or ""),
        awardee_name=str(_text(row.get("awardee_name"), "awardee_name")),
        organization_name=str(
            _text(row.get("organization_name"), "organization_name", optional=True) or ""
        ),
        area_of_delivery=str(
            _text(row.get("area_of_delivery"), "area_of_delivery", optional=True) or ""
        ),
        business_category=str(
            _text(row.get("business_category"), "business_category", optional=True) or ""
        ),
        contract_amount_centavos=amount,
        award_date=award_date.date().isoformat()
        if isinstance(award_date, datetime)
        else award_date.isoformat(),
        award_status=str(_text(row.get("award_status"), "award_status")),
        row_sha256=_row_digest(row),
    )


def _classify_award_row(
    row: dict[str, Any], universe: set[str]
) -> AwardMatch | QuarantinedAwardRow | None:
    structured = {
        candidate
        for field in ("reference_id", "contract_no")
        if (candidate := _normalized_candidate(row.get(field), universe)) is not None
    }
    title = _normalized_candidate(row.get("award_title"), universe)
    candidates = structured | ({title} if title is not None else set())
    if not candidates:
        return None
    if len(candidates) > 1:
        return QuarantinedAwardRow(
            source_row_id=str(row.get("id")),
            candidate_contract_ids=tuple(sorted(candidates)),
            reason="conflicting_exact_identifiers",
            row_sha256=_row_digest(row),
            reference_id=_text(row.get("reference_id"), "reference_id", optional=True),
            contract_no=_text(row.get("contract_no"), "contract_no", optional=True),
            award_title=_text(row.get("award_title"), "award_title", optional=True),
            notice_title=str(_text(row.get("notice_title"), "notice_title", optional=True) or ""),
        )
    contract_id = next(iter(candidates))
    basis = "structured_exact" if contract_id in structured else "title_exact"
    try:
        return _award_match(row, contract_id, basis)
    except (AcquisitionUniverseError, ValueError) as exc:
        return QuarantinedAwardRow(
            source_row_id=str(row.get("id")),
            candidate_contract_ids=(contract_id,),
            reason=f"invalid_matched_row:{exc}",
            row_sha256=_row_digest(row),
            reference_id=(str(row["reference_id"]) if row.get("reference_id") else None),
            contract_no=(str(row["contract_no"]) if row.get("contract_no") else None),
            award_title=(str(row["award_title"]) if row.get("award_title") else None),
            notice_title=str(row.get("notice_title") or ""),
        )


def _scan_awards(
    path: Path, universe: set[str]
) -> tuple[int, tuple[AwardMatch, ...], tuple[QuarantinedAwardRow, ...]]:
    matches: list[AwardMatch] = []
    quarantine: list[QuarantinedAwardRow] = []
    source_rows = 0
    try:
        parquet = pq.ParquetFile(path)
        batches = parquet.iter_batches(batch_size=100_000, columns=list(AWARD_COLUMNS))
        for batch in batches:
            source_rows += batch.num_rows
            for row in batch.to_pylist():
                result = _classify_award_row(row, universe)
                if isinstance(result, AwardMatch):
                    matches.append(result)
                elif isinstance(result, QuarantinedAwardRow):
                    quarantine.append(result)
    except Exception as exc:
        if isinstance(exc, AcquisitionUniverseError):
            raise
        raise AcquisitionUniverseError("cannot read award mirror schema") from exc
    return (
        source_rows,
        tuple(sorted(matches, key=lambda item: (item.contract_id, item.source_row_id))),
        tuple(sorted(quarantine, key=lambda item: item.source_row_id)),
    )


def _apply_states(
    contracts: tuple[UniverseContract, ...],
    matches: tuple[AwardMatch, ...],
    quarantine: tuple[QuarantinedAwardRow, ...],
) -> tuple[UniverseContract, ...]:
    accepted = Counter(item.contract_id for item in matches)
    bases: dict[str, set[str]] = defaultdict(set)
    for item in matches:
        bases[item.contract_id].add(item.match_basis)
    conflicts = Counter(
        contract_id for item in quarantine for contract_id in item.candidate_contract_ids
    )
    result = []
    for item in contracts:
        count = accepted[item.contract_id]
        if item.identifier_status == "invalid":
            state = "invalid_identifier"
        elif conflicts[item.contract_id]:
            state = "conflict_review"
        elif count > 1:
            state = "multiple_exact_rows"
        elif count == 1 and "structured_exact" in bases[item.contract_id]:
            state = "structured_exact"
        elif count == 1:
            state = "title_exact"
        else:
            state = "no_exact_row"
        result.append(
            replace(
                item,
                match_state=state,
                accepted_match_rows=count,
                quarantined_match_rows=conflicts[item.contract_id],
            )
        )
    return tuple(result)


def build_acquisition_universe(
    delivery_path: Path,
    award_path: Path,
    *,
    fiscal_years: tuple[int, ...],
    delivery_sha256: str,
    award_sha256: str,
    award_revision: str,
    checked_on: date,
) -> AcquisitionUniverseSnapshot:
    if not fiscal_years or len(fiscal_years) != len(set(fiscal_years)):
        raise AcquisitionUniverseError("fiscal_years must be unique and non-empty")
    for fiscal_year in fiscal_years:
        validate_fiscal_year(fiscal_year)
    delivery_digest = _digest(delivery_sha256, SHA256, "delivery_sha256")
    award_digest = _digest(award_sha256, SHA256, "award_sha256")
    revision = _digest(award_revision, REVISION, "award_revision")
    contracts = _load_contracts(delivery_path, fiscal_years)
    universe = {item.contract_id for item in contracts if item.identifier_status == "valid"}
    source_rows, matches, quarantine = _scan_awards(award_path, universe)
    contracts = _apply_states(contracts, matches, quarantine)
    counts = Counter(item.match_state for item in contracts)
    summary = AcquisitionUniverseSummary(
        contract_count=len(contracts),
        source_row_count=source_rows,
        accepted_match_rows=len(matches),
        quarantined_rows=len(quarantine),
        lifecycle_task_count=len(contracts) * len(STAGES),
        state_counts=MappingProxyType(dict(sorted(counts.items()))),
    )
    return AcquisitionUniverseSnapshot(
        checked_on=checked_on,
        fiscal_years=tuple(fiscal_years),
        delivery_sha256=delivery_digest,
        award_sha256=award_digest,
        award_revision=revision,
        contracts=contracts,
        matches=matches,
        quarantine=quarantine,
        summary=summary,
    )
