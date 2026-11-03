"""Immutable reviewed publication store with indexed, cursor-based queries."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path

from engine.budget_watchdog.publication import ProjectDossierView, build_publication

SCHEMA_VERSION = 1
MAX_QUERY_LIMIT = 100
MAX_EXPORT_ROWS = 10_000
MAX_QUERY_TEXT = 200
MIN_FISCAL_YEAR = 2000
MAX_FISCAL_YEAR = 2100
SEARCH_TOKEN = re.compile(r"[\w-]+", re.UNICODE)
ALLOWED_STATUSES = frozenset({"all", "reviewed", "quarantine"})
SORT_FIELDS = {
    "appropriation_desc": ("p.appropriation_centavos", "DESC", "integer"),
    "difference_desc": ("p.variance_centavos", "DESC", "integer"),
    "year_desc": ("p.fiscal_year", "DESC", "integer"),
    "title_asc": ("LOWER(p.title)", "ASC", "text"),
}

SCHEMA = """
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE projects (
    slug TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    location TEXT NOT NULL,
    appropriation_centavos INTEGER NOT NULL,
    contract_budget_centavos INTEGER NOT NULL,
    variance_centavos INTEGER NOT NULL,
    contract_id TEXT NOT NULL,
    delivery_title TEXT NOT NULL,
    implementing_office TEXT NOT NULL,
    source_of_funds TEXT NOT NULL,
    confidence TEXT NOT NULL,
    confidence_score INTEGER NOT NULL,
    match_signals_json TEXT NOT NULL,
    match_limitations TEXT NOT NULL,
    evidence_urls_json TEXT NOT NULL,
    family_id TEXT NOT NULL,
    family_label TEXT NOT NULL,
    status_label TEXT NOT NULL,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('reviewed', 'quarantine')),
    is_confirmed_link INTEGER NOT NULL CHECK (is_confirmed_link IN (0, 1))
);
CREATE INDEX projects_year ON projects (fiscal_year);
CREATE INDEX projects_status ON projects (publication_status);
CREATE INDEX projects_appropriation ON projects (appropriation_centavos DESC, slug);
CREATE INDEX projects_variance ON projects (variance_centavos DESC, slug);
CREATE VIRTUAL TABLE project_search USING fts5(
    slug UNINDEXED,
    title,
    location,
    contract_id,
    delivery_title,
    implementing_office,
    tokenize='unicode61 remove_diacritics 2'
);
PRAGMA user_version = 1;
"""


class RegisterQueryError(ValueError):
    """Raised when filters or cursor state violate the public query contract."""


@dataclass(frozen=True, slots=True)
class RegisterQuery:
    q: str = ""
    year: int | None = None
    status: str = "all"
    sort: str = "appropriation_desc"
    limit: int = 25
    cursor: str | None = None

    def __post_init__(self) -> None:
        if len(self.q) > MAX_QUERY_TEXT:
            raise RegisterQueryError(f"q must not exceed {MAX_QUERY_TEXT} characters")
        if self.year is not None and not MIN_FISCAL_YEAR <= self.year <= MAX_FISCAL_YEAR:
            raise RegisterQueryError("year is outside the supported range")
        if self.status not in ALLOWED_STATUSES:
            raise RegisterQueryError("status is invalid")
        if self.sort not in SORT_FIELDS:
            raise RegisterQueryError("sort is invalid")
        if not 1 <= self.limit <= MAX_QUERY_LIMIT:
            raise RegisterQueryError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")


@dataclass(frozen=True, slots=True)
class RegisterPage:
    records: tuple[ProjectDossierView, ...]
    total: int
    next_cursor: str | None


def _project_values(record: ProjectDossierView) -> tuple[object, ...]:
    return (
        record.slug,
        record.case_id,
        record.title,
        record.fiscal_year,
        record.location,
        record.appropriation_centavos,
        record.contract_budget_centavos,
        record.variance_centavos,
        record.contract_id,
        record.delivery_title,
        record.implementing_office,
        record.source_of_funds,
        record.confidence,
        record.confidence_score,
        json.dumps(record.match_signals),
        record.match_limitations,
        json.dumps(record.evidence_urls),
        record.family_id,
        record.family_label,
        record.status_label,
        "reviewed" if record.is_confirmed_link else "quarantine",
        int(record.is_confirmed_link),
    )


def _insert_projects(
    connection: sqlite3.Connection, records: tuple[ProjectDossierView, ...]
) -> None:
    connection.executemany(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        map(_project_values, records),
    )
    connection.executemany(
        "INSERT INTO project_search VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                record.slug,
                record.title,
                record.location,
                record.contract_id,
                record.delivery_title,
                record.implementing_office,
            )
            for record in records
        ),
    )


def build_publication_store(golden_path: Path, database_path: Path) -> Path:
    publication = build_publication(golden_path)
    source_digest = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    building = database_path.with_name(f".{database_path.name}.building")
    building.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(building)) as connection, connection:
            connection.executescript(SCHEMA)
            connection.executemany(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                (
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("golden_sha256", source_digest),
                    ("reviewed_cases", str(publication.release_gate.reviewed_cases)),
                    ("release_ready", json.dumps(publication.release_gate.release_ready)),
                ),
            )
            _insert_projects(connection, publication.dossiers)
        building.replace(database_path)
    except Exception:
        building.unlink(missing_ok=True)
        raise
    return database_path


def _connect_readonly(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise RegisterQueryError("publication database does not exist")
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _search_expression(value: str) -> str | None:
    tokens = SEARCH_TOKEN.findall(value.casefold())
    if not tokens:
        return None
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens)


def _filters(query: RegisterQuery) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    search = _search_expression(query.q)
    if search:
        clauses.append("p.slug IN (SELECT slug FROM project_search WHERE project_search MATCH ?)")
        parameters.append(search)
    if query.year is not None:
        clauses.append("p.fiscal_year = ?")
        parameters.append(query.year)
    if query.status != "all":
        clauses.append("p.publication_status = ?")
        parameters.append(query.status)
    return clauses, parameters


def _encode_cursor(sort: str, value: int | str, slug: str) -> str:
    payload = json.dumps(
        {"v": 1, "sort": sort, "value": value, "slug": slug}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(value: str, sort: str, kind: str) -> tuple[int | str, str]:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(f"{value}{padding}").decode())
        cursor_value = payload["value"]
        slug = payload["slug"]
        if payload.get("v") != 1 or payload.get("sort") != sort or not isinstance(slug, str):
            raise ValueError
        if kind == "integer" and (
            isinstance(cursor_value, bool) or not isinstance(cursor_value, int)
        ):
            raise ValueError
        if kind == "text" and not isinstance(cursor_value, str):
            raise ValueError
        return cursor_value, slug
    except (KeyError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise RegisterQueryError("cursor is invalid for this query") from exc


def _row_to_dossier(row: sqlite3.Row) -> ProjectDossierView:
    return ProjectDossierView(
        case_id=row["case_id"],
        slug=row["slug"],
        title=row["title"],
        fiscal_year=row["fiscal_year"],
        location=row["location"],
        appropriation_centavos=row["appropriation_centavos"],
        contract_budget_centavos=row["contract_budget_centavos"],
        variance_centavos=row["variance_centavos"],
        contract_id=row["contract_id"],
        delivery_title=row["delivery_title"],
        implementing_office=row["implementing_office"],
        source_of_funds=row["source_of_funds"],
        confidence=row["confidence"],
        confidence_score=row["confidence_score"],
        match_signals=tuple(json.loads(row["match_signals_json"])),
        match_limitations=row["match_limitations"],
        evidence_urls=tuple(json.loads(row["evidence_urls_json"])),
        family_id=row["family_id"],
        family_label=row["family_label"],
        status_label=row["status_label"],
        is_confirmed_link=bool(row["is_confirmed_link"]),
        is_quarantined=not bool(row["is_confirmed_link"]),
    )


def query_register(database_path: Path, query: RegisterQuery) -> RegisterPage:
    field, direction, kind = SORT_FIELDS[query.sort]
    clauses, parameters = _filters(query)
    connection = _connect_readonly(database_path)
    try:
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = connection.execute(
            f"SELECT COUNT(*) FROM projects p {where}",  # noqa: S608
            parameters,
        ).fetchone()[0]
        if query.cursor:
            value, slug = _decode_cursor(query.cursor, query.sort, kind)
            operator = "<" if direction == "DESC" else ">"
            clauses.append(f"({field} {operator} ? OR ({field} = ? AND p.slug > ?))")
            parameters.extend((value, value, slug))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"SELECT p.* FROM projects p {where} ORDER BY {field} {direction}, p.slug ASC LIMIT ?",  # noqa: S608
            (*parameters, query.limit + 1),
        ).fetchall()
    finally:
        connection.close()
    records = tuple(_row_to_dossier(row) for row in rows[: query.limit])
    next_cursor = None
    if len(rows) > query.limit and records:
        last = records[-1]
        cursor_value = (
            last.title.casefold() if kind == "text" else getattr(last, field.split(".")[-1])
        )
        next_cursor = _encode_cursor(query.sort, cursor_value, last.slug)
    return RegisterPage(records, int(total), next_cursor)


def get_project_dossier(database_path: Path, slug: str) -> ProjectDossierView | None:
    connection = _connect_readonly(database_path)
    try:
        row = connection.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
    finally:
        connection.close()
    return _row_to_dossier(row) if row else None


def export_register_csv(database_path: Path, query: RegisterQuery) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "fiscal_year",
            "project",
            "location",
            "contract_id",
            "status",
            "appropriation_centavos",
            "contract_budget_centavos",
            "dossier",
        )
    )
    exported = 0
    cursor = None
    while exported < MAX_EXPORT_ROWS:
        page = query_register(database_path, replace(query, limit=MAX_QUERY_LIMIT, cursor=cursor))
        for record in page.records:
            writer.writerow(
                (
                    record.fiscal_year,
                    record.title,
                    record.location,
                    record.contract_id,
                    "reviewed" if record.is_confirmed_link else "quarantine",
                    record.appropriation_centavos,
                    record.contract_budget_centavos,
                    f"/projects/{record.slug}/",
                )
            )
        exported += len(page.records)
        cursor = page.next_cursor
        if cursor is None:
            break
    if cursor is not None:
        raise RegisterQueryError(f"export exceeds {MAX_EXPORT_ROWS} records")
    return output.getvalue()
