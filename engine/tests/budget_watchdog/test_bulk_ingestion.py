import json
from datetime import UTC, datetime

from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.bulk_ingestion import ingest_dpwh_projects, ingest_gaa_programs
from engine.budget_watchdog.storage import CanonicalStore

RETRIEVED_AT = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
EXPECTED_GAA_RECORDS_PER_POSITIVE_YEAR = 2


class FakeFetcher:
    def __init__(self, payloads: list[bytes]) -> None:
        self._payloads = iter(payloads)
        self.calls: list[tuple[str, str, dict[str, str | int]]] = []

    def fetch(
        self,
        source_id: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        retrieved_at: datetime | None = None,
    ) -> Acquisition:
        self.calls.append((source_id, path, params or {}))
        return Acquisition(
            source_id=source_id,
            source_url=f"https://example.test{path}",
            retrieved_at=retrieved_at or RETRIEVED_AT,
            media_type="application/json",
            payload=next(self._payloads),
        )


def _gaa_page(name: str, cursor: str | None, amount: int) -> bytes:
    return json.dumps(
        {
            "meta": {"dataset": "gaa", "currency": "PHP", "scale": "pesos"},
            "next_cursor": cursor,
            "data": [
                {
                    "fam_key": f"18-001|{name.casefold()}",
                    "name": name,
                    "years": {
                        "2024": {"count": 1, "amount": amount},
                        "2025": {"count": 1, "amount": 0},
                        "2026": {"count": 1, "amount": amount * 2},
                    },
                }
            ],
        }
    ).encode()


def _dpwh_page(has_next: bool) -> bytes:
    return json.dumps(
        {
            "status": 200,
            "data": {
                "data": [
                    {
                        "contractId": "24XX0001",
                        "description": "CONSTRUCTION OF SAMPLE BUILDING, SAMPLE CITY",
                        "budget": 9900000,
                        "infraYear": "2024",
                        "sourceOfFunds": "Regular Infra - GAA 2024",
                        "location": {"province": "Sample DEO", "region": "Region X"},
                    },
                    {
                        "contractId": "22XX0001",
                        "description": "OLDER SAMPLE BUILDING",
                        "budget": 1000000,
                        "infraYear": "2022",
                        "sourceOfFunds": "GAA 2022",
                        "location": {"province": "Sample DEO", "region": "Region X"},
                    },
                ],
                "pagination": {
                    "page": 1,
                    "limit": 1000,
                    "totalCount": 2,
                    "totalPages": 1,
                    "hasNext": has_next,
                    "hasPrev": False,
                },
            },
        }
    ).encode()


def test_gaa_ingestion_resumes_from_cursor_and_skips_zero_placeholders(tmp_path) -> None:
    database = tmp_path / "watchdog.sqlite3"
    archive = ArtifactArchive(tmp_path / "archive")
    first_fetcher = FakeFetcher([_gaa_page("Project One", "cursor-2", 5_000_000)])

    with CanonicalStore(database) as store:
        first = ingest_gaa_programs(
            fetcher=first_fetcher,
            archive=archive,
            store=store,
            department_id="18",
            fiscal_years=(2024, 2025, 2026),
            max_pages=1,
        )

    assert first.completed is False
    assert first.records_inserted == EXPECTED_GAA_RECORDS_PER_POSITIVE_YEAR

    second_fetcher = FakeFetcher([_gaa_page("Project Two", None, 7_000_000)])
    with CanonicalStore(database) as store:
        second = ingest_gaa_programs(
            fetcher=second_fetcher,
            archive=archive,
            store=store,
            department_id="18",
            fiscal_years=(2024, 2025, 2026),
        )
        assert (
            len(store.list_budget_projects(fiscal_year=2024))
            == EXPECTED_GAA_RECORDS_PER_POSITIVE_YEAR
        )
        assert store.list_budget_projects(fiscal_year=2025) == ()
        assert (
            len(store.list_budget_projects(fiscal_year=2026))
            == EXPECTED_GAA_RECORDS_PER_POSITIVE_YEAR
        )

    assert second.completed is True
    assert second_fetcher.calls[0][2]["cursor"] == "cursor-2"


def test_dpwh_ingestion_filters_requested_years_and_completes(tmp_path) -> None:
    fetcher = FakeFetcher([_dpwh_page(False)])
    with CanonicalStore(tmp_path / "watchdog.sqlite3") as store:
        result = ingest_dpwh_projects(
            fetcher=fetcher,
            archive=ArtifactArchive(tmp_path / "archive"),
            store=store,
            fiscal_years=(2024, 2025, 2026),
        )
        projects = store.list_delivery_projects(fiscal_year=2024)

    assert result.completed is True
    assert result.records_inserted == 1
    assert [project.contract_id for project in projects] == ["24XX0001"]
    assert fetcher.calls[0][2] == {"page": 1, "limit": 1000}
