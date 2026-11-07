"""Build a local, evidence-preserving quarantine review workspace."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.acquisition_universe import (
    AcquisitionUniverseSnapshot,
    QuarantinedAwardRow,
    UniverseContract,
)

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE review_cases (
    source_row_id TEXT PRIMARY KEY,
    review_status TEXT NOT NULL CHECK (review_status IN ('unresolved', 'resolved', 'retained')),
    reason TEXT NOT NULL,
    row_sha256 TEXT NOT NULL,
    reference_id TEXT,
    contract_no TEXT,
    award_title TEXT,
    notice_title TEXT NOT NULL
);
CREATE TABLE review_candidates (
    source_row_id TEXT NOT NULL REFERENCES review_cases(source_row_id),
    contract_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    budget_centavos INTEGER NOT NULL,
    province TEXT NOT NULL,
    region TEXT NOT NULL,
    accepted_match_rows INTEGER NOT NULL,
    PRIMARY KEY (source_row_id, contract_id)
);
CREATE TABLE review_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_row_id TEXT NOT NULL REFERENCES review_cases(source_row_id),
    resolution TEXT NOT NULL CHECK (resolution IN (
        'confirmed_reference_id', 'confirmed_contract_no', 'confirmed_award_title',
        'duplicate_or_superseded', 'retain_quarantine'
    )),
    resolved_contract_id TEXT,
    evidence_url TEXT NOT NULL CHECK (evidence_url GLOB 'https://*'),
    evidence_sha256 TEXT NOT NULL CHECK (
        length(evidence_sha256) = 64 AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    reviewer_note TEXT NOT NULL CHECK (length(trim(reviewer_note)) > 0),
    reviewed_at TEXT NOT NULL CHECK (length(trim(reviewed_at)) > 0),
    CHECK (
        (resolution IN (
            'confirmed_reference_id', 'confirmed_contract_no', 'confirmed_award_title'
        ) AND resolved_contract_id IS NOT NULL)
        OR (resolution IN (
            'duplicate_or_superseded', 'retain_quarantine'
        ) AND resolved_contract_id IS NULL)
    )
);
CREATE TRIGGER review_decision_candidate_required
BEFORE INSERT ON review_decisions
WHEN NEW.resolution IN (
    'confirmed_reference_id', 'confirmed_contract_no', 'confirmed_award_title'
) AND NOT EXISTS (
    SELECT 1 FROM review_candidates
    WHERE source_row_id = NEW.source_row_id
      AND contract_id = NEW.resolved_contract_id
)
BEGIN
    SELECT RAISE(ABORT, 'resolved contract must be a recorded candidate');
END;
"""


@dataclass(frozen=True, slots=True)
class QuarantineReviewResult:
    output_dir: Path
    case_count: int
    candidate_count: int
    manifest_sha256: str


def _write_database(snapshot: AcquisitionUniverseSnapshot, path: Path) -> int:
    contracts = {item.contract_id: item for item in snapshot.contracts}
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT INTO review_cases VALUES (?, 'unresolved', ?, ?, ?, ?, ?, ?)",
            [
                (
                    item.source_row_id,
                    item.reason,
                    item.row_sha256,
                    item.reference_id,
                    item.contract_no,
                    item.award_title,
                    item.notice_title,
                )
                for item in snapshot.quarantine
            ],
        )
        candidates = []
        for item in snapshot.quarantine:
            for contract_id in item.candidate_contract_ids:
                contract = contracts[contract_id]
                candidates.append(
                    (
                        item.source_row_id,
                        contract.contract_id,
                        contract.fiscal_year,
                        contract.description,
                        contract.category,
                        contract.budget_centavos,
                        contract.province,
                        contract.region,
                        contract.accepted_match_rows,
                    )
                )
        connection.executemany(
            "INSERT INTO review_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            candidates,
        )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("quarantine review database integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("quarantine review database has invalid references")
        connection.commit()
    finally:
        connection.close()
    return len(candidates)


def _write_csv(snapshot: AcquisitionUniverseSnapshot, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "source_row_id",
                "review_status",
                "reason",
                "reference_id",
                "contract_no",
                "award_title",
                "notice_title",
                "candidate_contract_ids",
                "row_sha256",
            ),
        )
        writer.writeheader()
        for item in snapshot.quarantine:
            writer.writerow(
                {
                    "source_row_id": item.source_row_id,
                    "review_status": "unresolved",
                    "reason": item.reason,
                    "reference_id": item.reference_id or "",
                    "contract_no": item.contract_no or "",
                    "award_title": item.award_title or "",
                    "notice_title": item.notice_title,
                    "candidate_contract_ids": "|".join(item.candidate_contract_ids),
                    "row_sha256": item.row_sha256,
                }
            )


