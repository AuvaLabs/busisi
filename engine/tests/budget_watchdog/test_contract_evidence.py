import json
from pathlib import Path

import pytest

from engine.budget_watchdog.contract_evidence import (
    ContractEvidenceError,
    load_contract_evidence_catalog,
    summarize_contract_evidence,
)

FIXTURE = Path("ops/harness/fixtures/contract_evidence_catalog.json")


def test_loads_complete_contract_evidence_checklists() -> None:
    catalog = load_contract_evidence_catalog(FIXTURE.read_bytes())
    summary = summarize_contract_evidence(catalog)

    assert summary.contract_count == 3
    assert summary.item_count == 27
    assert summary.status_counts == {
        "blocked": 3,
        "not_located": 20,
        "secondary": 3,
        "verified_archived": 1,
    }
    phase_two = [item for item in catalog.items if item.contract_id == "24HI0131"]
    assert [item.stage for item in phase_two] == list(catalog.stage_order)
    assert next(item for item in phase_two if item.stage == "notice_to_proceed").reported_date == "2024-06-27"


def _raw() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rejects_incomplete_lifecycle_checklist() -> None:
    raw = _raw()
    raw["items"] = raw["items"][:-1]

    with pytest.raises(ContractEvidenceError, match="complete lifecycle checklist"):
        load_contract_evidence_catalog(json.dumps(raw).encode())


def test_rejects_archived_evidence_without_verified_bytes() -> None:
    raw = _raw()
    item = next(entry for entry in raw["items"] if entry["status"] == "verified_archived")
    item["artifact_sha256"] = None

    with pytest.raises(ContractEvidenceError, match="archived evidence"):
        load_contract_evidence_catalog(json.dumps(raw).encode())


def test_rejects_secondary_evidence_without_revision_and_row_hash() -> None:
    raw = _raw()
    item = next(entry for entry in raw["items"] if entry["status"] == "secondary")
    item["source_revision"] = None

    with pytest.raises(ContractEvidenceError, match="secondary evidence"):
        load_contract_evidence_catalog(json.dumps(raw).encode())


def test_rejects_blocked_evidence_without_retryable_http_failure() -> None:
    raw = _raw()
    item = next(entry for entry in raw["items"] if entry["status"] == "blocked")
    item["http_status"] = 200

    with pytest.raises(ContractEvidenceError, match="blocked evidence"):
        load_contract_evidence_catalog(json.dumps(raw).encode())


@pytest.mark.parametrize(("payload", "message"), [
    (b"{broken", "JSON is invalid"),
    (json.dumps({"schema_version": 2}).encode(), "schema version"),
])
def test_rejects_invalid_catalog_boundary(payload: bytes, message: str) -> None:
    with pytest.raises(ContractEvidenceError, match=message):
        load_contract_evidence_catalog(payload)
