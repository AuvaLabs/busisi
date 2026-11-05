# ruff: noqa: S608

from engine.budget_watchdog.review_sources import load_delivery_contexts


def test_loads_only_requested_saved_delivery_details(tmp_path) -> None:
    detail_schema = tmp_path / "details.sql"
    detail_schema.write_text(
        """
        CREATE TABLE delivery_project_details (
          contract_id TEXT, fiscal_year INTEGER, category TEXT, status TEXT, progress TEXT,
          contractor_name TEXT, contractor_parties_json TEXT, start_date TEXT,
          completion_date TEXT, province TEXT, region TEXT, latitude TEXT, longitude TEXT,
          has_satellite_image INTEGER, source_artifact_sha256 TEXT
        );
        """
    )
    signal_schema = tmp_path / "signals.sql"
    signal_schema.write_text(
        """
        CREATE TABLE integrity_signal_items (
          signal_id TEXT, contract_id TEXT, fiscal_year INTEGER, code TEXT,
          classification TEXT, label TEXT, description TEXT, contractor_name TEXT,
          pcab_id TEXT, budget_centavos INTEGER, status TEXT, progress TEXT,
          province TEXT, region TEXT, latitude TEXT, longitude TEXT, evidence TEXT,
          limitations TEXT, source_artifact_sha256 TEXT
        );
        """
    )
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    detail_values = (
        "2025, 'Roads', 'Completed', '100.0', 'Builder', "
        "'[{\"contractor_key\":\"pcab:1\"}]', '', '', 'Cebu', 'Region VII', "
        f"'10.0', '123.0', 1, '{'a' * 64}'"
    )
    (chunks / "050-delivery-details-0001.sql").write_text(  # noqa: S608 - SQL fixture
        "INSERT INTO delivery_project_details VALUES ('25AA0001', "
        f"{detail_values});\nINSERT INTO delivery_project_details VALUES ('25AA0002', "
        f"{detail_values});\n"
    )
    signal_tail = (
        "2025, 'coordinate_location_conflict', 'source_conflict', 'Location question', "
        f"'Description', 'Builder', '1', 100, 'Completed', '100.0', 'Cebu', "
        f"'Region VII', '10.0', '123.0', 'Evidence', 'Limits', '{'a' * 64}'"
    )
    (chunks / "100-signals-0001.sql").write_text(  # noqa: S608 - SQL fixture
        "INSERT INTO integrity_signal_items VALUES "
        f"('25AA0001:location', '25AA0001', {signal_tail});\n"
    )

    contexts = load_delivery_contexts(
        chunks,
        detail_migration=detail_schema,
        signal_migration=signal_schema,
        contract_ids=frozenset({"25AA0001"}),
    )

    assert set(contexts) == {"25AA0001"}
    assert contexts["25AA0001"].region == "Region VII"
    assert contexts["25AA0001"].contractor_parties == ("pcab:1",)
    assert contexts["25AA0001"].evidence_questions == ("coordinate_location_conflict",)
