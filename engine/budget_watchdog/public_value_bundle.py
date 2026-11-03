"""Build a verified D1 bundle for the FY2027 public-value desk."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.public_value import (
    BASELINE_YEAR,
    FISCAL_YEAR,
    PublicValueIndicator,
    parse_public_value_documents,
    summarize_public_value,
)

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "cloudflare/busisi/migrations/0009_public_value.sql"
MINIMUM_METADATA_ROWS = 8


@dataclass(frozen=True, slots=True)
class PublicValueBundleResult:
    output_dir: Path
    indicator_count: int
    improving_count: int
    pressure_count: int
    sql_chunks: int
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_values(values: Sequence[str | int | None]) -> str:
    return ", ".join(
        "NULL" if value is None else str(value) if isinstance(value, int) else _sql_text(value)
        for value in values
    )


def _batched(rows: Iterable[str], size: int) -> Iterator[tuple[str, ...]]:
    batch: list[str] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _load_snapshot(snapshot_dir: Path) -> tuple[tuple[PublicValueIndicator, ...], dict[str, dict[str, Any]], dict[str, Any]]:
    manifest_path = snapshot_dir / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("fiscal_year") != FISCAL_YEAR or manifest.get("baseline_year") != BASELINE_YEAR:
        raise ValueError("public-value snapshot fiscal boundary is invalid")
    entries = manifest.get("documents")
    if not isinstance(entries, list):
        raise ValueError("public-value snapshot document manifest is missing")
    documents: dict[str, dict[str, Any]] = {}
    text: dict[str, str] = {}
    for entry in entries:
        path = snapshot_dir / str(entry.get("path", ""))
        if not path.is_file():
            raise ValueError("public-value snapshot document is missing")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"public-value snapshot digest mismatch: {path.name}")
        key = str(entry.get("key", ""))
        if key in documents:
            raise ValueError(f"duplicate public-value document key: {key}")
        documents[key] = entry
        text[key] = path.read_text(encoding="utf-8")
    records = parse_public_value_documents(text)
    return records, documents, manifest


def _record_statement(record: PublicValueIndicator, documents: dict[str, dict[str, Any]]) -> str:
    document = documents[record.source_document]
    values = (
        record.indicator_id,
        record.category,
        record.label,
        record.unit,
        record.value_2026,
        record.value_2027,
        record.lower_2026,
        record.upper_2026,
        record.lower_2027,
        record.upper_2027,
        record.change,
        record.direction,
        record.rule,
        record.source_document,
        record.source_page,
        str(document["source_url"]),
        str(document["pdf_sha256"]),
        record.note,
    )
    return f"INSERT INTO public_value_indicators VALUES ({_sql_values(values)});"  # noqa: S608


def _verify(chunks: Sequence[Path], expected: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        actual = connection.execute("SELECT COUNT(*) FROM public_value_indicators").fetchone()[0]
        metadata = connection.execute("SELECT COUNT(*) FROM public_value_metadata").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if actual != expected or metadata < MINIMUM_METADATA_ROWS or integrity != "ok":
        raise ValueError("public-value D1 bundle verification failed")


def build_public_value_bundle(snapshot_dir: Path, output_dir: Path, *, chunk_rows: int = 100) -> PublicValueBundleResult:
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    records, documents, _ = _load_snapshot(snapshot_dir)
    summary = dict(summarize_public_value(records))
    metadata = {
        **{key: str(value) for key, value in summary.items()},
        "fiscal_year": str(FISCAL_YEAR),
        "baseline_year": str(BASELINE_YEAR),
        "source_scope": "FY2027 BESF Tables A.1 and A.2",
        "evidence_boundary": "DBM projections and fiscal program; not enacted appropriations, releases, payments, or outcomes",
    }
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata_path = chunks_dir / "000-metadata.sql"
    metadata_lines = ["DELETE FROM public_value_indicators;", "DELETE FROM public_value_metadata;"]
    metadata_lines.extend(
        f"INSERT INTO public_value_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    metadata_path.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")
    paths = [metadata_path]
    for index, batch in enumerate(
        _batched((_record_statement(record, documents) for record in records), chunk_rows), start=1
    ):
        path = chunks_dir / f"100-public-value-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    _verify(paths, len(records))
    manifest = {
        **metadata,
        "source_manifest_sha256": hashlib.sha256(
            (snapshot_dir / "snapshot-manifest.json").read_bytes()
        ).hexdigest(),
        "chunk_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return PublicValueBundleResult(
        output_dir,
        len(records),
        int(summary["improving_count"]),
        int(summary["pressure_count"]),
        len(paths),
        manifest_sha256,
    )
