"""Build a validated public status update for the facility registry pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.facility_release_gate import (
    MIN_AGREEMENT_BPS,
    MIN_PRECISION_BPS,
    MIN_REVIEWED_CASES,
)

_SOURCE_STATES = frozenset(
    {"blocked", "unavailable", "acquisition_failure", "validation_failure", "validated"}
)
_RELEASE_STATES = frozenset(
    {
        "source_blocked",
        "source_unavailable",
        "acquisition_failed",
        "validation_failed",
        "awaiting_review",
        "gate_failed",
        "ready_for_publication",
        "published",
    }
)
_RELEASES_BY_SOURCE = {
    "blocked": frozenset({"source_blocked"}),
    "unavailable": frozenset({"source_unavailable"}),
    "acquisition_failure": frozenset({"acquisition_failed"}),
    "validation_failure": frozenset({"validation_failed"}),
    "validated": frozenset(
        {"awaiting_review", "gate_failed", "ready_for_publication", "published"}
    ),
}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SOURCE_PATH = "/wp-content/uploads/List-of-PSIP-III-Sites.xlsx"
_CANDIDATE_PATH = (
    "/wp-content/uploads/"
    "Deped-Announcement-on-PPP-Indicative-List-of-Schools-Annex-A-2025-12-08_1.pdf"
)
_FAILURE_KINDS = frozenset(
    {
        "publisher_maintenance",
        "bot_challenge",
        "rate_limited",
        "server_error",
        "access_denied",
        "not_found",
        "transport_error",
        "unexpected_response",
        "validation_error",
    }
)
_FRESHNESS_STATES = frozenset({"fresh", "degraded", "stale", "unknown"})
_CANDIDATE_STATES = frozenset({"discovered_unarchived", "archived_unvalidated", "validated"})


def _sql(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _nullable_text(value: str | None) -> str:
    return "NULL" if value is None else _sql(value)


def _nullable_integer(value: int | None) -> str:
    return "NULL" if value is None else str(value)


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"facility status {label} is invalid")
    return value


def _optional_score(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label, 0, 10_000)


def _source_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("facility status source URL is invalid")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.deped.gov.ph"
        or parsed.path != _SOURCE_PATH
    ):
        raise ValueError("facility status source URL is invalid")
    return value


def _timestamp(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"facility status {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"facility status {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"facility status {label} is invalid")
    return value


def _candidate_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("facility status candidate source URL is invalid")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.deped.gov.ph"
        or parsed.path != _CANDIDATE_PATH
    ):
        raise ValueError("facility status candidate source URL is invalid")
    return value


def _validate_release_gate(
    release_state: Any,
    reviewed: int,
    precision: int | None,
    agreement: int | None,
    critical: int,
) -> None:
    if release_state not in {"ready_for_publication", "published"}:
        return
    if (
        reviewed < MIN_REVIEWED_CASES
        or precision is None
        or precision < MIN_PRECISION_BPS
        or agreement is None
        or agreement < MIN_AGREEMENT_BPS
        or critical != 0
    ):
        raise ValueError("facility status release gate controls do not reconcile")


def _core_status(report: dict[str, Any]) -> dict[str, Any]:
    checked_at = _timestamp(report.get("checked_at"), "check time")
    assert checked_at is not None
    source_url = _source_url(report.get("source_url"))
    source_state = report.get("source_state")
    release_state = report.get("release_state")
    if source_state not in _SOURCE_STATES:
        raise ValueError("facility status source state is invalid")
    if release_state not in _RELEASE_STATES:
        raise ValueError("facility status release state is invalid")
    if release_state not in _RELEASES_BY_SOURCE[source_state]:
        raise ValueError("facility status source and release states do not agree")
    http_status = report.get("http_status")
    if http_status is not None:
        http_status = _integer(http_status, "HTTP status", 100, 599)
    artifact = report.get("source_artifact_sha256")
    if artifact is not None and (
        not isinstance(artifact, str) or _SHA256.fullmatch(artifact) is None
    ):
        raise ValueError("facility status source artifact digest is invalid")
    expected = _integer(report.get("expected_facilities"), "expected facilities", 1, 100_000)
    validated = _integer(report.get("validated_facilities"), "validated facilities", 0, expected)
    candidates = _integer(report.get("candidate_links"), "candidate links", 0, 1_000_000)
    reviewed = _integer(report.get("reviewed_cases"), "reviewed cases", 0, 1_000_000)
    precision = _optional_score(report.get("precision_bps"), "precision")
    agreement = _optional_score(report.get("agreement_bps"), "agreement")
    critical = _integer(report.get("critical_failures"), "critical failures", 0, 1_000_000)
    note = report.get("status_note")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("facility status note is invalid")
    if source_state == "validated" and (artifact is None or validated != expected):
        raise ValueError("facility status validated source controls do not reconcile")
    _validate_release_gate(release_state, reviewed, precision, agreement, critical)
    return {
        "checked_at": checked_at,
        "source_url": source_url,
        "source_state": source_state,
        "release_state": release_state,
        "http_status": http_status,
        "source_artifact_sha256": artifact,
        "expected_facilities": expected,
        "validated_facilities": validated,
        "candidate_links": candidates,
        "reviewed_cases": reviewed,
        "precision_bps": precision,
        "agreement_bps": agreement,
        "critical_failures": critical,
        "status_note": note.strip(),
    }


def _resilience_status(report: dict[str, Any], source_state: str) -> dict[str, Any]:
    failure_kind = report.get("failure_kind")
    if failure_kind is not None and failure_kind not in _FAILURE_KINDS:
        raise ValueError("facility status failure kind is invalid")
    last_success_at = _timestamp(report.get("last_success_at"), "last success time", optional=True)
    consecutive_failures = _integer(
        report.get("consecutive_failures"), "consecutive failures", 0, 1_000_000
    )
    next_check_at = _timestamp(report.get("next_check_at"), "next check time", optional=True)
    freshness_state = report.get("freshness_state")
    if freshness_state not in _FRESHNESS_STATES:
        raise ValueError("facility status freshness state is invalid")
    response_sha256 = report.get("response_sha256")
    if response_sha256 is not None and (
        not isinstance(response_sha256, str) or _SHA256.fullmatch(response_sha256) is None
    ):
        raise ValueError("facility status response digest is invalid")
    source_version = report.get("source_version")
    if source_version != "legacy-xlsx-1095":
        raise ValueError("facility status source version is invalid")
    candidate_source_url = _candidate_url(report.get("candidate_source_url"))
    candidate_state = report.get("candidate_state")
    if candidate_state not in _CANDIDATE_STATES:
        raise ValueError("facility status candidate state is invalid")
    if source_state == "validated":
        if failure_kind is not None or consecutive_failures != 0 or freshness_state != "fresh":
            raise ValueError("facility status successful source health does not reconcile")
    elif failure_kind is None or consecutive_failures < 1:
        raise ValueError("facility status failed source health does not reconcile")
    return {
        "failure_kind": failure_kind,
        "last_success_at": last_success_at,
        "consecutive_failures": consecutive_failures,
        "next_check_at": next_check_at,
        "freshness_state": freshness_state,
        "response_sha256": response_sha256,
        "source_version": source_version,
        "candidate_source_url": candidate_source_url,
        "candidate_state": candidate_state,
    }


def _status_values(normalized: dict[str, Any], digest: str) -> tuple[str, ...]:
    nullable_text = {
        "failure_kind",
        "last_success_at",
        "next_check_at",
        "response_sha256",
    }
    nullable_integer = {"http_status", "precision_bps", "agreement_bps"}
    integers = {
        "expected_facilities",
        "validated_facilities",
        "candidate_links",
        "reviewed_cases",
        "critical_failures",
        "consecutive_failures",
    }
    ordered = (
        "checked_at",
        "source_url",
        "source_state",
        "release_state",
        "http_status",
        "source_artifact_sha256",
        "expected_facilities",
        "validated_facilities",
        "candidate_links",
        "reviewed_cases",
        "precision_bps",
        "agreement_bps",
        "critical_failures",
        "status_note",
        "failure_kind",
        "last_success_at",
        "consecutive_failures",
        "next_check_at",
        "freshness_state",
        "response_sha256",
        "source_version",
        "candidate_source_url",
        "candidate_state",
    )
    values = ["1"]
    for key in ordered:
        value = normalized[key]
        if key in nullable_text or key == "source_artifact_sha256":
            values.append(_nullable_text(value))
        elif key in nullable_integer:
            values.append(_nullable_integer(value))
        elif key in integers:
            values.append(str(value))
        else:
            values.append(_sql(value))
        if key == "status_note":
            values.append(_sql(digest))
    return tuple(values)


def _status_sql(normalized: dict[str, Any], digest: str) -> str:
    columns = (
        "singleton_id",
        "checked_at",
        "source_url",
        "source_state",
        "release_state",
        "http_status",
        "source_artifact_sha256",
        "expected_facilities",
        "validated_facilities",
        "candidate_links",
        "reviewed_cases",
        "precision_bps",
        "agreement_bps",
        "critical_failures",
        "status_note",
        "status_sha256",
        "failure_kind",
        "last_success_at",
        "consecutive_failures",
        "next_check_at",
        "freshness_state",
        "response_sha256",
        "source_version",
        "candidate_source_url",
        "candidate_state",
    )
    mutable = columns[1:]
    assignments = ", ".join(f"{column}=excluded.{column}" for column in mutable)
    values = _status_values(normalized, digest)
    return (
        f"INSERT INTO facility_registry_status ({', '.join(columns)}) "  # noqa: S608
        f"VALUES ({', '.join(values)}) ON CONFLICT(singleton_id) "
        f"DO UPDATE SET {assignments};\n"
    )


def build_facility_status_sql(report: dict[str, Any]) -> tuple[str, str]:
    """Validate a monitor report and return its deterministic singleton upsert."""

    if not isinstance(report, dict):
        raise ValueError("facility status report must be an object")
    normalized = _core_status(report)
    normalized.update(_resilience_status(report, normalized["source_state"]))
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return _status_sql(normalized, digest), digest
