"""Load the saved delivery details needed by the project-link review workspace."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from engine.budget_watchdog.review_expansion import DeliveryContext

DETAIL_ROW = re.compile(r"^INSERT INTO delivery_project_details VALUES \('([^']+)'", re.I)
SIGNAL_ROW = re.compile(r"^INSERT INTO integrity_signal_items VALUES \('[^']+', '([^']+)'", re.I)


def _load_matching_rows(
    connection: sqlite3.Connection,
    paths: list[Path],
    pattern: re.Pattern[str],
    contract_ids: frozenset[str],
) -> None:
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                match = pattern.match(line)
                if match and match.group(1) in contract_ids:
                    connection.execute(line)


def load_delivery_contexts(
    chunk_dir: Path,
    *,
    detail_migration: Path,
    signal_migration: Path,
    contract_ids: frozenset[str],
) -> dict[str, DeliveryContext]:
    if not contract_ids:
        return {}
    if not chunk_dir.is_dir():
        raise ValueError("delivery detail folder does not exist")
    for path in (detail_migration, signal_migration):
        if not path.is_file():
            raise ValueError("required review source schema does not exist")
    detail_paths = sorted(chunk_dir.glob("050-delivery-details-*.sql"))
    signal_paths = sorted(chunk_dir.glob("100-signals-*.sql"))
    if not detail_paths:
        raise ValueError("saved delivery details are missing")

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(detail_migration.read_text(encoding="utf-8"))
        connection.executescript(signal_migration.read_text(encoding="utf-8"))
        _load_matching_rows(connection, detail_paths, DETAIL_ROW, contract_ids)
        _load_matching_rows(connection, signal_paths, SIGNAL_ROW, contract_ids)
        signal_rows = connection.execute(
            "SELECT contract_id, code FROM integrity_signal_items ORDER BY contract_id, code"
        ).fetchall()
        questions: dict[str, list[str]] = {}
        for row in signal_rows:
            questions.setdefault(row["contract_id"], []).append(row["code"])
        rows = connection.execute(
            "SELECT * FROM delivery_project_details ORDER BY contract_id"
        ).fetchall()
    finally:
        connection.close()

    output = {}
    for row in rows:
        parties = json.loads(row["contractor_parties_json"])
        output[row["contract_id"]] = DeliveryContext(
            contract_id=row["contract_id"],
            category=row["category"],
            status=row["status"],
            progress=row["progress"],
            contractor_name=row["contractor_name"],
            contractor_parties=tuple(item["contractor_key"] for item in parties),
            province=row["province"],
            region=row["region"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            has_source_image=bool(row["has_satellite_image"]),
            evidence_questions=tuple(questions.get(row["contract_id"], ())),
            source_sha256=row["source_artifact_sha256"],
        )
    return output
