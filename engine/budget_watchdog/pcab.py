"""PCAB regular-license acquisition and deterministic verification."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArchivedArtifact, ArtifactArchive

SHA256 = re.compile(r"[0-9a-f]{64}")
PCAB_CELL_COUNT = 7
PCAB_GRID_PATH = "/phpGrid/data.php"
PCAB_GRID_PARAMS: Mapping[str, str | int] = MappingProxyType(
    {
        "dt": "json",
        "gn": "Licenses",
        "_search": "false",
        "nd": 0,
        "rows": 20_000,
        "page": 1,
        "sidx": 1,
        "sord": "asc",
    }
)


@dataclass(frozen=True, slots=True)
class PcabLicense:
    record_id: str
    firm_name: str
    license_number: str
    amo: str
    category: str
    valid_to: date
    gov_infra: bool


@dataclass(frozen=True, slots=True)
class PcabVerification:
    status: str
    firm_name: str
    category: str
    valid_to: str
    gov_infra: bool | None
    source_sha256: str


@dataclass(frozen=True, slots=True)
class PcabSnapshot:
    retrieved_on: date
    source_sha256: str
    record_count: int
    licenses_by_number: Mapping[str, tuple[PcabLicense, ...]]

    def verify(self, license_number: str) -> PcabVerification:
        normalized = normalize_license_number(license_number)
        licenses = self.licenses_by_number.get(normalized, ())
        if not licenses:
            return PcabVerification(
                status="not_found_current_regular",
                firm_name="",
                category="",
                valid_to="",
                gov_infra=None,
                source_sha256=self.source_sha256,
            )
        active = tuple(item for item in licenses if item.valid_to >= self.retrieved_on)
        current = active or licenses
        if active and any(item.gov_infra for item in active):
            status = "current_regular"
        elif active:
            status = "current_not_government_infra"
        else:
            status = "expired_regular"
        return PcabVerification(
            status=status,
            firm_name=" / ".join(sorted({item.firm_name for item in current})),
            category=" / ".join(sorted({item.category for item in current if item.category})),
            valid_to=max(item.valid_to for item in current).isoformat(),
            gov_infra=any(item.gov_infra for item in current),
            source_sha256=self.source_sha256,
        )


def normalize_license_number(value: str) -> str:
    stripped = value.strip()
    if not stripped.isdigit():
        raise ValueError("PCAB license number must contain digits")
    return str(int(stripped))


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"PCAB {label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"PCAB {label} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"PCAB {label} must be text")
    return value.strip()


def _license(row: Any) -> PcabLicense:
    item = _object(row, "row")
    cells = item.get("cell")
    if not isinstance(cells, list) or len(cells) != PCAB_CELL_COUNT:
        raise ValueError("PCAB row must contain seven cells")
    values = [
        _text(cells[0], "record id"),
        _text(cells[1], "firm name"),
        _text(cells[2], "license number"),
        _optional_text(cells[3], "AMO"),
        _optional_text(cells[4], "category"),
        _text(cells[5], "validity date"),
        _text(cells[6], "government-infrastructure value"),
    ]
    if values[0] != _text(item.get("id"), "row id"):
        raise ValueError("PCAB row id does not match its first cell")
    try:
        valid_to = date.fromisoformat(values[5])
    except ValueError as exc:
        raise ValueError("PCAB validity date must use ISO format") from exc
    if values[6] not in {"0", "1"}:
        raise ValueError("PCAB government-infrastructure value is invalid")
    return PcabLicense(
        record_id=values[0],
        firm_name=values[1],
        license_number=normalize_license_number(values[2]),
        amo=values[3],
        category=values[4],
        valid_to=valid_to,
        gov_infra=values[6] == "1",
    )


def parse_pcab_regular_licenses(
    payload: bytes,
    *,
    retrieved_on: date,
    source_sha256: str,
) -> PcabSnapshot:
    """Validate a complete page from the official PCAB verification grid."""

    if not SHA256.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    try:
        document = _object(json.loads(payload), "document")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("PCAB response must be valid JSON") from exc
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("PCAB rows must be a list")
    page = document.get("page")
    total = document.get("total")
    if page not in (1, "1") or total not in (1, "1"):
        raise ValueError("PCAB response must contain one single complete page")
    records = document.get("records")
    if not isinstance(records, int) or records != len(rows):
        raise ValueError("PCAB record count does not match returned rows")
    licenses = tuple(_license(row) for row in rows)
    grouped: dict[str, list[PcabLicense]] = defaultdict(list)
    for license_record in licenses:
        grouped[license_record.license_number].append(license_record)
    index = MappingProxyType(
        {
            number: tuple(sorted(items, key=lambda item: (item.valid_to, item.record_id)))
            for number, items in sorted(grouped.items())
        }
    )
    return PcabSnapshot(
        retrieved_on=retrieved_on,
        source_sha256=source_sha256,
        record_count=len(licenses),
        licenses_by_number=index,
    )


def acquire_pcab_regular_licenses(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    *,
    retrieved_at: datetime | None = None,
) -> tuple[ArchivedArtifact, PcabSnapshot]:
    """Establish a PCAB session, archive one complete grid response, and validate it."""

    timestamp = retrieved_at or datetime.now(UTC)
    fetcher.fetch("pcab", "/verify/", retrieved_at=timestamp)
    acquisition = fetcher.fetch(
        "pcab",
        PCAB_GRID_PATH,
        params=PCAB_GRID_PARAMS,
        retrieved_at=timestamp,
    )
    artifact = archive.store(acquisition)
    snapshot = parse_pcab_regular_licenses(
        acquisition.payload,
        retrieved_on=timestamp.date(),
        source_sha256=artifact.sha256,
    )
    return artifact, snapshot
