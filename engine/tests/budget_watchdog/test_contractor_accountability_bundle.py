from __future__ import annotations

import sqlite3
from pathlib import Path

from engine.budget_watchdog.contractor_accountability import (
    AccountabilitySnapshot,
    AwardTimingSignal,
    LinkedBlacklistEvent,
    LinkedCpesEvent,
)
from engine.budget_watchdog.contractor_accountability_bundle import (
    build_accountability_bundle,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64
REVISION = "1" * 40
MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0029_contractor_accountability.sql"
)


def _snapshot() -> AccountabilitySnapshot:
    blacklist = LinkedBlacklistEvent(
        order_id="order-1",
        contractor_key="pcab:12345",
        contractor_name="EXACT BUILDERS, INC.",
        pcab_id="12345",
        reported_name="Exact Builders, Inc.",
        identity_state="pcab_name_exact",
        procuring_entity="Example Department",
        project_title="Restricted project",
        start_date="2025-01-01",
        end_date="2025-12-31",
        status="expired",
        source_sha256=SHA,
    )
    cpes = LinkedCpesEvent(
        rating_id="rating-1",
        contractor_key="pcab:12345",
        contractor_name="EXACT BUILDERS, INC.",
        pcab_id="12345",
        reported_name="Exact Builders, Inc.",
        identity_state="pcab_id_exact",
        project_title="Poor project",
        evaluation_date="2025-02-01",
        implementing_agency="DPWH",
        visit_rating_bps=6_000,
        final_rating_bps=7_000,
        qualitative_rating="Poor",
        page_number=2,
        release_label="41st Release",
        source_sha256=OTHER_SHA,
        source_url="https://www.gppb.gov.ph/cpes.pdf",
    )
    signals = tuple(
        AwardTimingSignal(
            signal_id=f"signal-{index}",
            signal_type=signal_type,
            contractor_key="pcab:12345",
            contractor_name="EXACT BUILDERS, INC.",
            pcab_id="12345",
            evidence_event_id=event_id,
            contract_id=f"25AA000{index}",
            relationship="sole",
            match_basis="structured_exact",
            awardee_name="Exact Builders, Inc.",
            award_date="2025-03-01",
            contract_amount_centavos=index * 100_000_00,
            award_row_sha256=SHA,
        )
        for index, (signal_type, event_id) in enumerate(
            (("award_during_blacklist", "order-1"), ("award_after_low_cpes", "rating-1")),
            start=1,
        )
    )
    return AccountabilitySnapshot(
        checked_on="2026-11-04",
        blacklist_index_sha256=(SHA,),
        award_source_sha256=OTHER_SHA,
        award_source_revision=REVISION,
        blacklist_events=(blacklist,),
        cpes_events=(cpes,),
        award_signals=signals,
        quarantine_counts={
            "blacklist_name_only": 3,
            "cpes_missing_or_unmatched_pcab": 2,
        },
    )


def test_accountability_bundle_is_deterministic_and_replays(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    first = build_accountability_bundle(_snapshot(), output)
    second = build_accountability_bundle(_snapshot(), output)

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.blacklist_events == 1
    assert first.cpes_events == 1
    assert first.award_signals == 2
    with sqlite3.connect(":memory:") as database:
        database.executescript(MIGRATION.read_text(encoding="utf-8"))
        database.executescript((output / "contractor-accountability.sql").read_text())
        counts = database.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM contractor_blacklist_events),
              (SELECT COUNT(*) FROM contractor_cpes_events),
              (SELECT COUNT(*) FROM contractor_award_timing_signals)
            """
        ).fetchone()
        assert counts == (1, 1, 2)
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute(
            "SELECT value FROM accountability_metadata WHERE key = 'blacklist_name_only'"
        ).fetchone() == ("3",)


def test_accountability_bundle_does_not_publish_quarantined_names(tmp_path: Path) -> None:
    output = tmp_path / "bundle"

    build_accountability_bundle(_snapshot(), output)

    sql = (output / "contractor-accountability.sql").read_text(encoding="utf-8")
    assert "blacklist_name_only" in sql
    assert "Name Only Construction" not in sql
