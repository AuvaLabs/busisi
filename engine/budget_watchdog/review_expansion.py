"""Build a balanced, evidence-linked workspace for project-link review."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from engine.budget_watchdog.candidate_queue import ReviewCandidate

MINIMUM_REVIEWED_CASES = 100
MINIMUM_PRECISION_BPS = 9_500
MINIMUM_AGREEMENT_BPS = 9_500
TEN_MILLION_PESOS_CENTAVOS = 1_000_000_000
FIFTY_MILLION_PESOS_CENTAVOS = 5_000_000_000
ONE_HUNDRED_MILLION_PESOS_CENTAVOS = 10_000_000_000
CASE_INSERT = "INSERT INTO review_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE review_cases (
    case_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    budget_line_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    budget_description TEXT NOT NULL,
    delivery_description TEXT NOT NULL,
    budget_location TEXT NOT NULL,
    delivery_location TEXT NOT NULL,
    source_of_funds TEXT NOT NULL,
    budget_amount_centavos INTEGER NOT NULL,
    delivery_budget_centavos INTEGER NOT NULL,
    match_confidence TEXT NOT NULL CHECK (match_confidence IN ('exact', 'high')),
    match_score INTEGER NOT NULL,
    match_signals_json TEXT NOT NULL CHECK (json_valid(match_signals_json)),
    budget_source_url TEXT NOT NULL CHECK (budget_source_url GLOB 'https://*'),
    delivery_source_url TEXT NOT NULL CHECK (delivery_source_url GLOB 'https://*'),
    budget_source_sha256 TEXT NOT NULL,
    delivery_source_sha256 TEXT NOT NULL,
    category_group TEXT NOT NULL,
    source_category TEXT NOT NULL,
    amount_band TEXT NOT NULL,
    region TEXT NOT NULL,
    province TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    contractor_parties_json TEXT NOT NULL CHECK (json_valid(contractor_parties_json)),
    project_status TEXT NOT NULL,
    reported_progress TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    has_source_image INTEGER NOT NULL CHECK (has_source_image IN (0, 1)),
    evidence_questions_json TEXT NOT NULL CHECK (json_valid(evidence_questions_json))
);
CREATE TABLE review_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES review_cases(case_id),
    reviewer_id TEXT NOT NULL CHECK (length(trim(reviewer_id)) > 0),
    decision TEXT NOT NULL CHECK (decision IN ('confirm', 'reject', 'unclear')),
    evidence_url TEXT NOT NULL CHECK (evidence_url GLOB 'https://*'),
    evidence_sha256 TEXT NOT NULL CHECK (
        length(evidence_sha256) = 64 AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    reviewer_note TEXT NOT NULL CHECK (length(trim(reviewer_note)) > 0),
    reviewed_at TEXT NOT NULL CHECK (length(trim(reviewed_at)) > 0),
    UNIQUE (case_id, reviewer_id)
);
CREATE TRIGGER limit_two_independent_decisions
BEFORE INSERT ON review_decisions
WHEN (SELECT COUNT(*) FROM review_decisions WHERE case_id = NEW.case_id) >= 2
BEGIN
    SELECT RAISE(ABORT, 'each case accepts exactly two independent decisions');
END;
CREATE TABLE review_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    contract_id: str
    category: str
    status: str
    progress: str
    contractor_name: str
    contractor_parties: tuple[str, ...]
    province: str
    region: str
    latitude: str
    longitude: str
    has_source_image: bool
    evidence_questions: tuple[str, ...]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewExpansionCase:
    case_id: str
    candidate: ReviewCandidate
    context: DeliveryContext
    category_group: str
    amount_band: str
    is_joint_venture: bool


@dataclass(frozen=True, slots=True)
class ReviewWorkspaceStatus:
    total_cases: int
    reviewed_cases: int
    confirmed_cases: int
    rejected_cases: int
    unclear_cases: int
    precision_bps: int
    agreement_bps: int
    critical_failures: int
    release_ready: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewWorkspaceResult:
    output_dir: Path
    database_path: Path
    case_count: int
    manifest_sha256: str


def _category_group(value: str) -> str:
    text = value.casefold()
    for word, label in (
        ("road", "Roads"),
        ("building", "Buildings"),
        ("flood", "Flood control"),
        ("bridge", "Bridges"),
        ("water", "Water systems"),
    ):
        if word in text:
            return label
    return "Other public works"


def _amount_band(value: int) -> str:
    if value < TEN_MILLION_PESOS_CENTAVOS:
        return "Below ₱10 million"
    if value < FIFTY_MILLION_PESOS_CENTAVOS:
        return "₱10 million to below ₱50 million"
    if value < ONE_HUNDRED_MILLION_PESOS_CENTAVOS:
        return "₱50 million to below ₱100 million"
    return "₱100 million or more"


def _case(candidate: ReviewCandidate, context: DeliveryContext) -> ReviewExpansionCase:
    identity = f"{candidate.budget_line_id}|{candidate.fiscal_year}|{candidate.contract_id}"
    return ReviewExpansionCase(
        case_id=f"link-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        candidate=candidate,
        context=context,
        category_group=_category_group(context.category),
        amount_band=_amount_band(candidate.budget_amount_centavos),
        is_joint_venture=len(context.contractor_parties) > 1,
    )


def _stable_key(case: ReviewExpansionCase) -> str:
    return hashlib.sha256(case.case_id.encode()).hexdigest()


def select_balanced_cases(
    candidates: tuple[ReviewCandidate, ...],
    contexts: dict[str, DeliveryContext],
    *,
    target: int,
) -> tuple[ReviewExpansionCase, ...]:
    if target <= 0:
        raise ValueError("target must be positive")
    cases = [
        _case(item, contexts[item.contract_id])
        for item in candidates
        if item.contract_id in contexts
    ]
    if len(cases) < target:
        raise ValueError("not enough candidates with delivery details")
    remaining = sorted(cases, key=_stable_key)
    selected: list[ReviewExpansionCase] = []
    counts = {name: Counter() for name in ("year", "region", "category", "amount", "contractor")}
    joint_target = max(1, target // 10)
    question_target = max(1, target // 5)
    joint_count = 0
    question_count = 0
    while len(selected) < target:

        def rank(
            item: ReviewExpansionCase,
            current_joint: int = joint_count,
            current_questions: int = question_count,
        ) -> tuple[object, ...]:
            special = 2
            if item.is_joint_venture and current_joint < joint_target:
                special = 0
            elif item.context.evidence_questions and current_questions < question_target:
                special = 1
            return (
                special,
                counts["year"][item.candidate.fiscal_year],
                counts["region"][item.context.region],
                counts["category"][item.category_group],
                counts["amount"][item.amount_band],
                counts["contractor"][item.context.contractor_name],
                _stable_key(item),
            )

        chosen = min(remaining, key=rank)
        remaining.remove(chosen)
        selected.append(chosen)
        counts["year"][chosen.candidate.fiscal_year] += 1
        counts["region"][chosen.context.region] += 1
        counts["category"][chosen.category_group] += 1
        counts["amount"][chosen.amount_band] += 1
        counts["contractor"][chosen.context.contractor_name] += 1
        joint_count += int(chosen.is_joint_venture)
        question_count += int(bool(chosen.context.evidence_questions))
    return tuple(selected)


def _case_values(case: ReviewExpansionCase) -> tuple[object, ...]:
    candidate, context = case.candidate, case.context
    return (
        case.case_id,
        candidate.fiscal_year,
        candidate.budget_line_id,
        candidate.contract_id,
        candidate.budget_description,
        candidate.delivery_description,
        candidate.budget_location,
        candidate.delivery_location,
        candidate.source_of_funds,
        candidate.budget_amount_centavos,
        candidate.delivery_budget_centavos,
        candidate.confidence.value,
        candidate.score,
        json.dumps(candidate.signals),
        candidate.budget_evidence_url,
        candidate.delivery_evidence_url,
        candidate.budget_artifact_sha256,
        candidate.delivery_artifact_sha256 or context.source_sha256,
        case.category_group,
        context.category,
        case.amount_band,
        context.region,
        context.province,
        context.contractor_name,
        json.dumps(context.contractor_parties),
        context.status,
        context.progress,
        context.latitude,
        context.longitude,
        int(context.has_source_image),
        json.dumps(context.evidence_questions),
    )


def _write_database(cases: tuple[ReviewExpansionCase, ...], path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(CASE_INSERT, map(_case_values, cases))
        connection.executemany(
            "INSERT INTO review_metadata VALUES (?, ?)",
            (("critical_failures", "0"), ("required_cases", str(MINIMUM_REVIEWED_CASES))),
        )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("project-link review database failed its integrity check")
        connection.commit()
    finally:
        connection.close()


def evaluate_review_workspace(path: Path) -> ReviewWorkspaceStatus:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        total = connection.execute("SELECT COUNT(*) FROM review_cases").fetchone()[0]
        rows = connection.execute(
            "SELECT case_id, GROUP_CONCAT(decision, '|'), COUNT(*) "
            "FROM review_decisions GROUP BY case_id HAVING COUNT(*) = 2"
        ).fetchall()
        critical = int(
            connection.execute(
                "SELECT value FROM review_metadata WHERE key = 'critical_failures'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    reviewed = len(rows)
    decisions = [row[1].split("|") for row in rows]
    agreed = [values for values in decisions if values[0] == values[1]]
    confirmed = sum(values[0] == "confirm" for values in agreed)
    rejected = sum(values[0] == "reject" for values in agreed)
    unclear = reviewed - confirmed - rejected
    precision = (confirmed * 10_000) // reviewed if reviewed else 0
    agreement = (len(agreed) * 10_000) // reviewed if reviewed else 0
    reasons = []
    if reviewed < MINIMUM_REVIEWED_CASES:
        reasons.append("100 checked cases are required")
    if precision < MINIMUM_PRECISION_BPS:
        reasons.append("fewer than 95% of checked links were confirmed")
    if agreement < MINIMUM_AGREEMENT_BPS:
        reasons.append("the two reviewers agreed on fewer than 95% of cases")
    if critical:
        reasons.append("source totals still have a critical failure")
    return ReviewWorkspaceStatus(
        total,
        reviewed,
        confirmed,
        rejected,
        unclear,
        precision,
        agreement,
        critical,
        not reasons,
        tuple(reasons),
    )


def _money(centavos: int) -> str:
    pesos, remainder = divmod(centavos, 100)
    return f"₱{pesos:,}.{remainder:02d}"


def _write_html(cases: tuple[ReviewExpansionCase, ...], path: Path) -> None:
    cards = []
    for case in cases:
        item, context = case.candidate, case.context
        questions = ", ".join(context.evidence_questions) or "No current rule-based question"
        cards.append(f"""<article><header><b>Needs two checks</b><span>{html.escape(case.case_id)}</span></header>
