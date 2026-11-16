"""Build a validated public source-status record for poverty estimates."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.poverty_estimates import PSA_POVERTY_SOURCE_URL

_SOURCE_STATES = frozenset({"blocked", "acquisition_failure", "validation_failure", "validated"})
_PUBLICATION_STATES = frozenset({"not_published", "ready_for_review", "published"})
_FAILURE_KINDS = frozenset(
    {
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
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _timestamp(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"poverty status {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"poverty status {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"poverty status {label} is invalid")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"poverty status {label} is invalid")
    return value


def _digest(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"poverty status {label} is invalid")
    return value


def _normalize(report: dict[str, Any]) -> dict[str, Any]:
    source_url = report.get("source_url")
    if source_url != PSA_POVERTY_SOURCE_URL or urlparse(source_url).scheme != "https":
        raise ValueError("poverty status source URL is invalid")
    source_state = report.get("source_state")
    publication_state = report.get("publication_state")
    if source_state not in _SOURCE_STATES or publication_state not in _PUBLICATION_STATES:
        raise ValueError("poverty status state is invalid")
    expected = _integer(report.get("expected_records"), "expected records", 1, 10_000)
    validated = _integer(report.get("validated_records"), "validated records", 0, expected)
    if source_state != "validated" and validated != 0:
        raise ValueError("poverty status failed source cannot claim validated rows")
    if source_state == "validated" and validated != expected:
        raise ValueError("poverty status validated row count does not reconcile")
    if source_state != "validated" and publication_state != "not_published":
        raise ValueError("poverty status failed source must remain unpublished")
    return _normalized_fields(report, source_state, publication_state, expected, validated)


def _normalized_fields(
    report: dict[str, Any],
    source_state: str,
    publication_state: str,
    expected: int,
    validated: int,
) -> dict[str, Any]:
    failure_kind = report.get("failure_kind")
    if failure_kind is not None and failure_kind not in _FAILURE_KINDS:
        raise ValueError("poverty status failure kind is invalid")
    if source_state == "validated" and failure_kind is not None:
        raise ValueError("poverty status successful source cannot have a failure")
    note = report.get("status_note")
    freshness = report.get("freshness_state")
    if not isinstance(note, str) or not note.strip() or freshness not in _FRESHNESS_STATES:
        raise ValueError("poverty status public explanation is invalid")
    http_status = report.get("http_status")
    if http_status is not None:
        http_status = _integer(http_status, "HTTP status", 100, 599)
    return {
        "checked_at": _timestamp(report.get("checked_at"), "check time"),
        "source_url": PSA_POVERTY_SOURCE_URL,
        "source_state": source_state,
        "publication_state": publication_state,
        "http_status": http_status,
        "source_sha256": _digest(report.get("source_sha256"), "source digest", optional=True),
        "expected_records": expected,
        "validated_records": validated,
        "failure_kind": failure_kind,
        "last_success_at": _timestamp(report.get("last_success_at"), "last success", optional=True),
        "consecutive_failures": _integer(
            report.get("consecutive_failures"), "consecutive failures", 0, 1_000_000
        ),
        "next_check_at": _timestamp(report.get("next_check_at"), "next check", optional=True),
        "freshness_state": freshness,
        "response_sha256": _digest(report.get("response_sha256"), "response digest", optional=True),
        "status_note": note.strip(),
    }


def _sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return f"'{str(value).replace("'", "''")}'"


def build_poverty_status_sql(report: dict[str, Any]) -> tuple[str, str]:
    """Validate and serialize one replaceable public status row."""

    normalized = _normalize(report)
    canonical = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    order = tuple(normalized)
    values = ", ".join(_sql(normalized[key]) for key in order)
    columns = ", ".join(order)
    insert = (
        f"INSERT INTO community_poverty_status (singleton_id, {columns}, status_sha256) "  # noqa: S608
        f"VALUES (1, {values}, '{digest}');\n"
    )
    statement = "DELETE FROM community_poverty_status;\n" + insert  # noqa: S608
    return statement, digest
