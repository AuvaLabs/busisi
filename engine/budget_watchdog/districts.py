"""Validated congressional-district context for DPWH district offices."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArchivedArtifact, ArtifactArchive

SHA256 = re.compile(r"[0-9a-f]{64}")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
CLASSIFICATIONS = {"single_district", "shared_office", "unassigned"}
DISTRICT_API_PATH = "/api/v1/hgab/2027/districts"
DISTRICT_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class DistrictSeat:
    district_id: str
    label: str
    jurisdiction: str
    district_label: str
    region: str
    representative_name: str
    representative_status: str
    representative_status_note: str
    representative_profile_url: str


@dataclass(frozen=True, slots=True)
class OfficeDistrictAttribution:
    office_name: str
    classification: str
    seats: tuple[DistrictSeat, ...]

    def __post_init__(self) -> None:
        if self.classification not in CLASSIFICATIONS:
            raise ValueError("district classification is invalid")


@dataclass(frozen=True, slots=True)
class DistrictSnapshot:
    retrieved_on: date
    source_commit: str
    source_built_at: str
    source_sha256: tuple[str, ...]
    snapshot_sha256: str
    district_count: int
    office_count: int
    offices: Mapping[str, OfficeDistrictAttribution]

    def lookup(self, office_name: str) -> OfficeDistrictAttribution:
        normalized = _office_key(office_name)
        return self.offices.get(
            normalized,
            OfficeDistrictAttribution(office_name.strip(), "unassigned", ()),
        )


@dataclass(frozen=True, slots=True)
class _DistrictPage:
    offset: int
    total: int
    commit: str
    built_at: str
    records: tuple[Any, ...]


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"district {label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"district {label} must be a list")
    return value


def _text(value: Any, label: str, *, optional: bool = False) -> str:
    if not isinstance(value, str) or (not optional and not value.strip()):
        qualifier = "text" if optional else "non-empty text"
        raise ValueError(f"district {label} must be {qualifier}")
    return value.strip()


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"district {label} must be a nonnegative integer")
    return value


def _office_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _profile_url(value: Any) -> str:
    if value is None:
        return ""
    url = _text(value, "representative profile URL")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "congress.gov.ph",
        "www.congress.gov.ph",
    }:
        raise ValueError("representative profile URL must use the official House origin")
    return url


def _seat(value: Any) -> tuple[DistrictSeat, tuple[tuple[str, str], ...]]:
    district = _object(value, "record")
    representative = _object(district.get("representative"), "representative")
    status = _text(representative.get("status"), "representative status")
    if status not in {"resolved", "ambiguous"}:
        raise ValueError("representative status is invalid")
    status_note = representative.get("status_note")
    if status_note is None:
        status_note = ""
    else:
        status_note = _text(status_note, "representative status note", optional=True)
    seat = DistrictSeat(
        district_id=_text(district.get("id"), "id"),
        label=_text(district.get("label"), "label"),
        jurisdiction=_text(district.get("jurisdiction"), "jurisdiction"),
        district_label=_text(district.get("district_label"), "district label"),
        region=_text(district.get("region"), "region"),
        representative_name=_text(representative.get("name"), "representative name"),
        representative_status=status,
        representative_status_note=status_note,
        representative_profile_url=_profile_url(representative.get("profile_url")),
    )
    offices = []
    for raw_office in _list(district.get("offices"), "offices"):
        office = _object(raw_office, "office")
        tier = _text(office.get("tier"), "office tier")
        if tier not in {"A", "B"}:
            raise ValueError("district office tier is invalid")
        offices.append((_text(office.get("name"), "office name"), tier))
    return seat, tuple(offices)


def _page(payload: bytes) -> _DistrictPage:
    try:
        document = _object(json.loads(payload), "document")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("district response must be valid JSON") from exc
    meta = _object(document.get("meta"), "metadata")
    data = _object(document.get("data"), "data")
    districts = _list(data.get("districts"), "records")
    returned = _integer(meta.get("returned"), "returned count")
    if returned != len(districts):
        raise ValueError("district returned count does not match its records")
    commit = _text(meta.get("source_commit"), "source commit")
    if not GIT_SHA.fullmatch(commit):
        raise ValueError("district source commit must be a Git SHA")
    built_at = _text(meta.get("built_at"), "source build time")
    try:
        datetime.fromisoformat(built_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("district source build time must use ISO format") from exc
    return _DistrictPage(
        offset=_integer(meta.get("offset"), "offset"),
        total=_integer(meta.get("total"), "total count"),
        commit=commit,
        built_at=built_at,
        records=tuple(districts),
    )


def _complete_records(pages: tuple[_DistrictPage, ...]) -> tuple[Any, ...]:
    expected_offset = 0
    records: list[Any] = []
    for page in sorted(pages, key=lambda item: item.offset):
        if page.offset != expected_offset:
            raise ValueError("district pages are incomplete or overlap")
        records.extend(page.records)
        expected_offset += len(page.records)
    if len(records) != pages[0].total:
        raise ValueError("district pages do not contain the complete district set")
    return tuple(records)


def parse_district_pages(
    payloads: tuple[bytes, ...],
    *,
    source_sha256: tuple[str, ...],
    retrieved_on: date,
) -> DistrictSnapshot:
    """Validate a complete, paginated district snapshot and index its DPWH offices."""

    if not payloads or len(payloads) != len(source_sha256):
        raise ValueError("district pages and source hashes must be non-empty and aligned")
    if any(not SHA256.fullmatch(digest) for digest in source_sha256):
        raise ValueError("district source hashes must be lowercase SHA-256 digests")

    pages = tuple(_page(payload) for payload in payloads)
    totals = {page.total for page in pages}
    commits = {page.commit for page in pages}
    built_at_values = {page.built_at for page in pages}

    if len(totals) != 1 or len(commits) != 1 or len(built_at_values) != 1:
        raise ValueError("district pages have conflicting snapshot metadata")
    district_records = _complete_records(pages)

    seats: dict[str, DistrictSeat] = {}
    office_seats: dict[str, list[tuple[str, DistrictSeat, str]]] = defaultdict(list)
    for record in district_records:
        seat, offices = _seat(record)
        if seat.district_id in seats:
            raise ValueError("district identifiers must be unique")
        seats[seat.district_id] = seat
        for office_name, tier in offices:
            office_seats[_office_key(office_name)].append((office_name, seat, tier))

    office_index: dict[str, OfficeDistrictAttribution] = {}
    for key, values in sorted(office_seats.items()):
        ordered = tuple(sorted((item[1] for item in values), key=lambda item: item.district_id))
        classification = (
            "single_district"
            if len(ordered) == 1 and {item[2] for item in values} == {"A"}
            else "shared_office"
        )
        office_index[key] = OfficeDistrictAttribution(values[0][0], classification, ordered)

    snapshot_digest = hashlib.sha256("\n".join(source_sha256).encode()).hexdigest()
    return DistrictSnapshot(
        retrieved_on=retrieved_on,
        source_commit=next(iter(commits)),
        source_built_at=next(iter(built_at_values)),
        source_sha256=source_sha256,
        snapshot_sha256=snapshot_digest,
        district_count=len(seats),
        office_count=len(office_index),
        offices=MappingProxyType(office_index),
    )


def acquire_district_snapshot(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    *,
    retrieved_at: datetime | None = None,
) -> tuple[tuple[ArchivedArtifact, ...], DistrictSnapshot]:
    """Archive and validate the complete BetterGov district-office snapshot."""

    timestamp = retrieved_at or datetime.now(UTC)
    artifacts: list[ArchivedArtifact] = []
    payloads: list[bytes] = []
    for offset in (0, DISTRICT_PAGE_SIZE):
        acquisition = fetcher.fetch(
            "bettergov-budget",
            DISTRICT_API_PATH,
            params={"limit": DISTRICT_PAGE_SIZE, "offset": offset},
            retrieved_at=timestamp,
        )
        artifacts.append(archive.store(acquisition))
        payloads.append(acquisition.payload)
    snapshot = parse_district_pages(
        tuple(payloads),
        source_sha256=tuple(artifact.sha256 for artifact in artifacts),
        retrieved_on=timestamp.date(),
    )
    return tuple(artifacts), snapshot
