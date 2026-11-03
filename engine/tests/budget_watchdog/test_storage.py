import sqlite3
from datetime import UTC, datetime

import pytest

from engine.budget_watchdog.identity import BudgetProject, DeliveryProject
from engine.budget_watchdog.parquet_snapshots import SnapshotIssue
from engine.budget_watchdog.storage import CanonicalStore, StorageConflictError

ARTIFACT_SHA = "a" * 64
UPDATED_AT = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def _budget(description: str = "Construction of Sample Building") -> BudgetProject:
    return BudgetProject(
        budget_line_id="18-001|sample-building",
        fiscal_year=2026,
        description=description,
        amount_centavos=1_000_000_000,
        location="Sample City",
    )


def _delivery() -> DeliveryProject:
    return DeliveryProject(
        contract_id="26XX0001",
        fiscal_year=2026,
        description="CONSTRUCTION OF SAMPLE BUILDING, SAMPLE CITY",
        budget_centavos=990_000_000,
        location="Sample DEO",
        source_of_funds="GAA 2026",
    )


def test_store_persists_canonical_records_across_reopen(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    with CanonicalStore(database) as store:
        assert store.store_budget_projects((_budget(),), ARTIFACT_SHA) == 1
        assert store.store_delivery_projects((_delivery(),), ARTIFACT_SHA) == 1

    with CanonicalStore(database) as reopened:
        budgets = reopened.list_budget_projects(fiscal_year=2026)
        deliveries = reopened.list_delivery_projects(fiscal_year=2026)

    assert budgets == (_budget(),)
    assert deliveries == (_delivery(),)


def test_store_is_idempotent_and_rejects_same_snapshot_conflict(tmp_path) -> None:
    with CanonicalStore(tmp_path / "watchdog.sqlite3") as store:
        assert store.store_budget_projects((_budget(),), ARTIFACT_SHA) == 1
        assert store.store_budget_projects((_budget(),), ARTIFACT_SHA) == 0

        with pytest.raises(StorageConflictError, match="immutable"):
            store.store_budget_projects((_budget("Changed description"),), ARTIFACT_SHA)


def test_store_refreshes_derived_family_without_mutating_source_record(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    with CanonicalStore(database) as store:
        store.store_delivery_projects((_delivery(),), ARTIFACT_SHA)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_projects SET project_family_id = ?",
            ("stale-family",),
        )

    with CanonicalStore(database) as store:
        assert store.store_delivery_projects((_delivery(),), ARTIFACT_SHA) == 0
    with sqlite3.connect(database) as connection:
        family_id = connection.execute(
            "SELECT project_family_id FROM delivery_projects"
        ).fetchone()[0]

    assert family_id != "stale-family"


def test_checkpoint_is_resumable_and_explicitly_completed(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    with CanonicalStore(database) as store:
        store.save_checkpoint(
            source_id="bettergov-budget",
            stream_id="dpwh-programs-2026",
            position="cursor-2",
            completed=False,
            updated_at=UPDATED_AT,
        )

    with CanonicalStore(database) as reopened:
        checkpoint = reopened.get_checkpoint(
            source_id="bettergov-budget",
            stream_id="dpwh-programs-2026",
        )

    assert checkpoint is not None
    assert checkpoint.position == "cursor-2"
    assert checkpoint.completed is False
    assert checkpoint.updated_at == UPDATED_AT


def test_store_persists_quarantine_evidence_idempotently(tmp_path) -> None:
    issue = SnapshotIssue(
        row_number=42,
        code="invalid_gaa_row",
        detail="description has no canonical text",
        source_identifier="'-'",
        amount_centavos=219_400_000,
    )
    with CanonicalStore(tmp_path / "watchdog.sqlite3") as store:
        assert store.store_quarantine_issues((issue,), ARTIFACT_SHA) == 1
        assert store.store_quarantine_issues((issue,), ARTIFACT_SHA) == 0
        assert store.count_quarantine_issues(artifact_sha256=ARTIFACT_SHA) == 1
