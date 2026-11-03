from datetime import date

from engine.budget_watchdog.integrity import (
    DeliveryIntegrityRecord,
    build_integrity_snapshot,
    contractor_identity,
)


def _record(
    contract_id: str,
    *,
    description: str = "Construction of public market",
    status: str = "On-Going",
    budget_centavos: int = 10_000_000,
    progress: str = "50",
    contractor: str = "ACME BUILDERS (12345)",
    latitude: str | None = "14.5995",
    longitude: str | None = "120.9842",
    province: str = "Metro Manila 1st DEO",
    region: str = "National Capital Region",
    start_date: date | None = date(2025, 1, 1),
    completion_date: date | None = date(2025, 12, 1),
    has_satellite_image: bool = True,
) -> DeliveryIntegrityRecord:
    return DeliveryIntegrityRecord(
        contract_id=contract_id,
        fiscal_year=2025,
        description=description,
        category="Buildings and Facilities",
        status=status,
        budget_centavos=budget_centavos,
        progress=progress,
        province=province,
        region=region,
        contractor=contractor,
        start_date=start_date,
        completion_date=completion_date,
        latitude=latitude,
        longitude=longitude,
        has_satellite_image=has_satellite_image,
        source_artifact_sha256="a" * 64,
    )


def test_contractor_identity_prefers_pcab_number() -> None:
    identity = contractor_identity("ACME BUILDERS, INC. (FORMERLY ACME) (12345)")

    assert identity.key == "pcab:12345"
    assert identity.pcab_id == "12345"
    assert identity.display_name == "ACME BUILDERS, INC. (FORMERLY ACME)"


def test_integrity_snapshot_emits_disclosed_rules_and_contractor_totals() -> None:
    records = (
        _record("25A", progress="100", budget_centavos=10_000_000),
        _record(
            "25B",
            description="Repair of provincial hospital",
            status="Completed",
            progress="0",
            budget_centavos=20_000_000,
            province="Quezon 1st DEO",
            region="Region IV-A",
            latitude="13.9411",
            longitude="121.6234",
            has_satellite_image=False,
        ),
        _record(
            "25C",
            description="Construction of evacuation center",
            budget_centavos=0,
            contractor="SECOND BUILDERS (67890)",
            latitude=None,
            longitude=None,
            start_date=date(2025, 3, 1),
            completion_date=date(2025, 2, 1),
        ),
    )

    snapshot = build_integrity_snapshot(records)

    by_contract = {
        contract_id: {
            signal.code for signal in snapshot.signals if signal.contract_id == contract_id
        }
        for contract_id in ("25A", "25B", "25C")
    }
    assert by_contract["25A"] == {"status_progress_conflict"}
    assert by_contract["25B"] == {
        "completed_progress_conflict",
        "completed_without_satellite_image",
    }
    assert by_contract["25C"] == {
        "date_order_conflict",
        "missing_coordinate",
        "nonpositive_active_budget",
    }
    acme = next(item for item in snapshot.contractors if item.pcab_id == "12345")
    assert acme.project_count == 2
    assert acme.total_budget_centavos == 30_000_000
    assert acme.completed_count == 1
    assert acme.ongoing_count == 1


def test_integrity_snapshot_flags_reused_coordinates_without_claiming_duplication() -> None:
    records = (
        _record("25A", description="Construction of public market"),
        _record(
            "25B",
            description="Rehabilitation of public school",
            contractor="SECOND BUILDERS (67890)",
        ),
        _record(
            "25C",
            description="Construction of health center",
            contractor="THIRD BUILDERS (24680)",
            province="Cebu 1st DEO",
            region="Region VII",
        ),
    )

    snapshot = build_integrity_snapshot(records)

    reused = [signal for signal in snapshot.signals if signal.code == "reused_coordinate"]
    conflicts = [
        signal for signal in snapshot.signals if signal.code == "coordinate_location_conflict"
    ]
    assert len(reused) == 3
    assert len(conflicts) == 3
    assert all(signal.classification == "identity_review" for signal in reused)
    assert all("not proof" in signal.limitations.casefold() for signal in reused)


def test_integrity_snapshot_is_stable_across_input_order() -> None:
    records = (_record("25B"), _record("25A", contractor="SECOND BUILDERS (67890)"))

    first = build_integrity_snapshot(records)
    second = build_integrity_snapshot(tuple(reversed(records)))

    assert first == second
