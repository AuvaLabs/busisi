from engine.budget_watchdog.family import build_family_identity


def test_family_identity_groups_phase_and_completion_variants() -> None:
    phase_one = build_family_identity(
        "Construction of Multi-Purpose Building, Phase 1, Barangay Corazon, Catmon, Cebu"
    )
    completion = build_family_identity(
        "Construction (Completion) of Multi-Purpose Building, Barangay Corazon, Catmon, Cebu"
    )

    assert phase_one.family_id == completion.family_id
    assert phase_one.canonical_text == completion.canonical_text


def test_family_identity_removes_known_program_boilerplate() -> None:
    phase_one = build_family_identity(
        "Construction of Multi-Purpose Building, Phase 1, Barangay Corazon, Catmon, Cebu"
    )
    completion = build_family_identity(
        "CSSP: Basic Infrastructure Program (BIP) - Multi-Purpose Buildings/Facilities "
        "to Support Social Services - Construction (Completion) of Multi-Purpose "
        "Building, Barangay Corazon, Catmon, Cebu"
    )

    assert phase_one.family_id == completion.family_id


def test_family_identity_does_not_merge_different_locations() -> None:
    catmon = build_family_identity(
        "Construction of Multi-Purpose Building, Barangay Corazon, Catmon, Cebu"
    )
    calumpit = build_family_identity(
        "Construction of Multi-Purpose Building, Barangay Corazon, Calumpit, Bulacan"
    )

    assert catmon.family_id != calumpit.family_id


def test_family_identity_retains_distinct_asset_types() -> None:
    building = build_family_identity(
        "Construction of Multi-Purpose Building, Barangay Corazon, Catmon, Cebu"
    )
    road = build_family_identity("Construction of Road, Barangay Corazon, Catmon, Cebu")

    assert building.family_id != road.family_id
