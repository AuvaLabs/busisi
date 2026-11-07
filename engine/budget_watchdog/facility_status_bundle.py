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


def build_facility_status_sql(report: dict[str, Any]) -> tuple[str, str]:
    """Validate a monitor report and return its deterministic singleton upsert."""

    if not isinstance(report, dict):
        raise ValueError("facility status report must be an object")
    checked_at = report.get("checked_at")
    if not isinstance(checked_at, str):
        raise ValueError("facility status check time is invalid")
    try:
        parsed = datetime.fromisoformat(checked_at)
    except ValueError as exc:
        raise ValueError("facility status check time is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("facility status check time is invalid")
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
    normalized = {
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
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    values = (
        "1",
        _sql(checked_at),
        _sql(source_url),
        _sql(source_state),
        _sql(release_state),
        _nullable_integer(http_status),
        _nullable_text(artifact),
        str(expected),
        str(validated),
        str(candidates),
        str(reviewed),
        _nullable_integer(precision),
        _nullable_integer(agreement),
        str(critical),
        _sql(note.strip()),
        _sql(digest),
    )
    assignments = (
        "checked_at=excluded.checked_at, source_url=excluded.source_url, "
        "source_state=excluded.source_state, release_state=excluded.release_state, "
        "http_status=excluded.http_status, source_artifact_sha256=excluded.source_artifact_sha256, "
        "expected_facilities=excluded.expected_facilities, "
        "validated_facilities=excluded.validated_facilities, "
        "candidate_links=excluded.candidate_links, reviewed_cases=excluded.reviewed_cases, "
        "precision_bps=excluded.precision_bps, agreement_bps=excluded.agreement_bps, "
        "critical_failures=excluded.critical_failures, status_note=excluded.status_note, "
        "status_sha256=excluded.status_sha256"
    )
    sql = (
        f"INSERT INTO facility_registry_status VALUES ({', '.join(values)}) "  # noqa: S608
        f"ON CONFLICT(singleton_id) DO UPDATE SET {assignments};\n"
    )
    return sql, digest
