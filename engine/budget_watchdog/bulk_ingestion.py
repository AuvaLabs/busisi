"""Resumable bulk ingestion for GAA program families and DPWH projects."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from engine.budget_watchdog.adapters.bettergov import (
    parse_dpwh_page_info,
    parse_dpwh_search,
    parse_gaa_search,
    parse_next_cursor,
)
from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.models import validate_fiscal_year
from engine.budget_watchdog.storage import CanonicalStore

GAA_PAGE_SIZE = 500
DPWH_PAGE_SIZE = 1000


class BulkIngestionError(RuntimeError):
    """Raised when pagination cannot produce a complete, reproducible stream."""


class AcquisitionFetcher(Protocol):
    def fetch(
        self,
        source_id: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        retrieved_at: datetime | None = None,
    ) -> Acquisition: ...


@dataclass(frozen=True, slots=True)
class BulkIngestionResult:
    pages_fetched: int
    records_inserted: int
    completed: bool
    next_position: str
    source_total: int | None = None


def _validate_inputs(fiscal_years: tuple[int, ...], max_pages: int | None) -> None:
    if not fiscal_years:
        raise ValueError("fiscal_years must not be empty")
    if len(set(fiscal_years)) != len(fiscal_years):
        raise ValueError("fiscal_years must be unique")
    for fiscal_year in fiscal_years:
        validate_fiscal_year(fiscal_year)
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be positive")


def ingest_gaa_programs(
    *,
    fetcher: AcquisitionFetcher,
    archive: ArtifactArchive,
    store: CanonicalStore,
    department_id: str,
    fiscal_years: tuple[int, ...],
    max_pages: int | None = None,
) -> BulkIngestionResult:
    _validate_inputs(fiscal_years, max_pages)
    if not department_id.isdigit():
        raise ValueError("department_id must be numeric")
    stream_id = f"gaa-programs:{department_id}:{','.join(map(str, fiscal_years))}"
    checkpoint = store.get_checkpoint(source_id="bettergov-budget", stream_id=stream_id)
    if checkpoint is not None and checkpoint.completed:
        return BulkIngestionResult(0, 0, True, checkpoint.position)

    cursor = checkpoint.position if checkpoint is not None else ""
    pages_fetched = 0
    records_inserted = 0
    seen_cursors = {cursor}
    while max_pages is None or pages_fetched < max_pages:
        params: dict[str, str | int] = {
            "year": max(fiscal_years),
            "limit": GAA_PAGE_SIZE,
        }
        if cursor:
            params["cursor"] = cursor
        acquisition = fetcher.fetch(
            "bettergov-budget",
            f"/api/v1/gaa/departments/{department_id}/programs",
            params=params,
        )
        artifact = archive.store(acquisition)
        for fiscal_year in fiscal_years:
            projects = tuple(
                project
                for project in parse_gaa_search(
                    acquisition.payload,
                    fiscal_year=fiscal_year,
                )
                if project.amount_centavos > 0
            )
            records_inserted += store.store_budget_projects(projects, artifact.sha256)

        pages_fetched += 1
        next_cursor = parse_next_cursor(acquisition.payload)
        completed = next_cursor is None
        next_position = next_cursor or ""
        store.save_checkpoint(
            source_id="bettergov-budget",
            stream_id=stream_id,
            position=next_position,
            completed=completed,
            updated_at=acquisition.retrieved_at,
        )
        if completed:
            return BulkIngestionResult(
                pages_fetched,
                records_inserted,
                True,
                next_position,
            )
        if next_position in seen_cursors:
            raise BulkIngestionError("GAA pagination cursor repeated")
        seen_cursors.add(next_position)
        cursor = next_position

    return BulkIngestionResult(pages_fetched, records_inserted, False, cursor)


def ingest_dpwh_projects(
    *,
    fetcher: AcquisitionFetcher,
    archive: ArtifactArchive,
    store: CanonicalStore,
    fiscal_years: tuple[int, ...],
    max_pages: int | None = None,
) -> BulkIngestionResult:
    _validate_inputs(fiscal_years, max_pages)
    stream_id = f"dpwh-projects:{','.join(map(str, fiscal_years))}"
    checkpoint = store.get_checkpoint(source_id="bettergov-dpwh", stream_id=stream_id)
    if checkpoint is not None and checkpoint.completed:
        return BulkIngestionResult(0, 0, True, checkpoint.position)

    page = int(checkpoint.position) if checkpoint is not None else 1
    pages_fetched = 0
    records_inserted = 0
    source_total: int | None = None
    while max_pages is None or pages_fetched < max_pages:
        acquisition = fetcher.fetch(
            "bettergov-dpwh",
            "/projects",
            params={"page": page, "limit": DPWH_PAGE_SIZE},
        )
        page_info = parse_dpwh_page_info(acquisition.payload)
        if page_info.page != page:
            raise BulkIngestionError("DPWH response page does not match the request")
        source_total = page_info.total_count
        artifact = archive.store(acquisition)
        projects = tuple(
            project
            for project in parse_dpwh_search(acquisition.payload)
            if project.fiscal_year in fiscal_years
        )
        records_inserted += store.store_delivery_projects(projects, artifact.sha256)
        pages_fetched += 1

        completed = not page_info.has_next
        next_page = page if completed else page + 1
        next_position = str(next_page)
        store.save_checkpoint(
            source_id="bettergov-dpwh",
            stream_id=stream_id,
            position=next_position,
            completed=completed,
            updated_at=acquisition.retrieved_at,
        )
        if completed:
            return BulkIngestionResult(
                pages_fetched,
                records_inserted,
                True,
                next_position,
                source_total,
            )
        page = next_page

    return BulkIngestionResult(
        pages_fetched,
        records_inserted,
        False,
        str(page),
        source_total,
    )
