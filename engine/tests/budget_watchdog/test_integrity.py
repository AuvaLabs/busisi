from datetime import date

from engine.budget_watchdog.integrity import (
    DeliveryIntegrityRecord,
    build_integrity_snapshot,
    contractor_concentrations,
    contractor_identities,
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
    fiscal_year: int = 2025,
) -> DeliveryIntegrityRecord:
    return DeliveryIntegrityRecord(
        contract_id=contract_id,
        fiscal_year=fiscal_year,
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


def test_contractor_identities_split_joint_ventures_without_losing_pcab_numbers() -> None:
    identities = contractor_identities(
        "VIKING CONSTRUCTION & SUPPLIES (18129) / BJMJB CONSTRUCTION & SUPPLY (44546)"
    )

    assert [(item.display_name, item.pcab_id) for item in identities] == [
        ("VIKING CONSTRUCTION & SUPPLIES", "18129"),
        ("BJMJB CONSTRUCTION & SUPPLY", "44546"),
    ]


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


def test_integrity_snapshot_tracks_joint_venture_parties_and_supported_followup_rules() -> None:
    contractor = "ACME BUILDERS (12345) / SECOND BUILDERS (67890)"
    records = (
        _record(
            "24A",
            contractor=contractor,
            fiscal_year=2024,
            description="Construction of San Isidro public market Phase I",
            completion_date=date(2024, 12, 1),
        ),
        _record(
            "25A",
            contractor=contractor,
            fiscal_year=2025,
            description="Construction of San Isidro public market Phase II",
            completion_date=date(2025, 6, 1),
        ),
    )

    snapshot = build_integrity_snapshot(records, as_of=date(2026, 1, 22))

    for pcab_id in ("12345", "67890"):
        contractor_summary = next(item for item in snapshot.contractors if item.pcab_id == pcab_id)
        assert contractor_summary.project_count == 2
        assert contractor_summary.joint_project_count == 2
        assert contractor_summary.total_budget_centavos == 20_000_000
    by_code = {signal.code for signal in snapshot.signals}
    assert "past_completion_not_complete" in by_code
    assert "same_site_repeat_family" in by_code


def test_contractor_concentrations_use_party_associations_as_the_denominator() -> None:
    records = (
        _record("25A", contractor="ACME BUILDERS (12345) / SECOND BUILDERS (67890)"),
        _record("25B", contractor="ACME BUILDERS (12345)"),
        _record("25C", contractor="", budget_centavos=30_000_000),
    )

    concentrations = contractor_concentrations(records, minimum_projects=1)

    overall = next(
        item
        for item in concentrations
        if item.dimension == "region"
        and item.group_label == "National Capital Region"
        and item.fiscal_year == 0
    )
    assert overall.project_count == 3
    assert overall.named_project_count == 2
    assert overall.party_association_count == 3
    assert overall.contractor_count == 2
    assert overall.top_contractor_name == "ACME BUILDERS"
    assert overall.top_project_count == 2
    assert overall.top_share_basis_points == 6666
    assert overall.top_associated_budget_centavos == 20_000_000
