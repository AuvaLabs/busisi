"""Validate versioned secondary PhilGEPS award mirror rows."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse

REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
ACQUISITION_STATUS = "source_file_archived_secondary"
MINIMUM_FISCAL_YEAR = 2000
MAXIMUM_FISCAL_YEAR = 2100


class AwardMirrorError(ValueError):
    """Raised when a mirror row cannot support the stated evidence boundary."""


@dataclass(frozen=True, slots=True)
class AwardMirrorSource:
    title: str
    publisher: str
    dataset_url: str
    file_url: str
    dataset_file: str
    revision: str
    last_modified: str
    retrieved_at: str
    license: str
    acquisition_status: str
    source_file_sha256: str
    source_file_byte_size: int
    evidence_note: str


@dataclass(frozen=True, slots=True)
class AwardMirrorRecord:
    source_row_id: str
    contract_id: str
    fiscal_year: int
    reference_id: str
    award_title: str
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
class AwardMirrorCatalog:
    checked_at: str
    source: AwardMirrorSource
    records: tuple[AwardMirrorRecord, ...]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AwardMirrorError(f"{field} must be non-empty text")
    return value.strip()


def _https(value: object, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise AwardMirrorError(f"{field} must use HTTPS without credentials")
    return text


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AwardMirrorError(f"{field} must be ISO formatted") from exc
    if parsed.tzinfo is None:
        raise AwardMirrorError(f"{field} must be timezone-aware")
    return text


def _source(raw: object) -> AwardMirrorSource:
    if not isinstance(raw, dict):
        raise AwardMirrorError("source must be an object")
    revision = _text(raw.get("revision"), "revision")
    if REVISION.fullmatch(revision) is None:
        raise AwardMirrorError("revision must be a lowercase 40-character commit")
    status = _text(raw.get("acquisition_status"), "acquisition_status")
    if status != ACQUISITION_STATUS:
        raise AwardMirrorError("unsupported acquisition status")
    source_digest = _text(raw.get("source_file_sha256"), "source_file_sha256")
    if SHA256.fullmatch(source_digest) is None:
        raise AwardMirrorError("source file SHA-256 is invalid")
    source_size = raw.get("source_file_byte_size")
    if isinstance(source_size, bool) or not isinstance(source_size, int) or source_size <= 0:
        raise AwardMirrorError("source file byte size must be a positive integer")
    return AwardMirrorSource(
        title=_text(raw.get("title"), "title"),
        publisher=_text(raw.get("publisher"), "publisher"),
        dataset_url=_https(raw.get("dataset_url"), "dataset_url"),
        file_url=_https(raw.get("file_url"), "file_url"),
        dataset_file=_text(raw.get("dataset_file"), "dataset_file"),
        revision=revision,
        last_modified=_timestamp(raw.get("last_modified"), "last_modified"),
        retrieved_at=_timestamp(raw.get("retrieved_at"), "retrieved_at"),
        license=_text(raw.get("license"), "license"),
        acquisition_status=status,
        source_file_sha256=source_digest,
        source_file_byte_size=source_size,
        evidence_note=_text(raw.get("evidence_note"), "evidence_note"),
    )


def _row_payload(raw: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in raw.items() if key != "row_sha256"}


def _record(raw: object) -> AwardMirrorRecord:
    if not isinstance(raw, dict):
        raise AwardMirrorError("record entries must be objects")
    row_id = _text(raw.get("source_row_id"), "source_row_id")
    try:
        uuid.UUID(row_id)
    except ValueError as exc:
        raise AwardMirrorError("source_row_id must be a UUID") from exc
    amount = raw.get("contract_amount_centavos")
    year = raw.get("fiscal_year")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise AwardMirrorError("contract_amount_centavos must use non-negative integer centavos")
    if (
        isinstance(year, bool)
        or not isinstance(year, int)
        or not MINIMUM_FISCAL_YEAR <= year <= MAXIMUM_FISCAL_YEAR
    ):
        raise AwardMirrorError("fiscal_year is outside the supported range")
    award_date = _text(raw.get("award_date"), "award_date")
    try:
        date.fromisoformat(award_date)
    except ValueError as exc:
        raise AwardMirrorError("award_date must be ISO formatted") from exc
    digest = _text(raw.get("row_sha256"), "row_sha256")
    observed = hashlib.sha256(
        json.dumps(_row_payload(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if SHA256.fullmatch(digest) is None or digest != observed:
        raise AwardMirrorError("row_sha256 does not match the canonical extracted row")
    return AwardMirrorRecord(
        source_row_id=row_id,
        contract_id=_text(raw.get("contract_id"), "contract_id"),
        fiscal_year=year,
        reference_id=_text(raw.get("reference_id"), "reference_id"),
        award_title=_text(raw.get("award_title"), "award_title"),
        notice_title=_text(raw.get("notice_title"), "notice_title"),
        awardee_name=_text(raw.get("awardee_name"), "awardee_name"),
        organization_name=_text(raw.get("organization_name"), "organization_name"),
        area_of_delivery=_text(raw.get("area_of_delivery"), "area_of_delivery"),
        business_category=_text(raw.get("business_category"), "business_category"),
        contract_amount_centavos=amount,
        award_date=award_date,
        award_status=_text(raw.get("award_status"), "award_status"),
        row_sha256=digest,
    )


def load_award_mirror(payload: bytes) -> AwardMirrorCatalog:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AwardMirrorError("award mirror JSON is invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise AwardMirrorError("unsupported award mirror schema version")
    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        raise AwardMirrorError("records must be an array")
    records = tuple(_record(item) for item in records_raw)
    for field in ("source_row_id", "contract_id"):
        values = [getattr(item, field) for item in records]
        if len(values) != len(set(values)):
            raise AwardMirrorError(f"duplicate {field}")
    return AwardMirrorCatalog(
        checked_at=_timestamp(raw.get("checked_at"), "checked_at"),
        source=_source(raw.get("source")),
        records=records,
    )
