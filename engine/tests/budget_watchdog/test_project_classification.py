from engine.budget_watchdog.project_classification import classify_project


def _tags(description: str, category: str) -> dict[tuple[str, str], object]:
    return {
        (item.dimension, item.tag): item
        for item in classify_project(description=description, category=category)
    }


def test_classifies_farm_to_market_phase_without_collapsing_dimensions() -> None:
    tags = _tags(
        "Construction of Farm-to-Market Road, Phase 2",
        "GAA 2025 DA FMR",
    )

    assert ("project_type", "road") in tags
    assert ("purpose", "farm_to_market") in tags
    assert ("work_type", "construction") in tags
    assert ("work_type", "later_phase") in tags
    assert ("funding_program", "da_fmr") in tags
    assert tags[("purpose", "farm_to_market")].evidence_kind == "source_category_and_title"


def test_classifies_public_service_and_work_tags_independently() -> None:
    tags = _tags(
        "Repair and improvement of provincial hospital building",
        "Buildings and Facilities",
    )

    assert ("project_type", "health_facility") in tags
    assert ("project_type", "public_building") in tags
    assert ("purpose", "health") in tags
    assert ("work_type", "repair") in tags
    assert ("work_type", "improvement") in tags


def test_ignores_multipurpose_program_heading_when_project_is_another_asset() -> None:
    tags = _tags(
        "Buildings and Other Structures - Multi Purpose Facilities - "
        "Construction of airport runway",
        "Buildings and Facilities",
    )

    assert ("project_type", "multipurpose_building") not in tags
    assert ("project_type", "public_building") in tags


def test_keeps_multiple_physical_types_when_the_title_states_both() -> None:
    tags = _tags(
        "Construction of bridge and access road with drainage",
        "Bridges, Roads",
    )

    assert ("project_type", "bridge") in tags
    assert ("project_type", "road") in tags
    assert ("project_type", "flood_control") in tags
    assert ("purpose", "transport") in tags
    assert ("purpose", "flood_protection") in tags


def test_classifies_plural_public_facilities() -> None:
    tags = _tags(
        "Construction of public schools, evacuation centers, and water tanks",
        "Buildings and Facilities",
    )

    assert ("project_type", "school") in tags
    assert ("project_type", "evacuation_center") in tags
    assert ("project_type", "water_system") in tags
    assert ("purpose", "education") in tags
    assert ("purpose", "disaster_response") in tags
    assert ("purpose", "water_access") in tags


def test_returns_no_tag_when_the_source_text_does_not_support_one() -> None:
    assert classify_project(description="Other works", category="GAA 2025 CP") == ()
