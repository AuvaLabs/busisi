"""Build verified D1 seed chunks for the public source-record explorer."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0002_public_explorer.sql"
)


@dataclass(frozen=True, slots=True)
class PublicDataBundleResult:
    output_dir: Path
    budget_records: int
    delivery_records: int
    candidate_links: int
    sql_chunks: int
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_values(values: Sequence[str | int]) -> str:
    return ", ".join(str(value) if isinstance(value, int) else _sql_text(value) for value in values)


def _stable_id(*values: object) -> str:
    document = "\x1f".join(str(value) for value in values).encode()
    return hashlib.sha256(document).hexdigest()


def _batched(rows: Iterable[str], size: int) -> Iterator[tuple[str, ...]]:
    batch: list[str] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _write_chunks(
    directory: Path,
    prefix: str,
    statements: Iterable[str],
    chunk_rows: int,
) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(statements, chunk_rows), start=1):
        path = directory / f"{prefix}-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _budget_statements(connection: sqlite3.Connection) -> Iterator[str]:
    rows = connection.execute("SELECT * FROM budget_projects ORDER BY fiscal_year, budget_line_id")
    for row in rows:
        values = (
            _stable_id(row["fiscal_year"], row["budget_line_id"], row["artifact_sha256"]),
            row["budget_line_id"],
            row["fiscal_year"],
            row["description"],
            row["amount_centavos"],
            row["project_family_id"],
            row["family_canonical_text"],
            row["artifact_sha256"],
        )
        yield f"INSERT INTO budget_items VALUES ({_sql_values(values)});"  # noqa: S608


def _delivery_statements(connection: sqlite3.Connection) -> Iterator[str]:
    rows = connection.execute("SELECT * FROM delivery_projects ORDER BY fiscal_year, contract_id")
    for row in rows:
        values = (
            row["contract_id"],
            row["fiscal_year"],
            row["description"],
            row["budget_centavos"],
            row["location"],
            row["source_of_funds"],
            row["project_family_id"],
            row["family_canonical_text"],
            row["artifact_sha256"],
        )
        yield f"INSERT INTO delivery_items VALUES ({_sql_values(values)});"  # noqa: S608


def _candidate_statement(record: dict[str, Any]) -> str:
    candidate_id = _stable_id(
        record["fiscal_year"], record["budget_line_id"], record["contract_id"]
    )
    values = (
        candidate_id,
        record["fiscal_year"],
        record["budget_line_id"],
        record["contract_id"],
        record["confidence"],
        record["score"],
        json.dumps(record["signals"], ensure_ascii=False, separators=(",", ":")),
        record["budget_description"],
        record["delivery_description"],
        record["budget_amount_centavos"],
        record["delivery_budget_centavos"],
        record["budget_amount_centavos"] - record["delivery_budget_centavos"],
        record["budget_evidence_url"],
        record["delivery_evidence_url"],
        "candidate",
    )
    return f"INSERT INTO candidate_links VALUES ({_sql_values(values)});"  # noqa: S608


def _read_candidates(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(records, list) or payload.get("count") != len(records):
        raise ValueError("candidate file count does not match its records")
    return tuple(records)


def _artifact_digest(connection: sqlite3.Connection, table: str) -> str:
    rows = connection.execute(
        f"SELECT DISTINCT artifact_sha256 FROM {table} ORDER BY 1"  # noqa: S608
    ).fetchall()
    values = [row[0] for row in rows]
    if len(values) != 1:
        raise ValueError(f"{table} must contain exactly one source artifact")
    value = values[0]
    if not isinstance(value, str):
        raise ValueError(f"{table} source artifact must be text")
    return value


def _metadata_sql(metadata: dict[str, str]) -> str:
    lines = [
        "DELETE FROM candidate_links;",
        "DELETE FROM delivery_items;",
        "DELETE FROM budget_items;",
        "DELETE FROM public_metadata;",
    ]
    for key, value in sorted(metadata.items()):
        lines.append(
            f"INSERT INTO public_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        )
    return "\n".join(lines) + "\n"


def _verify_bundle(chunks: Sequence[Path], expected: tuple[int, int, int]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("budget_items", "delivery_items", "candidate_links")
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or integrity != "ok":
        raise ValueError("public data bundle verification failed")


def build_public_data_bundle(
    canonical_database: Path,
    candidate_path: Path,
    output_dir: Path,
    *,
    chunk_rows: int = 2_000,
) -> PublicDataBundleResult:
    """Build deterministic, verified SQL chunks from the archived canonical snapshot."""

    if not canonical_database.is_file() or not candidate_path.is_file():
        raise ValueError("canonical database and candidate file must exist")
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    connection = sqlite3.connect(f"{canonical_database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("budget_projects", "delivery_projects")
        )
        candidates = _read_candidates(candidate_path)
        metadata = {
            "budget_artifact_sha256": _artifact_digest(connection, "budget_projects"),
            "budget_records": str(counts[0]),
            "candidate_links": str(len(candidates)),
            "delivery_artifact_sha256": _artifact_digest(connection, "delivery_projects"),
            "delivery_records": str(counts[1]),
            "schema_version": "2",
        }
        metadata_path = chunks_dir / "000-metadata.sql"
        metadata_path.write_text(_metadata_sql(metadata), encoding="utf-8")
        chunks = [metadata_path]
        chunks += _write_chunks(
            chunks_dir, "100-budget", _budget_statements(connection), chunk_rows
        )
        chunks += _write_chunks(
            chunks_dir, "200-delivery", _delivery_statements(connection), chunk_rows
        )
        chunks += _write_chunks(
            chunks_dir,
            "300-candidates",
            (_candidate_statement(record) for record in candidates),
            chunk_rows,
        )
    finally:
        connection.close()
    expected = (counts[0], counts[1], len(candidates))
    _verify_bundle(chunks, expected)
    manifest = {
        **metadata,
        "chunk_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in chunks
        },
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return PublicDataBundleResult(
        output_dir,
        counts[0],
        counts[1],
        len(candidates),
        len(chunks),
        manifest_sha256,
    )
