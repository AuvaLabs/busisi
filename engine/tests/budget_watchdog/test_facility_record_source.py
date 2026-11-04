import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.facility_record_source import load_public_school_records
from engine.budget_watchdog.storage import SCHEMA


def _canonical_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            """
            INSERT INTO delivery_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "school-1", 2025, "Construction of Sample Elementary School", 100,
                    "Sample City", "GAA", "[]", "family:school", "school", "a" * 64,
                ),
                (
                    "road-1", 2025, "Construction of Sample Road", 200,
                    "Sample City", "GAA", "[]", "family:road", "road", "b" * 64,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _hgab_bundle(path: Path) -> None:
    chunks = path / "chunks"
    chunks.mkdir(parents=True)
    (chunks / "0001.sql").write_text(
        """
        INSERT INTO stage_change_items (
          record_id, fiscal_year, dataset, title, program, pap, region, office,
          change_type, change_label, review_status, held, confidence,
          nep_centavos, house_centavos, difference_centavos, source_url,
          nep_pdf_url, house_pdf_url, nep_page, house_page, source_commit,
          artifact_sha256, family_label
        ) VALUES
          ('budget-school', 2027, 'dpwh', 'Repair of Sample High School', '', '',
           'NCR', 'Sample DEO', 'unchanged', '', 'candidate', 0, 1, 100, 100, 0,
           'https://example.test/source', 'https://example.test/nep',
           'https://example.test/house', 1, 1, 'commit',
           'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', ''),
          ('budget-road', 2027, 'dpwh', 'Repair of Sample Road', '', '',
           'NCR', 'Sample DEO', 'unchanged', '', 'candidate', 0, 1, 100, 100, 0,
           'https://example.test/source', 'https://example.test/nep',
           'https://example.test/house', 1, 1, 'commit',
           'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', '');
        """,
        encoding="utf-8",
    )


def test_loads_only_school_records_and_keeps_sources_separate(tmp_path: Path) -> None:
    canonical = tmp_path / "watchdog.sqlite3"
    bundle = tmp_path / "hgab"
    _canonical_database(canonical)
    _hgab_bundle(bundle)

    records = load_public_school_records(canonical, bundle)

    assert [(record.source_type, record.record_id) for record in records] == [
        ("budget", "budget-school"),
        ("delivery", "school-1"),
    ]


def test_rejects_missing_canonical_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must exist"):
        load_public_school_records(tmp_path / "missing.sqlite3", tmp_path / "missing-bundle")
