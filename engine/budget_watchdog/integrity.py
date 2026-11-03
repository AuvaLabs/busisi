"""Deterministic delivery-integrity signals and contractor aggregates."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

PCAB_SUFFIX = re.compile(r"\s*\((\d{3,})\)\s*$")
SPACE = re.compile(r"\s+")
PHILIPPINES_LATITUDE = (Decimal("4"), Decimal("22"))
PHILIPPINES_LONGITUDE = (Decimal("116"), Decimal("127"))
COMPLETE_PROGRESS = Decimal("100")
MINIMUM_DISTINCT_VALUES = 2


@dataclass(frozen=True, slots=True)
class ContractorIdentity:
    key: str
    display_name: str
    pcab_id: str


@dataclass(frozen=True, slots=True)
class DeliveryIntegrityRecord:
    contract_id: str
    fiscal_year: int
    description: str
    category: str
    status: str
    budget_centavos: int
    progress: str
    province: str
    region: str
    contractor: str
    start_date: date | None
    completion_date: date | None
    latitude: str | None
    longitude: str | None
    has_satellite_image: bool
    source_artifact_sha256: str

    def __post_init__(self) -> None:
        for field, value in (
            ("contract_id", self.contract_id),
            ("description", self.description),
            ("status", self.status),
        ):
            if not value.strip():
                raise ValueError(f"{field} must not be empty")
        _decimal(self.progress, "progress")


@dataclass(frozen=True, slots=True)
class IntegritySignal:
    contract_id: str
    fiscal_year: int
    code: str
    classification: str
    label: str
    description: str
    contractor_name: str
    pcab_id: str
    budget_centavos: int
    status: str
    progress: str
    province: str
    region: str
    latitude: str
    longitude: str
    evidence: str
    limitations: str
    source_artifact_sha256: str


@dataclass(frozen=True, slots=True)
class ContractorSummary:
    contractor_key: str
    contractor_name: str
    pcab_id: str
    project_count: int
    total_budget_centavos: int
    completed_count: int
    ongoing_count: int
    terminated_count: int
    first_year: int
    last_year: int


@dataclass(frozen=True, slots=True)
class IntegritySnapshot:
    signals: tuple[IntegritySignal, ...]
    contractors: tuple[ContractorSummary, ...]


@dataclass(slots=True)
class _ContractorAccumulator:
    identity: ContractorIdentity
    project_count: int = 0
    total_budget_centavos: int = 0
    completed_count: int = 0
    ongoing_count: int = 0
    terminated_count: int = 0
    first_year: int = 9999
    last_year: int = 0


def _decimal(value: str | None, field: str) -> Decimal:
    try:
        result = Decimal(value or "")
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _status(value: str) -> str:
    return SPACE.sub(" ", value.casefold().replace("-", " ")).strip()


def _canonical(value: str) -> str:
    return SPACE.sub(" ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def contractor_identity(value: str) -> ContractorIdentity:
    display = SPACE.sub(" ", value.strip())
    match = PCAB_SUFFIX.search(display)
    pcab_id = match.group(1) if match else ""
    if match:
        display = display[: match.start()].strip()
    if not display:
        display = "Contractor not stated"
    if pcab_id:
        return ContractorIdentity(f"pcab:{pcab_id}", display, pcab_id)
    digest = hashlib.sha256(_canonical(display).encode()).hexdigest()
    return ContractorIdentity(f"name:{digest}", display, "")


def _coordinate(record: DeliveryIntegrityRecord) -> tuple[Decimal, Decimal] | None:
    if record.latitude is None or record.longitude is None:
        return None
    return (_decimal(record.latitude, "latitude"), _decimal(record.longitude, "longitude"))


def _signal(
    record: DeliveryIntegrityRecord,
    *,
    code: str,
    classification: str,
    label: str,
    evidence: str,
    limitations: str,
) -> IntegritySignal:
    contractor = contractor_identity(record.contractor)
    return IntegritySignal(
        contract_id=record.contract_id,
        fiscal_year=record.fiscal_year,
        code=code,
        classification=classification,
        label=label,
        description=record.description,
        contractor_name=contractor.display_name,
        pcab_id=contractor.pcab_id,
        budget_centavos=record.budget_centavos,
        status=record.status,
        progress=record.progress,
        province=record.province,
        region=record.region,
        latitude=record.latitude or "",
        longitude=record.longitude or "",
        evidence=evidence,
        limitations=limitations,
        source_artifact_sha256=record.source_artifact_sha256,
    )


def _record_signals(record: DeliveryIntegrityRecord) -> list[IntegritySignal]:
    signals: list[IntegritySignal] = []
    status = _status(record.status)
    progress = _decimal(record.progress, "progress")
    coordinate = _coordinate(record)
    if status in {"ongoing", "on going"} and progress >= COMPLETE_PROGRESS:
        signals.append(
            _signal(
                record,
                code="status_progress_conflict",
                classification="source_conflict",
                label="Ongoing with 100% progress",
                evidence=f"Status is {record.status}; reported progress is {progress}%.",
                limitations="The status field may update later than the progress field.",
            )
        )
    if status == "completed" and progress < COMPLETE_PROGRESS:
        signals.append(
            _signal(
                record,
                code="completed_progress_conflict",
                classification="source_conflict",
                label="Completed below 100% progress",
                evidence=f"Status is Completed; reported progress is {progress}%.",
                limitations="The progress field may be stale or use a different reporting cutoff.",
            )
        )
    if record.start_date and record.completion_date and record.start_date > record.completion_date:
        signals.append(
            _signal(
                record,
                code="date_order_conflict",
                classification="source_conflict",
                label="Start date follows completion date",
                evidence=f"Start {record.start_date.isoformat()}; completion {record.completion_date.isoformat()}.",
                limitations="A source correction or date-field interpretation may resolve the conflict.",
            )
        )
    if status != "for procurement" and record.budget_centavos <= 0:
        signals.append(
            _signal(
                record,
                code="nonpositive_active_budget",
                classification="amount_review",
                label="Non-positive budget after procurement",
                evidence=f"Status is {record.status}; recorded project budget is not positive.",
                limitations="A zero value can reflect publication lag or a source-field omission.",
            )
        )
    if coordinate is None:
        signals.append(
            _signal(
                record,
                code="missing_coordinate",
                classification="coverage_gap",
                label="Coordinate not available",
                evidence="The archived DPWH record has no usable latitude and longitude pair.",
                limitations="Missing coordinates do not indicate that a project is missing on the ground.",
            )
        )
    elif not (
        PHILIPPINES_LATITUDE[0] <= coordinate[0] <= PHILIPPINES_LATITUDE[1]
        and PHILIPPINES_LONGITUDE[0] <= coordinate[1] <= PHILIPPINES_LONGITUDE[1]
    ):
        signals.append(
            _signal(
                record,
                code="coordinate_outside_philippines",
                classification="source_conflict",
                label="Coordinate outside broad Philippine bounds",
                evidence=f"Recorded coordinate is {coordinate[0]}, {coordinate[1]}.",
                limitations="Broad bounds are a screening rule and do not replace boundary validation.",
            )
        )
    if status == "completed" and not record.has_satellite_image:
        signals.append(
            _signal(
                record,
                code="completed_without_satellite_image",
                classification="coverage_gap",
                label="Completed without satellite imagery",
                evidence="The record is completed but the snapshot reports no satellite image.",
                limitations="Absence from this field is not proof that implementation evidence does not exist.",
            )
        )
    return signals


def _coordinate_signals(
    groups: dict[tuple[Decimal, Decimal], list[DeliveryIntegrityRecord]],
) -> list[IntegritySignal]:
    signals: list[IntegritySignal] = []
    for coordinate, records in sorted(groups.items()):
        descriptions = {_canonical(record.description) for record in records}
        if len(records) < MINIMUM_DISTINCT_VALUES or len(descriptions) < MINIMUM_DISTINCT_VALUES:
            continue
        contracts = ", ".join(sorted(record.contract_id for record in records))
        for record in records:
            signals.append(
                _signal(
                    record,
                    code="reused_coordinate",
                    classification="identity_review",
                    label="Coordinate reused by different descriptions",
                    evidence=f"Coordinate {coordinate[0]}, {coordinate[1]} is shared by: {contracts}.",
                    limitations="Shared coordinates can represent adjacent works or a common site and are not proof of duplicate funding.",
                )
            )
        locations = {(record.province.casefold(), record.region.casefold()) for record in records}
        if len(locations) < MINIMUM_DISTINCT_VALUES:
            continue
        for record in records:
            signals.append(
                _signal(
                    record,
                    code="coordinate_location_conflict",
                    classification="source_conflict",
                    label="Shared coordinate has conflicting location labels",
                    evidence=f"Coordinate {coordinate[0]}, {coordinate[1]} appears under multiple DPWH location labels.",
                    limitations="District-office labels can differ from physical administrative boundaries.",
                )
            )
    return signals


def _contractor_summaries(
    records: tuple[DeliveryIntegrityRecord, ...],
) -> tuple[ContractorSummary, ...]:
    accumulators: dict[str, _ContractorAccumulator] = {}
    for record in records:
        if not record.contractor.strip():
            continue
        identity = contractor_identity(record.contractor)
        accumulator = accumulators.setdefault(identity.key, _ContractorAccumulator(identity))
        accumulator.project_count += 1
        accumulator.total_budget_centavos += max(record.budget_centavos, 0)
        accumulator.first_year = min(accumulator.first_year, record.fiscal_year)
        accumulator.last_year = max(accumulator.last_year, record.fiscal_year)
        status = _status(record.status)
        accumulator.completed_count += status == "completed"
        accumulator.ongoing_count += status in {"ongoing", "on going"}
        accumulator.terminated_count += status == "terminated"
    return tuple(
        sorted(
            (
                ContractorSummary(
                    contractor_key=item.identity.key,
                    contractor_name=item.identity.display_name,
                    pcab_id=item.identity.pcab_id,
                    project_count=item.project_count,
                    total_budget_centavos=item.total_budget_centavos,
                    completed_count=item.completed_count,
                    ongoing_count=item.ongoing_count,
                    terminated_count=item.terminated_count,
                    first_year=item.first_year,
                    last_year=item.last_year,
                )
                for item in accumulators.values()
            ),
            key=lambda item: (
                -item.project_count,
                -item.total_budget_centavos,
                item.contractor_key,
            ),
        )
    )


def build_integrity_snapshot(
    records: tuple[DeliveryIntegrityRecord, ...],
) -> IntegritySnapshot:
    """Return stable rule outputs without an opaque combined risk score."""

    ordered = tuple(sorted(records, key=lambda record: record.contract_id))
    coordinate_groups: dict[tuple[Decimal, Decimal], list[DeliveryIntegrityRecord]] = defaultdict(
        list
    )
    signals: list[IntegritySignal] = []
    for record in ordered:
        signals.extend(_record_signals(record))
        coordinate = _coordinate(record)
        if coordinate is not None:
            coordinate_groups[coordinate].append(record)
    signals.extend(_coordinate_signals(coordinate_groups))
    return IntegritySnapshot(
        signals=tuple(sorted(signals, key=lambda item: (item.code, item.contract_id))),
        contractors=_contractor_summaries(ordered),
    )