<h2>{html.escape(item.budget_description)}</h2><p>{html.escape(context.region)} · {html.escape(context.province)} · {html.escape(case.category_group)}</p>
<dl><div><dt>Approved budget record</dt><dd>{_money(item.budget_amount_centavos)}</dd></div><div><dt>Project record</dt><dd>{_money(item.delivery_budget_centavos)}</dd></div><div><dt>Contract</dt><dd>{html.escape(item.contract_id)}</dd></div><div><dt>Recorded contractor</dt><dd>{html.escape(context.contractor_name)}</dd></div><div><dt>Questions already visible</dt><dd>{html.escape(questions)}</dd></div></dl>
<p><a href="{html.escape(item.budget_evidence_url)}">Open budget source</a> <a href="{html.escape(item.delivery_evidence_url)}">Open project source</a></p></article>""")
    path.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project link review</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#111;background:#fff;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:3rem 1rem}}h1{{font-size:clamp(2.5rem,7vw,5rem);line-height:1}}.intro{{max-width:70rem;border-left:4px solid #111;padding:1rem 1.25rem;background:#f4f2ed}}article{{border:1px solid #bbb;margin:1.5rem 0;padding:1.25rem}}header{{display:flex;justify-content:space-between;gap:1rem}}header b{{background:#111;color:#fff;padding:.25rem .5rem}}dl div{{display:grid;grid-template-columns:13rem 1fr;border-top:1px solid #ddd;padding:.5rem 0}}dd{{margin:0}}a{{color:#111;font-weight:700;margin-right:1rem}}@media(max-width:650px){{header,dl div{{display:grid;grid-template-columns:1fr}}}}
</style></head><body><main><p>BUSISI INTERNAL</p><h1>Project link review</h1><section class="intro"><h2>What reviewers need to decide</h2><p>Do the budget record and project record describe the same funded work? Check the title, year, amount, place, program, and source documents. A possible link or a question to check is not proof of wrongdoing.</p><p>Each case needs two independent decisions. Unclear or conflicting cases stay out of the public reviewed-project list.</p></section>{"".join(cards)}</main></body></html>""",
        encoding="utf-8",
    )


