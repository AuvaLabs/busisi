from engine.budget_watchdog.facility_identity import (
    FacilityMention,
    FacilityRegistryRecord,
    FacilityTitleRecord,
    link_facility,
    link_school_title,
)


def _school(
    facility_id: str = "deped:136505",
    official_id: str = "136505",
    name: str = "San Antonio Elementary School",
    municipality: str = "Quezon City",
) -> FacilityRegistryRecord:
    return FacilityRegistryRecord(
        facility_id=facility_id,
        facility_type="school",
        official_id=official_id,
        official_name=name,
        municipality=municipality,
        province="Metro Manila",
        region="NCR",
        source_id="deped-ppp-2025",
    )


def test_exact_official_id_and_compatible_place_publish_identity() -> None:
    mention = FacilityMention(
        source_type="delivery",
        record_id="25AA0001",
        facility_type="school",
        facility_name="San Antonio ES",
        municipality="Quezon City",
        province="Metro Manila",
        official_id="136505",
    )

    link = link_facility(mention, (_school(),))

    assert link.match_state == "official_exact"
    assert link.facility_id == "deped:136505"
    assert link.confidence == 100
    assert link.signals == ("official_id", "facility_type", "place")


def test_exact_normalized_name_and_place_can_publish_identity_without_id() -> None:
    mention = FacilityMention(
        source_type="budget",
        record_id="dpwh:school",
        facility_type="school",
        facility_name="San Antonio Elementary School",
        municipality="Quezon City",
        province="Metro Manila",
    )

    link = link_facility(mention, (_school(),))

    assert link.match_state == "official_exact"
    assert link.facility_id == "deped:136505"
    assert link.confidence == 95
    assert link.signals == ("exact_name", "facility_type", "place")


def test_repeated_name_without_a_unique_place_is_quarantined() -> None:
    mention = FacilityMention(
        source_type="budget",
        record_id="dpwh:school",
        facility_type="school",
        facility_name="San Antonio Elementary School",
    )
    registry = (
        _school(),
        _school("deped:999999", "999999", municipality="Pasig City"),
    )

    link = link_facility(mention, registry)

    assert link.match_state == "ambiguous"
    assert link.facility_id is None
    assert link.confidence == 0
    assert link.signals == ("multiple_exact_names", "place_missing")


def test_place_conflict_holds_an_official_id_for_review() -> None:
    mention = FacilityMention(
        source_type="delivery",
        record_id="25AA0002",
        facility_type="school",
        facility_name="San Antonio Elementary School",
        municipality="Pasig City",
        province="Metro Manila",
        official_id="136505",
    )

    link = link_facility(mention, (_school(),))

    assert link.match_state == "ambiguous"
    assert link.facility_id is None
    assert link.signals == ("official_id", "place_conflict")


def test_unmatched_name_and_place_create_only_a_record_group() -> None:
    mention = FacilityMention(
        source_type="delivery",
        record_id="25HOSP01",
        facility_type="hospital",
        facility_name="District Hospital",
        municipality="Cebu City",
        province="Cebu",
    )

    first = link_facility(mention, ())
    second = link_facility(mention, ())

    assert first.match_state == "group_only"
    assert first.facility_id is None
    assert first.record_group_key == second.record_group_key
    assert first.record_group_key.startswith("facility-group:")
    assert first.confidence == 70


def test_missing_facility_name_remains_unlinked() -> None:
    mention = FacilityMention(
        source_type="budget",
        record_id="hfep:2",
        facility_type="health_center",
        facility_name="",
        province="Cebu",
    )

    link = link_facility(mention, ())

    assert link.match_state == "unlinked"
    assert link.facility_id is None
    assert link.record_group_key is None
    assert link.confidence == 0


def test_school_title_match_expands_suffix_and_requires_place() -> None:
    registry = (_school(name="Agtangao ES", municipality="Bangued (Capital)"),)
    record = FacilityTitleRecord(
        source_type="delivery",
        record_id="25AB0001",
        title="Construction of School Building, Agtangao Elementary School, Bangued, Abra",
        location="Abra DEO, CAR",
    )

    link = link_school_title(record, registry)

    assert link.match_state == "official_exact"
    assert link.facility_id == "deped:136505"
    assert link.confidence == 95
    assert link.signals == ("exact_registry_name_in_title", "place_in_record")


def test_school_title_without_place_or_with_multiple_candidates_is_ambiguous() -> None:
    registry = (
        _school(name="San Antonio Elementary School", municipality="Quezon City"),
        _school("deped:999999", "999999", name="San Antonio ES", municipality="Pasig City"),
    )
    no_place = FacilityTitleRecord(
        source_type="budget",
        record_id="dpwh:school",
        title="Repair of San Antonio Elementary School classrooms",
        location="NCR",
    )
    multiple = FacilityTitleRecord(
        source_type="delivery",
        record_id="25AA0003",
        title="Facilities for San Antonio ES in Quezon City and Pasig City",
        location="NCR",
    )

    assert link_school_title(no_place, registry).match_state == "ambiguous"
    assert link_school_title(no_place, registry).facility_id is None
    assert link_school_title(multiple, registry).match_state == "ambiguous"


def test_unmatched_school_title_remains_unlinked() -> None:
    record = FacilityTitleRecord(
        source_type="delivery",
        record_id="25AA0004",
        title="Construction of Unlisted Elementary School, Cebu",
        location="Cebu DEO, Region VII",
    )

    link = link_school_title(record, (_school(),))

    assert link.match_state == "unlinked"
    assert link.facility_id is None
    assert link.signals == ("no_exact_registry_name",)
