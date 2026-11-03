"""Build a validated singleton D1 update for public source-monitor status."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

_STATUSES = frozenset(
    {
        "unchanged",
        "drift_detected",
        "acquisition_or_validation_failure",
    }
)


def _sql(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"source monitor {label} must be a text list")
    return value


def _limitations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("source monitor limitations must be a list")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("source monitor limitation must be an object")
        source = item.get("source")
        effect = item.get("effect")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source monitor limitation source is invalid")
        if not isinstance(effect, str) or not effect.strip():
            raise ValueError("source monitor limitation effect is invalid")
        result.append({"source": source, "effect": effect})
    return result


def build_source_status_sql(report: dict[str, Any]) -> tuple[str, str]:
    """Validate a monitor report and return its deterministic public upsert."""
    checked_at = report.get("checked_at")
    status = report.get("status")
    if not isinstance(checked_at, str):
        raise ValueError("source monitor check time is invalid")
    try:
        parsed_time = datetime.fromisoformat(checked_at)
    except ValueError as exc:
        raise ValueError("source monitor check time is invalid") from exc
    if parsed_time.tzinfo is None:
        raise ValueError("source monitor check time must be timezone-aware")
    if status not in _STATUSES:
        raise ValueError("source monitor status is invalid")
    differences = _text_list(report.get("differences", []), "differences")
    limitations = _limitations(report.get("known_discovery_limits", []))
    observed = report.get("observed")
    if not isinstance(observed, dict):
        raise ValueError("source monitor observation must be an object")
    observed_json = json.dumps(observed, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(observed_json.encode()).hexdigest()
    differences_json = json.dumps(differences, separators=(",", ":"))
    limitations_json = json.dumps(limitations, separators=(",", ":"))
    values = ", ".join(
        (
            "1",
            _sql(checked_at),
            _sql(status),
            _sql(differences_json),
            _sql(limitations_json),
            _sql(digest),
        )
    )
    sql = (
        f"INSERT INTO source_monitor_status VALUES ({values}) "  # noqa: S608
        "ON CONFLICT(singleton_id) DO UPDATE SET "
        "checked_at=excluded.checked_at, status=excluded.status, "
        "differences_json=excluded.differences_json, "
        "limitations_json=excluded.limitations_json, "
        "observations_sha256=excluded.observations_sha256;\n"
    )
    return sql, digest
