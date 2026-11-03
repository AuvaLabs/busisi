import csv
import io
from pathlib import Path

import pytest

from engine.budget_watchdog.publication_store import (
    RegisterQuery,
    RegisterQueryError,
    build_publication_store,
    export_register_csv,
    get_project_dossier,
    query_register,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
REVIEWED_RECORDS = 6
CATMON_RECORDS = 5
FY2024_RECORDS = 2
EVIDENCE_URLS = 2


@pytest.fixture
def publication_database(tmp_path) -> Path:
    database = tmp_path / "publication.sqlite3"
    build_publication_store(GOLDEN_PATH, database)
    return database


def test_store_queries_reviewed_records_with_stable_cursor(publication_database) -> None:
    first = query_register(
        publication_database,
        RegisterQuery(limit=2, sort="appropriation_desc"),
    )
    second = query_register(
        publication_database,
        RegisterQuery(limit=2, sort="appropriation_desc", cursor=first.next_cursor),
    )

    assert first.total == REVIEWED_RECORDS
    assert [record.slug for record in first.records] == [
        "corazon-2026-completion",
        "agoncillo-2023",
    ]
    assert first.next_cursor is not None
    assert not (
        {record.slug for record in first.records} & {record.slug for record in second.records}
    )


def test_store_searches_and_filters_without_exposing_unreviewed_data(
    publication_database,
) -> None:
    catmon = query_register(publication_database, RegisterQuery(q="Catmon", limit=20))
    year = query_register(publication_database, RegisterQuery(year=2024, limit=20))
    quarantine = query_register(
        publication_database,
        RegisterQuery(status="quarantine", limit=20),
    )

    assert catmon.total == CATMON_RECORDS
    assert year.total == FY2024_RECORDS
    assert {record.fiscal_year for record in year.records} == {2024}
    assert quarantine.total == 1
    assert quarantine.records[0].slug == "corazon-2026-completion"
    assert quarantine.records[0].is_confirmed_link is False


def test_store_rejects_cursor_from_different_sort(publication_database) -> None:
    first = query_register(publication_database, RegisterQuery(limit=1))

    with pytest.raises(RegisterQueryError, match="cursor"):
        query_register(
            publication_database,
            RegisterQuery(limit=1, sort="title_asc", cursor=first.next_cursor),
        )


def test_every_sort_is_stable_across_cursor_pages(publication_database) -> None:
    sorts = ("appropriation_desc", "difference_desc", "year_desc", "title_asc")
    for sort in sorts:
        expected = query_register(
            publication_database,
            RegisterQuery(limit=100, sort=sort),
        )
        cursor = None
        actual = []
        while True:
            page = query_register(
                publication_database,
                RegisterQuery(limit=1, sort=sort, cursor=cursor),
            )
            actual.extend(record.slug for record in page.records)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert actual == [record.slug for record in expected.records]


def test_store_rejects_malformed_cursor(publication_database) -> None:
    for cursor in ("not-a-valid-cursor", "a"):
        with pytest.raises(RegisterQueryError, match="cursor"):
            query_register(
                publication_database,
                RegisterQuery(limit=1, cursor=cursor),
            )


def test_store_returns_full_dossier_and_missing_is_none(publication_database) -> None:
    dossier = get_project_dossier(publication_database, "corazon-2024-phase-1")

    assert dossier is not None
    assert dossier.contract_id == "24HI0148"
    assert len(dossier.evidence_urls) == EVIDENCE_URLS
    assert get_project_dossier(publication_database, "missing") is None


def test_server_csv_export_respects_filters(publication_database) -> None:
    document = export_register_csv(
        publication_database,
        RegisterQuery(year=2024, sort="title_asc", limit=100),
    )
    rows = list(csv.DictReader(io.StringIO(document)))

    assert len(rows) == FY2024_RECORDS
    assert {row["fiscal_year"] for row in rows} == {"2024"}
    assert rows[0]["project"].startswith("Construction of Multi-Purpose Building")