def _case_html(item: QuarantinedAwardRow, contracts: dict[str, UniverseContract]) -> str:
    fields = (
        ("Reference ID", item.reference_id),
        ("Contract number", item.contract_no),
        ("Award title", item.award_title),
    )
    candidates = "".join(
        f"<article><b>{html.escape(contract_id)}</b><span>FY {contracts[contract_id].fiscal_year}</span>"
        f"<p>{html.escape(contracts[contract_id].description)}</p>"
        f"<small>{html.escape(contracts[contract_id].province)} · "
        f"{html.escape(contracts[contract_id].region)}</small></article>"
        for contract_id in item.candidate_contract_ids
    )
    return (
        f"<section><header><span>Unresolved</span><code>{html.escape(item.source_row_id)}</code>"
        f"</header><h2>{html.escape(item.notice_title or 'Untitled mirror row')}</h2>"
        f"<dl>{''.join(f'<div><dt>{label}</dt><dd>{html.escape(value or "Not stated")}</dd></div>' for label, value in fields)}</dl>"
        f"<div class='candidates'>{candidates}</div><footer>Row SHA-256: "
        f"<code>{html.escape(item.row_sha256)}</code></footer></section>"
    )


def _write_html(snapshot: AcquisitionUniverseSnapshot, path: Path) -> None:
    contracts = {item.contract_id: item for item in snapshot.contracts}
    cases = "".join(_case_html(item, contracts) for item in snapshot.quarantine)
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Internal quarantine review</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#111;font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1200px;margin:auto;padding:3rem 1rem}}h1{{font-size:clamp(2.4rem,6vw,5rem);line-height:.95}}
.boundary{{border-left:4px solid #111;background:#f3f3f1;padding:1rem 1.25rem;max-width:70rem}}
section{{margin:2rem 0;border:1px solid #bbb;padding:1.25rem}}header{{display:flex;justify-content:space-between;gap:1rem}}
header span{{background:#111;color:#fff;padding:.25rem .5rem;font-weight:700;text-transform:uppercase}}
code{{overflow-wrap:anywhere}}dl div{{display:grid;grid-template-columns:10rem 1fr;border-top:1px solid #ddd;padding:.6rem 0}}
dd{{margin:0}}.candidates{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:#bbb}}
.candidates article{{background:#fff;padding:1rem}}.candidates span{{float:right}}footer{{margin-top:1rem;color:#555}}
@media(max-width:650px){{.candidates{{grid-template-columns:1fr}}header,dl div{{display:grid;grid-template-columns:1fr}}}}
</style></head><body><main><p>BUSISI INTERNAL</p><h1>Internal quarantine review</h1>
<p class="boundary">These rows contain conflicting exact identifiers. Quarantine is a request for documentary review, not a finding of wrongdoing. Clear a case only with archived official evidence.</p>
<p><strong>{len(snapshot.quarantine)} unresolved source rows</strong></p>{cases}</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def build_quarantine_review(
    snapshot: AcquisitionUniverseSnapshot, output_dir: Path
) -> QuarantineReviewResult:
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    candidate_count = _write_database(snapshot, building / "quarantine-review.sqlite3")
    _write_csv(snapshot, building / "quarantine-review.csv")
    _write_html(snapshot, building / "index.html")
    manifest = {
        "award_sha256": snapshot.award_sha256,
        "case_count": len(snapshot.quarantine),
        "candidate_count": candidate_count,
        "checked_on": snapshot.checked_on.isoformat(),
        "delivery_sha256": snapshot.delivery_sha256,
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in building.iterdir()
            if path.name != "manifest.json"
        },
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return QuarantineReviewResult(output_dir, len(snapshot.quarantine), candidate_count, digest)
