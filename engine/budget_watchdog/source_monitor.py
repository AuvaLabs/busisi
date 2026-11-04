"""Deterministic parsing and drift comparison for regularly checked sources."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from engine.budget_watchdog.pcab import parse_pcab_regular_licenses

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DBM_ORIGIN = "https://www.dbm.gov.ph"


class SourceMonitorError(ValueError):
    """Raised when a monitored source cannot support a safe comparison."""


def review_pcab_transition(
    reviewed_payload: bytes,
    observed_payload: bytes,
    *,
    reviewed_sha256: str,
    observed_sha256: str,
    observed_on: str,
) -> dict[str, Any]:
    """Classify a PCAB count drop using two fully validated archived snapshots."""
    try:
        comparison_date = date.fromisoformat(observed_on)
    except ValueError as exc:
        raise SourceMonitorError("PCAB transition date must use ISO format") from exc
    reviewed = parse_pcab_regular_licenses(
        reviewed_payload,
        retrieved_on=comparison_date,
        source_sha256=reviewed_sha256,
    )
    observed = parse_pcab_regular_licenses(
        observed_payload,
        retrieved_on=comparison_date,
        source_sha256=observed_sha256,
    )

    def by_record(snapshot: Any) -> dict[str, tuple[Any, ...]]:
        return {
            item.record_id: (
                item.firm_name,
                item.license_number,
                item.amo,
                item.category,
                item.valid_to,
                item.gov_infra,
            )
            for licenses in snapshot.licenses_by_number.values()
            for item in licenses
        }

    reviewed_rows = by_record(reviewed)
    observed_rows = by_record(observed)
    removed_ids = sorted(reviewed_rows.keys() - observed_rows.keys())
    added_ids = sorted(observed_rows.keys() - reviewed_rows.keys())
    retained_ids = reviewed_rows.keys() & observed_rows.keys()
    removed_expired = [
        record_id
        for record_id in removed_ids
        if reviewed_rows[record_id][4] <= comparison_date
    ]
    removed_active = sorted(set(removed_ids) - set(removed_expired))
    changed = sorted(
        record_id
        for record_id in retained_ids
        if reviewed_rows[record_id] != observed_rows[record_id]
    )
    passed = not removed_active and not changed
    return {
        "passed": passed,
        "observed_on": comparison_date.isoformat(),
        "reviewed_sha256": reviewed_sha256,
        "observed_sha256": observed_sha256,
        "reviewed_records": reviewed.record_count,
        "observed_records": observed.record_count,
        "removed_expired_records": len(removed_expired),
        "removed_active_records": len(removed_active),
        "added_records": len(added_ids),
        "changed_retained_records": len(changed),
        "recommended_floor": reviewed.record_count - len(removed_expired) if passed else None,
        "removed_active_ids": removed_active,
        "changed_retained_ids": changed,
    }


def _object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceMonitorError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise SourceMonitorError(f"{label} must be a JSON object")
    return value


def parse_huggingface_metadata(payload: bytes, dataset_id: str) -> dict[str, str]:
    """Return stable revision fields from the public Hugging Face dataset API."""
    value = _object(payload, "dataset metadata")
    revision = value.get("sha")
    modified = value.get("lastModified")
    if value.get("id") != dataset_id:
        raise SourceMonitorError("dataset identifier changed")
    if value.get("private") is True or value.get("disabled") is True:
        raise SourceMonitorError("dataset is no longer publicly available")
    if not isinstance(revision, str) or _GIT_SHA.fullmatch(revision) is None:
        raise SourceMonitorError("dataset revision is invalid")
    if not isinstance(modified, str):
        raise SourceMonitorError("dataset modification time is invalid")
    try:
        datetime.fromisoformat(modified.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceMonitorError("dataset modification time is invalid") from exc
    return {
        "dataset_id": dataset_id,
        "revision": revision,
        "last_modified": modified,
    }


def _canonical_dbm_url(value: str) -> str:
    absolute = urljoin(f"{_DBM_ORIGIN}/", value)
    parsed = urlparse(absolute)
    if parsed.scheme != "https" or parsed.hostname != "www.dbm.gov.ph":
        raise SourceMonitorError("DBM catalogue link escaped the official origin")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse(("https", "www.dbm.gov.ph", parsed.path, "", query, ""))


class _DbmPanelParser(HTMLParser):
    def __init__(self, year: int) -> None:
        super().__init__(convert_charrefs=True)
        self._panel_id = f"rlta-panel-{year}"
        self._active = False
        self._depth = 0
        self._href: str | None = None
        self._text: list[str] = []
        self.records: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div":
            if not self._active and attributes.get("id") == self._panel_id:
                self._active = True
                self._depth = 1
            elif self._active:
                self._depth += 1
        if self._active and tag == "a" and attributes.get("href"):
            self._href = attributes["href"]
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active and tag == "a" and self._href is not None:
            label = " ".join("".join(self._text).split())
            if label:
                self.records.append({"label": label, "url": _canonical_dbm_url(self._href)})
            self._href = None
            self._text = []
        if self._active and tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._active = False


def parse_dbm_release_catalog(
    payload: bytes, year: int, *, allow_empty: bool = False
) -> tuple[dict[str, str], ...]:
    """Extract stable official article links from one DBM release-year panel."""
    try:
        document = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceMonitorError("DBM release catalogue must be UTF-8") from exc
    parser = _DbmPanelParser(year)
    parser.feed(document)
    records = tuple(parser.records)
    if not records and not allow_empty:
        raise SourceMonitorError(f"DBM release catalogue has no {year} records")
    labels = [record["label"] for record in records]
    if len(labels) != len(set(labels)):
        raise SourceMonitorError("DBM release catalogue has duplicate labels")
    return records


def compare_observations(baseline: dict[str, Any], observed: dict[str, Any]) -> tuple[str, ...]:
    """Compare only stable source identities and catalogue records."""
    differences: list[str] = []
    baseline_datasets = baseline.get("datasets", {})
    observed_datasets = observed.get("datasets", {})
    if set(baseline_datasets) != set(observed_datasets):
        differences.append("datasets: monitored set changed")
    for key in sorted(set(baseline_datasets) & set(observed_datasets)):
        if baseline_datasets[key].get("revision") != observed_datasets[key].get("revision"):
            differences.append(f"datasets:{key}: revision changed")
    for key in ("dbm_releases", "dbm_next_releases"):
        if baseline.get(key) != observed.get(key):
            differences.append(f"{key}: catalogue changed")
    for key in ("revision", "total"):
        if baseline.get("districts", {}).get(key) != observed.get("districts", {}).get(key):
            differences.append(f"districts: {key} changed")
    minimum_pcab_records = baseline.get("pcab", {}).get("minimum_records")
    observed_pcab_records = observed.get("pcab", {}).get("records")
    if (
        not isinstance(minimum_pcab_records, int)
        or isinstance(minimum_pcab_records, bool)
        or minimum_pcab_records <= 0
    ):
        raise SourceMonitorError("PCAB baseline record floor is invalid")
    if not isinstance(observed_pcab_records, int) or isinstance(observed_pcab_records, bool):
        raise SourceMonitorError("PCAB observed record count is invalid")
    if observed_pcab_records < minimum_pcab_records:
        differences.append("pcab: records fell below the reviewed floor")
    return tuple(differences)
