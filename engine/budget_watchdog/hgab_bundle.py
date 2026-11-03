"""Build a reconciled D1 bundle for the FY2027 NEP-to-House change ledger."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.budget_watchdog.stage_changes import (
    StageChange,
    parse_hgab_page,
    reconcile_hgab_dataset,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "cloudflare"
    / "busisi"
    / "migrations"
    / "0003_stage_changes.sql"
)


@dataclass(frozen=True, slots=True)
class HgabBundleResult:
    output_dir: Path
    record_count: int
    quarantine_count: int
    sql_chunks: int
    source_commit: str
    manifest_sha256: str


def _sql_text(value: str) -> str:
    return f"'{value.replace("'", "''")}'"


def _sql_values(values: Sequence[str | int | float | None]) -> str:
    encoded = []
    for value in values:
        if value is None:
            encoded.append("NULL")
        elif isinstance(value, str):
            encoded.append(_sql_text(value))
        else:
            encoded.append(str(value))
    return ", ".join(encoded)


def _batched(rows: Iterable[str], size: int) -> Iterator[tuple[str, ...]]:
    batch: list[str] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _write_chunks(directory: Path, statements: Iterable[str], size: int) -> list[Path]:
    paths = []
    for index, batch in enumerate(_batched(statements, size), start=1):
        path = directory / f"100-stage-changes-{index:04d}.sql"
        path.write_text("\n".join(batch) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _statement(record: StageChange) -> str:
    values = (
        record.record_id,
        record.fiscal_year,
        record.dataset,
        record.title,
        record.program,
        record.pap,
        record.region,
        record.office,
        record.change_type,
        record.change_label,
        record.review_status,
        int(record.held),
        record.confidence,
        record.nep_centavos,
        record.house_centavos,
        record.difference_centavos,
        record.source_url,
        record.nep_pdf_url,
        record.house_pdf_url,
        record.nep_page,
        record.house_page,
        record.source_commit,
        record.artifact_sha256,
    )
    return f"INSERT OR REPLACE INTO stage_change_items VALUES ({_sql_values(values)});"  # noqa: S608


def _overview_controls(overview: dict[str, Any]) -> dict[str, dict[str, int | str]]:
    datasets = overview.get("data", {}).get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("overview datasets are missing")
    controls = {}
    for dataset in datasets:
        key = dataset["key"]
        groups = dataset["bridge"]["groups"]
        stage = dataset["house_stage"]
        controls[key] = {
            "count": sum(int(group["rows"]) for group in groups.values()),
            "nep": int(dataset["totals"]["nep_php"]) * 100,
            "house": int(dataset["totals"][f"{stage}_php"]) * 100,
            "quarantine": int(dataset["unconfirmed_rows"]) + int(groups["scope_review"]["rows"]),
            "house_stage": stage,
        }
    return controls


def _load_records(snapshot_dir: Path) -> tuple[tuple[StageChange, ...], str, dict[str, Any]]:
    manifest = json.loads((snapshot_dir / "snapshot-manifest.json").read_text(encoding="utf-8"))
    overview = json.loads((snapshot_dir / "overview.json").read_text(encoding="utf-8"))
    records: list[StageChange] = []
    commits = set()
    for page in manifest["pages"]:
        payload = (snapshot_dir / page["path"]).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != page["sha256"]:
            raise ValueError(f"snapshot page digest mismatch: {page['path']}")
        parsed = parse_hgab_page(payload, artifact_sha256=digest)
        records.extend(parsed.records)
        commits.add(parsed.source_commit)
    if len(commits) != 1:
        raise ValueError("snapshot pages do not share one source commit")
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("snapshot contains duplicate stage-change identifiers")
    return tuple(records), commits.pop(), overview


def _verify_bundle(chunks: Sequence[Path], expected_count: int) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for chunk in chunks:
            connection.executescript(chunk.read_text(encoding="utf-8"))
        count = connection.execute("SELECT COUNT(*) FROM stage_change_items").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if count != expected_count or integrity != "ok":
        raise ValueError("stage-change D1 bundle verification failed")


def build_hgab_bundle(
    snapshot_dir: Path,
    output_dir: Path,
    *,
    chunk_rows: int = 1_000,
) -> HgabBundleResult:
    """Validate a complete snapshot, reconcile controls and emit verified D1 SQL chunks."""

    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    records, source_commit, overview = _load_records(snapshot_dir)
    controls = _overview_controls(overview)
    for dataset, expected in controls.items():
        selected = tuple(record for record in records if record.dataset == dataset)
        reconcile_hgab_dataset(
            selected,
            expected_count=int(expected["count"]),
            expected_nep_centavos=int(expected["nep"]),
            expected_house_centavos=int(expected["house"]),
            expected_quarantine_count=int(expected["quarantine"]),
        )

    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    chunks_dir = building / "chunks"
    chunks_dir.mkdir(parents=True)
    metadata = {
        "fiscal_year": "2027",
        "record_count": str(len(records)),
        "quarantine_count": str(sum(record.review_status == "quarantine" for record in records)),
        "source_commit": source_commit,
        "overview_sha256": hashlib.sha256(
            (snapshot_dir / "overview.json").read_bytes()
        ).hexdigest(),
    }
    metadata_path = chunks_dir / "000-metadata.sql"
    lines = ["DELETE FROM stage_change_items;", "DELETE FROM stage_change_metadata;"]
    lines.extend(
        f"INSERT INTO stage_change_metadata VALUES ({_sql_text(key)}, {_sql_text(value)});"  # noqa: S608
        for key, value in sorted(metadata.items())
    )
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    chunks = [metadata_path, *_write_chunks(chunks_dir, map(_statement, records), chunk_rows)]
    _verify_bundle(chunks, len(records))
    manifest = {
        **metadata,
        "controls": controls,
        "documents": overview["data"]["documents"],
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
    return HgabBundleResult(
        output_dir=output_dir,
        record_count=len(records),
        quarantine_count=int(metadata["quarantine_count"]),
        sql_chunks=len(chunks),
        source_commit=source_commit,
        manifest_sha256=manifest_sha256,
    )