def _selection_digest(cases: tuple[ReviewExpansionCase, ...]) -> str:
    payload = json.dumps(
        [_case_values(case) for case in cases],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _write_case_packet(cases: tuple[ReviewExpansionCase, ...], path: Path) -> None:
    records = []
    for case in cases:
        record = asdict(case)
        record["candidate"]["confidence"] = case.candidate.confidence.value
        records.append(record)
    path.write_text(
        json.dumps({"count": len(records), "cases": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _distribution(cases: tuple[ReviewExpansionCase, ...]) -> dict[str, dict[str, int]]:
    dimensions = {
        "year": (str(case.candidate.fiscal_year) for case in cases),
        "region": (case.context.region for case in cases),
        "project_type": (case.category_group for case in cases),
        "value": (case.amount_band for case in cases),
    }
    return {name: dict(sorted(Counter(values).items())) for name, values in dimensions.items()}


def build_review_workspace(
    candidates: tuple[ReviewCandidate, ...],
    contexts: dict[str, DeliveryContext],
    output_dir: Path,
    *,
    target: int = 120,
) -> ReviewWorkspaceResult:
    cases = select_balanced_cases(candidates, contexts, target=target)
    selection_sha256 = _selection_digest(cases)
    existing_manifest = output_dir / "manifest.json"
    existing_database = output_dir / "project-link-review.sqlite3"
    if existing_manifest.is_file() and existing_database.is_file():
        current = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if current.get("selection_sha256") != selection_sha256:
            raise ValueError("review selection changed; use a new output folder")
        return ReviewWorkspaceResult(
            output_dir,
            existing_database,
            int(current["case_count"]),
            hashlib.sha256(existing_manifest.read_bytes()).hexdigest(),
        )
    building = output_dir.with_name(f".{output_dir.name}.building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    database = building / "project-link-review.sqlite3"
    _write_database(cases, database)
    _write_html(cases, building / "index.html")
    _write_case_packet(cases, building / "cases.json")
    status = evaluate_review_workspace(database)
    manifest = {
        "schema_version": 1,
        "case_count": len(cases),
        "reviewed_cases": status.reviewed_cases,
        "release_ready": status.release_ready,
        "selection_sha256": selection_sha256,
        "selection": "balanced across year, region, project type, value, contractor, joint records, and questions to check",
        "distribution": _distribution(cases),
        "files": {
            item.name: hashlib.sha256(item.read_bytes()).hexdigest()
            for item in building.iterdir()
            if item.name != "manifest.json"
        },
    }
    manifest_path = building / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shutil.rmtree(output_dir, ignore_errors=True)
    building.replace(output_dir)
    return ReviewWorkspaceResult(output_dir, output_dir / database.name, len(cases), digest)
