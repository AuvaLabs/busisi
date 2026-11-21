"""Validated Senate committee-stage change records."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

FISCAL_YEAR = 2027
STATES = ("awaiting_official_document", "verified_changes")
ORIGIN_STAGES = ("nep", "house_gab")
MATCH_STATES = ("exact", "unmatched")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SenateCommitteeError(ValueError):
    """Raised when a committee-stage claim lacks the required official evidence."""


@dataclass(frozen=True, slots=True)
class OfficialDocument:
    source_url: str
    publication_date: str
    artifact_sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class ChangeControl:
    group_code: str
    label: str
    project_count: int
    previous_centavos: int
    senate_centavos: int
    change_centavos: int


@dataclass(frozen=True, slots=True)
class CommitteeChange:
    change_id: str
    group_code: str
    origin_stage: str
    source_project_id: str | None
    title: str
    project_type: str | None
    region: str | None
    province: str | None
    city_or_municipality: str | None
    district: str | None
    previous_centavos: int
    senate_centavos: int
    change_centavos: int
    reason: str
    source_page: int
    match_state: str
    linked_project_slug: str | None
    public_note: str


@dataclass(frozen=True, slots=True)
class SenateCommitteeRelease:
    release_id: str
    fiscal_year: int
    report_number: str
    related_bill: str
    state: str
    checked_at: str
    official_document: OfficialDocument | None
    controls: tuple[ChangeControl, ...]
    items: tuple[CommitteeChange, ...]
    public_note: str


@dataclass(frozen=True, slots=True)
class SenateCommitteeSummary:
    item_count: int
    total_previous_centavos: int | None
    total_senate_centavos: int | None
    total_change_centavos: int | None


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SenateCommitteeError(f"{label} must be an object")
    return value


def _text(value: Any, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SenateCommitteeError(f"{label} must be non-empty text")
    return value.strip()


def _centavos(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SenateCommitteeError(f"{label} must use integer centavos")
    return value


def _non_negative_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SenateCommitteeError(f"{label} must be a non-negative integer")
    return value


def _official_url(value: Any) -> str:
    source_url = str(_text(value, "official document source URL"))
    parsed = urlparse(source_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (host == "senate.gov.ph" or host.endswith(".senate.gov.ph")):
        raise SenateCommitteeError("official document source must use an official Senate URL")
    return source_url


def _official_document(value: Any) -> OfficialDocument:
    item = _mapping(value, "official document")
    publication_date = str(_text(item.get("publication_date"), "publication date"))
    try:
        date.fromisoformat(publication_date)
    except ValueError as exc:
        raise SenateCommitteeError("publication date must use ISO format") from exc
    digest = str(_text(item.get("artifact_sha256"), "artifact SHA-256"))
    if not SHA256_PATTERN.fullmatch(digest):
        raise SenateCommitteeError("artifact SHA-256 must contain 64 lowercase hex characters")
    byte_size = _non_negative_integer(item.get("byte_size"), "official document byte size")
    if byte_size == 0:
        raise SenateCommitteeError("official document byte size must be positive")
    return OfficialDocument(
        _official_url(item.get("source_url")), publication_date, digest, byte_size
    )


def _change_values(item: dict[str, Any], label: str) -> tuple[int, int, int]:
    previous = _centavos(item.get("previous_centavos"), f"{label} previous amount")
    senate = _centavos(item.get("senate_centavos"), f"{label} Senate amount")
    change = _centavos(item.get("change_centavos"), f"{label} change amount")
    if change != senate - previous:
        raise SenateCommitteeError(f"{label} change does not equal Senate minus previous amount")
    return previous, senate, change


def _control(value: Any) -> ChangeControl:
    item = _mapping(value, "change control")
    previous, senate, change = _change_values(item, "change control")
    return ChangeControl(
        group_code=str(_text(item.get("group_code"), "control group code")),
        label=str(_text(item.get("label"), "control label")),
        project_count=_non_negative_integer(item.get("project_count"), "control project count"),
        previous_centavos=previous,
        senate_centavos=senate,
        change_centavos=change,
    )


def _change(value: Any) -> CommitteeChange:
    item = _mapping(value, "committee change")
    previous, senate, change = _change_values(item, "committee change")
    origin_stage = str(_text(item.get("origin_stage"), "origin stage"))
    if origin_stage not in ORIGIN_STAGES:
        raise SenateCommitteeError("origin stage is not supported")
    match_state = str(_text(item.get("match_state"), "match state"))
    if match_state not in MATCH_STATES:
        raise SenateCommitteeError("held-back match cannot enter the public committee release")
    linked_slug = _text(item.get("linked_project_slug"), "linked project slug", optional=True)
    if (match_state == "exact") != (linked_slug is not None):
        raise SenateCommitteeError("only an exact match may link a Busisi project page")
    source_page = _non_negative_integer(item.get("source_page"), "source page")
    if source_page == 0:
        raise SenateCommitteeError("source page must be positive")
    return CommitteeChange(
        change_id=str(_text(item.get("change_id"), "change ID")),
        group_code=str(_text(item.get("group_code"), "change group code")),
        origin_stage=origin_stage,
        source_project_id=_text(item.get("source_project_id"), "source project ID", optional=True),
        title=str(_text(item.get("title"), "change title")),
        project_type=_text(item.get("project_type"), "project type", optional=True),
        region=_text(item.get("region"), "region", optional=True),
        province=_text(item.get("province"), "province", optional=True),
        city_or_municipality=_text(
            item.get("city_or_municipality"), "city or municipality", optional=True
        ),
        district=_text(item.get("district"), "district", optional=True),
        previous_centavos=previous,
        senate_centavos=senate,
        change_centavos=change,
        reason=str(_text(item.get("reason"), "change reason")),
        source_page=source_page,
        match_state=match_state,
        linked_project_slug=linked_slug,
        public_note=str(_text(item.get("public_note"), "change public note")),
    )


def load_senate_committee_release(payload: bytes) -> SenateCommitteeRelease:
    """Load one release and reject claims that exceed the official evidence."""

    try:
        root = _mapping(json.loads(payload), "Senate committee release")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SenateCommitteeError("Senate committee release JSON is invalid") from exc
    if root.get("schema_version") != 1 or root.get("fiscal_year") != FISCAL_YEAR:
        raise SenateCommitteeError("Senate committee schema or fiscal year is unsupported")
    state = str(_text(root.get("state"), "release state"))
    if state not in STATES:
        raise SenateCommitteeError("release state is not supported")
    report_number = str(_text(root.get("report_number"), "report number"))
    related_bill = str(_text(root.get("related_bill"), "related bill"))
    if not report_number.isdigit() or not re.fullmatch(r"HB \d+", related_bill):
        raise SenateCommitteeError("report number or related bill is invalid")
    checked_at = str(_text(root.get("checked_at"), "checked at"))
    try:
        datetime.fromisoformat(checked_at)
    except ValueError as exc:
        raise SenateCommitteeError("checked at must use ISO format") from exc
    controls_raw = root.get("controls")
    items_raw = root.get("items")
    if not isinstance(controls_raw, list) or not isinstance(items_raw, list):
        raise SenateCommitteeError("controls and items must be arrays")
    document_value = root.get("official_document")
    if state == "awaiting_official_document":
        if document_value is not None or controls_raw or items_raw:
            raise SenateCommitteeError(
                "watch-only release must not claim documents, amounts, or items"
            )
        official_document = None
    else:
        if document_value is None or not controls_raw or not items_raw:
            raise SenateCommitteeError("verified release requires a document, controls, and items")
        official_document = _official_document(document_value)
    release = SenateCommitteeRelease(
        release_id=str(_text(root.get("release_id"), "release ID")),
        fiscal_year=FISCAL_YEAR,
        report_number=report_number,
        related_bill=related_bill,
        state=state,
        checked_at=checked_at,
        official_document=official_document,
        controls=tuple(_control(value) for value in controls_raw),
        items=tuple(_change(value) for value in items_raw),
        public_note=str(_text(root.get("public_note"), "public note")),
    )
    reconcile_senate_committee_release(release)
    return release


def reconcile_senate_committee_release(
    release: SenateCommitteeRelease,
) -> SenateCommitteeSummary:
    """Require every published row to reconcile to the official group controls."""

    if release.state == "awaiting_official_document":
        return SenateCommitteeSummary(0, None, None, None)
    control_codes = [control.group_code for control in release.controls]
    if len(control_codes) != len(set(control_codes)):
        raise SenateCommitteeError("control group codes must be unique")
    if len({item.change_id for item in release.items}) != len(release.items):
        raise SenateCommitteeError("committee change IDs must be unique")
    grouped: dict[str, list[CommitteeChange]] = defaultdict(list)
    for item in release.items:
        if item.group_code not in control_codes:
            raise SenateCommitteeError("committee change group has no control total")
        grouped[item.group_code].append(item)
    for control in release.controls:
        items = grouped[control.group_code]
        actual = (
            len(items),
            sum(item.previous_centavos for item in items),
            sum(item.senate_centavos for item in items),
            sum(item.change_centavos for item in items),
        )
        expected = (
            control.project_count,
            control.previous_centavos,
            control.senate_centavos,
            control.change_centavos,
        )
        if actual != expected:
            raise SenateCommitteeError(f"{control.group_code} control does not reconcile")
    return SenateCommitteeSummary(
        item_count=len(release.items),
        total_previous_centavos=sum(control.previous_centavos for control in release.controls),
        total_senate_centavos=sum(control.senate_centavos for control in release.controls),
        total_change_centavos=sum(control.change_centavos for control in release.controls),
    )
