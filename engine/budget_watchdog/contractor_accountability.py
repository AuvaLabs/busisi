"""Deterministic contractor accountability evidence and timing signals."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
LOW_RATINGS = frozenset({"Poor", "Unsatisfactory"})
AWARD_MATCH_BASES = frozenset({"structured_exact", "title_exact"})
MAX_BASIS_POINTS = 10_000


@dataclass(frozen=True, slots=True)
class BlacklistEntity:
    reported_name: str
    order_count: int
    minimum_date: str
    maximum_date: str
    date_valid: bool


@dataclass(frozen=True, slots=True)
class BlacklistIndex:
    reported_count: int
    entities: tuple[BlacklistEntity, ...]
    source_sha256: tuple[str, ...]
    date_anomaly_count: int


@dataclass(frozen=True, slots=True)
class BlacklistOrder:
    order_id: str
    reported_name: str
    procuring_entity: str
    project_title: str
    start_date: str
    end_date: str | None
    permanent: bool
    source_sha256: str


@dataclass(frozen=True, slots=True)
class CpesLowRating:
    rating_id: str
    reported_name: str
    pcab_id: str | None
    project_title: str
    evaluation_date: str
    implementing_agency: str
    visit_rating_bps: int
    final_rating_bps: int
    qualitative_rating: str
    page_number: int
    release_label: str
    source_sha256: str
    source_url: str


@dataclass(frozen=True, slots=True)
class ContractorRecord:
    contractor_key: str
    contractor_name: str
    pcab_id: str
    pcab_name: str


@dataclass(frozen=True, slots=True)
class AwardRecord:
    source_row_id: str
    contract_id: str
    contractor_key: str
    relationship: str
    match_basis: str
    awardee_name: str
    award_date: str
    contract_amount_centavos: int
    row_sha256: str


@dataclass(frozen=True, slots=True)
class LinkedBlacklistEvent:
    order_id: str
    contractor_key: str
    contractor_name: str
    pcab_id: str
    reported_name: str
    identity_state: str
    procuring_entity: str
    project_title: str
    start_date: str
    end_date: str | None
    status: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class LinkedCpesEvent:
    rating_id: str
    contractor_key: str
    contractor_name: str
    pcab_id: str
    reported_name: str
    identity_state: str
    project_title: str
    evaluation_date: str
    implementing_agency: str
    visit_rating_bps: int
    final_rating_bps: int
    qualitative_rating: str
    page_number: int
    release_label: str
    source_sha256: str
    source_url: str


@dataclass(frozen=True, slots=True)
class AwardTimingSignal:
    signal_id: str
    signal_type: str
    contractor_key: str
    contractor_name: str
    pcab_id: str
    evidence_event_id: str
    contract_id: str
    relationship: str
    match_basis: str
    awardee_name: str
    award_date: str
    contract_amount_centavos: int
    award_row_sha256: str


@dataclass(frozen=True, slots=True)
class AccountabilitySnapshot:
    checked_on: str
    blacklist_index_sha256: tuple[str, ...]
    award_source_sha256: str
    award_source_revision: str
    blacklist_events: tuple[LinkedBlacklistEvent, ...]
    cpes_events: tuple[LinkedCpesEvent, ...]
    award_signals: tuple[AwardTimingSignal, ...]
    quarantine_counts: dict[str, int]


def normalize_entity_name(value: str) -> str:
    text = value.upper().replace("&", " AND ")
    return re.sub(r"[^A-Z0-9]+", "", text)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(_text(value, label))
    except ValueError as exc:
        raise ValueError(f"{label} must use ISO format") from exc


def _digest(values: tuple[str, ...]) -> None:
    if not values or any(SHA256.fullmatch(value) is None for value in values):
        raise ValueError("source digests must be lowercase SHA-256 values")


def _page_document(payload: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    return _object(document, label)


def _pagination(document: dict[str, Any], label: str) -> tuple[int, int, list[Any]]:
    count = document.get("count")
    total_pages = document.get("total_pages")
    data = document.get("data")
    if not isinstance(count, int) or count < 0:
        raise ValueError(f"{label} count is invalid")
    if not isinstance(total_pages, int) or total_pages < 1:
        raise ValueError(f"{label} total pages is invalid")
    if not isinstance(data, list):
        raise ValueError(f"{label} data must be a list")
    return count, total_pages, data


def _blacklist_entity(value: Any) -> BlacklistEntity:
    item = _object(value, "blacklist entity")
    orders = item.get("bo_issued")
    if not isinstance(orders, str) or not orders.isdigit() or int(orders) <= 0:
        raise ValueError("blacklist order count is invalid")
    minimum = _date(item.get("min_date"), "blacklist minimum date")
    maximum_raw = _text(item.get("max_date"), "blacklist maximum date")
    date_valid = maximum_raw == "PERMANENT" or (
        _date(maximum_raw, "blacklist maximum date") >= minimum
    )
    return BlacklistEntity(
        reported_name=_text(item.get("blacklisted_entity"), "blacklisted entity name"),
        order_count=int(orders),
        minimum_date=minimum.isoformat(),
        maximum_date=maximum_raw,
        date_valid=date_valid,
    )


def parse_blacklist_index_pages(
    payloads: tuple[bytes, ...], source_sha256: tuple[str, ...]
) -> BlacklistIndex:
    """Validate all pages of the GPPB consolidated entity index."""

    if len(payloads) != len(source_sha256):
        raise ValueError("blacklist payload and digest counts differ")
    _digest(source_sha256)
    documents = tuple(_page_document(payload, "blacklist index") for payload in payloads)
    pagination = tuple(_pagination(document, "blacklist index") for document in documents)
    counts = {item[0] for item in pagination}
    page_counts = {item[1] for item in pagination}
    if len(counts) != 1 or page_counts != {len(payloads)}:
        raise ValueError("blacklist pagination control total does not reconcile")
    rows = tuple(row for _, _, page in pagination for row in page)
    reported_count = next(iter(counts))
    if len(rows) != reported_count:
        raise ValueError("blacklist control total does not reconcile")
    entities = tuple(sorted((_blacklist_entity(row) for row in rows), key=repr))
    anomalies = sum(not entity.date_valid for entity in entities)
    return BlacklistIndex(reported_count, entities, source_sha256, anomalies)


def _blacklist_order(reported_name: str, value: Any, source_sha256: str) -> BlacklistOrder:
    item = _object(value, "blacklist order")
    start = _date(item.get("start_date"), "blacklist start date")
    raw_end = _text(item.get("end_date"), "blacklist end date")
    permanent = raw_end == "PERMANENT"
    end = None if permanent else _date(raw_end, "blacklist end date")
    if end is not None and end < start:
        raise ValueError("blacklist end date precedes start date")
    fields = {
        "reported_name": reported_name,
        "procuring_entity": _text(item.get("procuring_entity"), "procuring entity"),
        "project_title": _text(item.get("project"), "blacklist project"),
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "permanent": permanent,
    }
    identity_fields = {**fields, "reported_name": normalize_entity_name(reported_name)}
    identity = hashlib.sha256(
        json.dumps(identity_fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BlacklistOrder(order_id=identity, source_sha256=source_sha256, **fields)


def parse_blacklist_order_pages(
    reported_name: str, pages: tuple[tuple[bytes, str], ...]
) -> tuple[BlacklistOrder, ...]:
    """Validate detailed GPPB orders for one reported entity name."""

    name = _text(reported_name, "reported blacklist name")
    if not pages:
        raise ValueError("blacklist order pages must not be empty")
    _digest(tuple(digest for _, digest in pages))
    parsed = [(_page_document(payload, "blacklist orders"), digest) for payload, digest in pages]
    pagination = [
        (_pagination(document, "blacklist orders"), digest) for document, digest in parsed
    ]
    counts = {item[0][0] for item in pagination}
    page_counts = {item[0][1] for item in pagination}
    if len(counts) != 1 or page_counts != {len(pages)}:
        raise ValueError("blacklist order pagination control total does not reconcile")
    orders = tuple(
        _blacklist_order(name, row, digest) for (_, _, rows), digest in pagination for row in rows
    )
    if len(orders) != next(iter(counts)):
        raise ValueError("blacklist order control total does not reconcile")
    unique = {}
    for order in sorted(orders, key=lambda item: (item.order_id, item.source_sha256)):
        unique.setdefault(order.order_id, order)
    return tuple(unique.values())


def _percent_bps(value: str) -> int:
    result = int(Decimal(value.removesuffix("%")) * 100)
    if result < 0 or result > MAX_BASIS_POINTS:
        raise ValueError("CPES rating is outside percentage bounds")
    return result


def _cpes_header(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if all(label in line for label in ("NAME OF CONSTRUCTOR", "LICENSE NO.", "PROJECT")):
            return index
    raise ValueError("CPES page is missing its table header")


def _cpes_rating(
    line: str,
    *,
    page_number: int,
    release_label: str,
    source_sha256: str,
    source_url: str,
) -> CpesLowRating | None:
    match = re.search(
        r"(?P<visit>\d{2,3}\.\d{2}%)\s+(?P<final>\d{2,3}\.\d{2}%)\s+"
        r"(?P<quality>Poor|Unsatisfactory)\s*$",
        line,
    )
    if match is None:
        return None
    row = re.match(
        r"^\s*(?P<name>.*?)\s{2,}"
        r"(?:(?P<license>\d+|-)\s{2,})?"
        r"(?P<project>.*?)\s{2,}"
        r"(?P<date>\d{2}/\d{2}/\d{4})\s{2,}"
        r"(?P<agency>.*?)\s{2,}[\d,]+\.\d{3}\s+.*",
        line,
    )
    if row is None:
        raise ValueError("CPES low-rating row does not match the report layout")
    license_text = row.group("license") or ""
    evaluation = datetime.strptime(row.group("date"), "%m/%d/%Y").date()
    fields = {
        "reported_name": _text(row.group("name"), "CPES constructor name"),
        "pcab_id": str(int(license_text)) if license_text.isdigit() else None,
        "project_title": _text(row.group("project"), "CPES project title"),
        "evaluation_date": evaluation.isoformat(),
        "implementing_agency": _text(row.group("agency"), "CPES implementing agency"),
        "visit_rating_bps": _percent_bps(match.group("visit")),
        "final_rating_bps": _percent_bps(match.group("final")),
        "qualitative_rating": match.group("quality"),
        "page_number": page_number,
        "release_label": release_label,
        "source_sha256": source_sha256,
        "source_url": source_url,
    }
    identity = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CpesLowRating(rating_id=identity, **fields)


def parse_cpes_low_ratings(
    layout_text: str,
    *,
    source_sha256: str,
    source_url: str,
    release_label: str,
) -> tuple[CpesLowRating, ...]:
    """Extract only Poor and Unsatisfactory rows from an official CPES report."""

    _digest((source_sha256,))
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("CPES source URL must use HTTPS")
    ratings = []
    for page_number, page in enumerate(layout_text.split("\f"), start=1):
        lines = page.splitlines()
        if not any("Poor" in line or "Unsatisfactory" in line for line in lines):
            continue
        header_index = _cpes_header(lines)
        for line in lines[header_index + 1 :]:
            rating = _cpes_rating(
                line,
                page_number=page_number,
                release_label=_text(release_label, "CPES release label"),
                source_sha256=source_sha256,
                source_url=source_url,
            )
            if rating is not None:
                ratings.append(rating)
    if len({item.rating_id for item in ratings}) != len(ratings):
        raise ValueError("CPES low-rating rows contain duplicates")
    return tuple(sorted(ratings, key=lambda item: item.rating_id))


def _blacklist_status(order: BlacklistOrder, checked_on: date) -> str:
    start = date.fromisoformat(order.start_date)
    if start > checked_on:
        return "scheduled"
    if order.permanent or (order.end_date and date.fromisoformat(order.end_date) >= checked_on):
        return "active"
    return "expired"


def _link_blacklists(
    contractors: tuple[ContractorRecord, ...],
    orders: tuple[BlacklistOrder, ...],
    checked_on: date,
) -> tuple[tuple[LinkedBlacklistEvent, ...], int]:
    by_name: dict[str, list[ContractorRecord]] = {}
    for contractor in contractors:
        by_name.setdefault(normalize_entity_name(contractor.contractor_name), []).append(contractor)
    linked = []
    quarantined = 0
    seen: set[str] = set()
    for order in sorted(orders, key=lambda item: (item.order_id, item.reported_name)):
        if order.order_id in seen:
            continue
        seen.add(order.order_id)
        normalized = normalize_entity_name(order.reported_name)
        candidates = by_name.get(normalized, [])
        strong = [
            item
            for item in candidates
            if item.pcab_id and normalize_entity_name(item.pcab_name) == normalized
        ]
        if len(strong) != 1:
            quarantined += 1
            continue
        contractor = strong[0]
        linked.append(
            LinkedBlacklistEvent(
                order_id=order.order_id,
                contractor_key=contractor.contractor_key,
                contractor_name=contractor.contractor_name,
                pcab_id=contractor.pcab_id,
                reported_name=order.reported_name,
                identity_state="pcab_name_exact",
                procuring_entity=order.procuring_entity,
                project_title=order.project_title,
                start_date=order.start_date,
                end_date=order.end_date,
                status=_blacklist_status(order, checked_on),
                source_sha256=order.source_sha256,
            )
        )
    return tuple(sorted(linked, key=lambda item: item.order_id)), quarantined


def _link_cpes(
    contractors: tuple[ContractorRecord, ...], ratings: tuple[CpesLowRating, ...]
) -> tuple[tuple[LinkedCpesEvent, ...], int]:
    by_pcab: dict[str, list[ContractorRecord]] = {}
    for contractor in contractors:
        if contractor.pcab_id:
            by_pcab.setdefault(contractor.pcab_id, []).append(contractor)
    linked = []
    quarantined = 0
    for rating in ratings:
        candidates = by_pcab.get(rating.pcab_id or "", [])
        if len(candidates) != 1:
            quarantined += 1
            continue
        contractor = candidates[0]
        linked.append(
            LinkedCpesEvent(
                rating_id=rating.rating_id,
                contractor_key=contractor.contractor_key,
                contractor_name=contractor.contractor_name,
                pcab_id=contractor.pcab_id,
                reported_name=rating.reported_name,
                identity_state="pcab_id_exact",
                project_title=rating.project_title,
                evaluation_date=rating.evaluation_date,
                implementing_agency=rating.implementing_agency,
                visit_rating_bps=rating.visit_rating_bps,
                final_rating_bps=rating.final_rating_bps,
                qualitative_rating=rating.qualitative_rating,
                page_number=rating.page_number,
                release_label=rating.release_label,
                source_sha256=rating.source_sha256,
                source_url=rating.source_url,
            )
        )
    return tuple(sorted(linked, key=lambda item: item.rating_id)), quarantined


def _award_identity_matches(award: AwardRecord, contractor: ContractorRecord) -> bool:
    normalized = normalize_entity_name(award.awardee_name)
    names = {
        normalize_entity_name(contractor.contractor_name),
        normalize_entity_name(contractor.pcab_name),
    }
    return award.match_basis in AWARD_MATCH_BASES and normalized in names and bool(normalized)


def _signal(
    signal_type: str,
    event_id: str,
    contractor: ContractorRecord,
    award: AwardRecord,
) -> AwardTimingSignal:
    identity = hashlib.sha256(
        f"{signal_type}|{event_id}|{award.source_row_id}".encode()
    ).hexdigest()
    return AwardTimingSignal(
        signal_id=identity,
        signal_type=signal_type,
        contractor_key=contractor.contractor_key,
        contractor_name=contractor.contractor_name,
        pcab_id=contractor.pcab_id,
        evidence_event_id=event_id,
        contract_id=award.contract_id,
        relationship=award.relationship,
        match_basis=award.match_basis,
        awardee_name=award.awardee_name,
        award_date=award.award_date,
        contract_amount_centavos=award.contract_amount_centavos,
        award_row_sha256=award.row_sha256,
    )


def _award_signals(
    contractors: tuple[ContractorRecord, ...],
    blacklists: tuple[LinkedBlacklistEvent, ...],
    ratings: tuple[LinkedCpesEvent, ...],
    awards: tuple[AwardRecord, ...],
) -> tuple[AwardTimingSignal, ...]:
    by_key = {item.contractor_key: item for item in contractors}
    signals = []
    for event in blacklists:
        contractor = by_key[event.contractor_key]
        start = date.fromisoformat(event.start_date)
        end = date.max if event.end_date is None else date.fromisoformat(event.end_date)
        signals.extend(
            _signal("award_during_blacklist", event.order_id, contractor, award)
            for award in awards
            if award.contractor_key == event.contractor_key
            and _award_identity_matches(award, contractor)
            and start <= date.fromisoformat(award.award_date) <= end
        )
    for event in ratings:
        contractor = by_key[event.contractor_key]
        evaluation = date.fromisoformat(event.evaluation_date)
        signals.extend(
            _signal("award_after_low_cpes", event.rating_id, contractor, award)
            for award in awards
            if award.contractor_key == event.contractor_key
            and _award_identity_matches(award, contractor)
            and date.fromisoformat(award.award_date) > evaluation
        )
    unique = {item.signal_id: item for item in signals}
    return tuple(sorted(unique.values(), key=lambda item: item.signal_id))


def build_accountability_snapshot(
    contractors: tuple[ContractorRecord, ...],
    orders: tuple[BlacklistOrder, ...],
    cpes_ratings: tuple[CpesLowRating, ...],
    awards: tuple[AwardRecord, ...],
    *,
    checked_on: str,
    blacklist_index_sha256: tuple[str, ...],
    award_source_sha256: str,
    award_source_revision: str,
) -> AccountabilitySnapshot:
    """Link only strong identities and calculate narrow award-timing signals."""

    checked = _date(checked_on, "accountability checked date")
    _digest(blacklist_index_sha256 + (award_source_sha256,))
    if REVISION.fullmatch(award_source_revision) is None:
        raise ValueError("award source revision is invalid")
    if len({item.contractor_key for item in contractors}) != len(contractors):
        raise ValueError("contractor keys must be unique")
    blacklists, blacklist_quarantine = _link_blacklists(contractors, orders, checked)
    linked_cpes, cpes_quarantine = _link_cpes(contractors, cpes_ratings)
    return AccountabilitySnapshot(
        checked_on=checked.isoformat(),
        blacklist_index_sha256=blacklist_index_sha256,
        award_source_sha256=award_source_sha256,
        award_source_revision=award_source_revision,
        blacklist_events=blacklists,
        cpes_events=linked_cpes,
        award_signals=_award_signals(contractors, blacklists, linked_cpes, awards),
        quarantine_counts={
            "blacklist_name_only": blacklist_quarantine,
            "cpes_missing_or_unmatched_pcab": cpes_quarantine,
        },
    )
