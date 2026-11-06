"""Evidence packets, structured votes, and fail-closed council outcomes."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.evidence_retrieval import RetrievalResult
from engine.budget_watchdog.research_evidence import passage_payload

COUNCIL_SEATS = ("source_auditor", "identity_skeptic", "quality_reviewer")
DECISIONS = frozenset({"confirm", "reject", "unclear"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
SEVERITIES = frozenset({"blocking", "important", "note"})
REJECTION_QUORUM = 2
VERDICT_SCHEMA_VERSION = 2
PACKET_SCHEMA_VERSION = 2
UNSUPPORTED_GENERALIZATION = re.compile(
    r"\b(?:normal(?:ly)?|common(?:ly)?|usual(?:ly)?|typical(?:ly)?)\b", re.IGNORECASE
)
VERDICT_FIELDS = frozenset(
    {
        "schema_version",
        "case_id",
        "seat",
        "decision",
        "confidence",
        "summary",
        "identity_basis",
        "findings",
        "gaps",
        "does_not_prove",
        "recommendation",
    }
)


@dataclass(frozen=True, slots=True)
class CouncilVerdict:
    schema_version: int
    case_id: str
    seat: str
    decision: str
    confidence: str
    summary: str
    identity_basis: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    gaps: tuple[dict[str, Any], ...]
    does_not_prove: tuple[str, ...]
    recommendation: str


@dataclass(frozen=True, slots=True)
class CouncilOutcome:
    case_id: str
    round_number: int
    outcome: str
    reason: str
    votes: dict[str, str]
    blocking_findings: tuple[dict[str, Any], ...]
    packet_sha256: str


@dataclass(frozen=True, slots=True)
class CouncilStatus:
    completed_cases: int
    confirmed_cases: int
    rejected_cases: int
    unclear_cases: int
    incomplete_cases: int
    unanimous_cases: int
    agreement_bps: int
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_tokens: int


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _text_tuple(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{field} must be a{' non-empty' if required else ''} list")
    return tuple(_required_text(item, field) for item in value)


def _evidence_record_tuple(
    value: Any, field: str, required_fields: tuple[str, ...]
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    output = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entries must be objects")
        expected = set(required_fields) | {"evidence_paths"}
        if set(item) != expected:
            raise ValueError(f"{field} entry fields do not match the required schema")
        record = {key: _required_text(item.get(key), f"{field}.{key}") for key in required_fields}
        record["evidence_paths"] = _text_tuple(
            item.get("evidence_paths"), f"{field}.evidence_paths", required=True
        )
        output.append(record)
    return tuple(output)


def verdict_from_payload(payload: dict[str, Any]) -> CouncilVerdict:
    if set(payload) != VERDICT_FIELDS:
        raise ValueError("verdict fields do not match the required schema")
    findings = _evidence_record_tuple(
        payload.get("findings"),
        "findings",
        ("code", "severity", "claim", "evidence", "what_to_check"),
    )
    gaps = _evidence_record_tuple(payload.get("gaps"), "gaps", ("code", "label", "why_it_matters"))
    verdict = CouncilVerdict(
        schema_version=payload.get("schema_version"),
        case_id=_required_text(payload.get("case_id"), "case_id"),
        seat=_required_text(payload.get("seat"), "seat"),
        decision=_required_text(payload.get("decision"), "decision"),
        confidence=_required_text(payload.get("confidence"), "confidence"),
        summary=_required_text(payload.get("summary"), "summary"),
        identity_basis=_evidence_record_tuple(
            payload.get("identity_basis"), "identity_basis", ("claim",)
        ),
        findings=findings,
        gaps=gaps,
        does_not_prove=_text_tuple(payload.get("does_not_prove"), "does_not_prove", required=True),
        recommendation=_required_text(payload.get("recommendation"), "recommendation"),
    )
    validate_verdict(verdict)
    return verdict


def validate_verdict(verdict: CouncilVerdict) -> None:
    if verdict.schema_version != VERDICT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {VERDICT_SCHEMA_VERSION}")
    if verdict.seat not in COUNCIL_SEATS:
        raise ValueError("seat is invalid")
    if verdict.decision not in DECISIONS:
        raise ValueError("decision is invalid")
    if verdict.confidence not in CONFIDENCE_LEVELS:
        raise ValueError("confidence is invalid")
    if not verdict.identity_basis:
        raise ValueError("identity_basis must not be empty")
    for record in (*verdict.identity_basis, *verdict.findings, *verdict.gaps):
        if not record.get("evidence_paths"):
            raise ValueError("every evidence record requires evidence paths")
    for finding in verdict.findings:
        if finding["severity"] not in SEVERITIES:
            raise ValueError("finding severity is invalid")
        if not finding["evidence"].strip():
            raise ValueError("finding evidence must be provided")
    prose = [verdict.summary, verdict.recommendation, *verdict.does_not_prove]
    prose.extend(record["claim"] for record in verdict.identity_basis)
    prose.extend(
        value
        for finding in verdict.findings
        for value in (finding["claim"], finding["evidence"], finding["what_to_check"])
    )
    prose.extend(value for gap in verdict.gaps for value in (gap["label"], gap["why_it_matters"]))
    if any(UNSUPPORTED_GENERALIZATION.search(value) for value in prose):
        raise ValueError("verdict uses an unsupported generalization")


def _resolve_pointer(packet: dict[str, Any], pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("evidence path must be a JSON pointer")
    current: Any = packet
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise ValueError(f"evidence path does not exist: {pointer}")
    return current


def validate_verdict_against_packet(verdict: CouncilVerdict, packet: dict[str, Any]) -> None:
    validate_verdict(verdict)
    if verdict.case_id != packet.get("case_id"):
        raise ValueError("verdict case does not match the evidence packet")
    records = (*verdict.identity_basis, *verdict.findings, *verdict.gaps)
    for record in records:
        for pointer in record["evidence_paths"]:
            _resolve_pointer(packet, pointer)


def _source_classification(source_url: str) -> str:
    hostname = (urlparse(source_url).hostname or "").lower()
    if hostname == "gov.ph" or hostname.endswith(".gov.ph"):
        return "official government website"
    if hostname == "bettergov.ph" or hostname.endswith(".bettergov.ph"):
        return "civic data mirror, not an official government website"
    return "recorded web source with no government classification"


def build_evidence_packet(database_path: Path, case_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        case = connection.execute(
            "SELECT * FROM review_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        precheck = connection.execute(
            "SELECT * FROM review_prechecks WHERE case_id = ?", (case_id,)
        ).fetchone()
    finally:
        connection.close()
    if case is None:
        raise ValueError("review case does not exist")
    if precheck is None or not precheck["passed"]:
        raise ValueError("review case has not passed the source precheck")
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "case_id": case["case_id"],
        "question": "Do these two records describe the same funded public work?",
        "budget_record": {
            "fiscal_year": case["fiscal_year"],
            "budget_line_id": case["budget_line_id"],
            "description": case["budget_description"],
            "location": case["budget_location"],
            "amount_centavos": case["budget_amount_centavos"],
            "source_url": case["budget_source_url"],
            "source_classification": _source_classification(case["budget_source_url"]),
            "source_sha256": case["budget_source_sha256"],
        },
        "project_record": {
            "contract_id": case["contract_id"],
            "description": case["delivery_description"],
            "office": case["delivery_location"],
            "amount_centavos": case["delivery_budget_centavos"],
            "source_of_funds": case["source_of_funds"],
            "category": case["source_category"],
            "status": case["project_status"],
            "progress": case["reported_progress"],
            "contractor": case["contractor_name"],
            "contractor_parties": json.loads(case["contractor_parties_json"]),
            "region": case["region"],
            "province": case["province"],
            "coordinates": [case["latitude"], case["longitude"]],
            "has_source_image": bool(case["has_source_image"]),
            "source_url": case["delivery_source_url"],
            "source_classification": _source_classification(case["delivery_source_url"]),
            "source_sha256": case["delivery_source_sha256"],
        },
        "automatic_comparison": {
            "confidence": case["match_confidence"],
            "score": case["match_score"],
            "signals": json.loads(case["match_signals_json"]),
            "existing_questions": json.loads(case["evidence_questions_json"]),
        },
        "source_precheck": {
            "passed": bool(precheck["passed"]),
            "checks": json.loads(precheck["checks_json"]),
            "failures": json.loads(precheck["failures_json"]),
        },
        "limits": [
            "The records can describe separate phases or physical assets.",
            "A matching record does not prove payment, completion, quality, benefit, or wrongdoing.",
            "Missing evidence must remain a gap and must not be guessed.",
        ],
    }


def attach_document_evidence(
    packet: dict[str, Any],
    *,
    query: str,
    results: tuple[RetrievalResult, ...],
    index_manifest_sha256: str,
) -> dict[str, Any]:
    """Return a new council packet with one fixed set of cited document passages."""

    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        raise ValueError("document evidence can only be attached to a base council packet")
    if not query.strip():
        raise ValueError("document evidence query must be non-empty")
    if re.fullmatch(r"[a-f0-9]{64}", index_manifest_sha256) is None:
        raise ValueError("index manifest SHA-256 is invalid")
    copied = json.loads(json.dumps(packet, ensure_ascii=False))
    copied["schema_version"] = 3
    copied["document_evidence"] = {
        "query": query.strip(),
        "index_manifest_sha256": index_manifest_sha256,
        "retrieval_method": "fts5-bm25 with explicit metadata filters",
        "passages": [passage_payload(result) for result in results],
        "limits": [
            "A search match is supporting context, not proof that two records are the same work.",
            "Every factual statement must point to a field or cited passage in this packet.",
            "No passage may be added or replaced after review seats receive this packet.",
        ],
    }
    return copied


def packet_sha256(packet: dict[str, Any]) -> str:
    content = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


def record_verdict(
    database_path: Path,
    verdict: CouncilVerdict,
    *,
    round_number: int,
    model: str,
    packet_sha256: str,
    prompt_sha256: str,
    output_sha256: str,
    started_at: str,
    duration_seconds: float,
    token_usage: dict[str, int | None],
) -> None:
    validate_verdict(verdict)
    values = (
        verdict.case_id,
        round_number,
        verdict.seat,
        model,
        packet_sha256,
        prompt_sha256,
        verdict.decision,
        verdict.confidence,
        verdict.summary,
        json.dumps(verdict.identity_basis),
        json.dumps(verdict.findings),
        json.dumps(verdict.gaps),
        json.dumps(verdict.does_not_prove),
        verdict.recommendation,
        output_sha256,
        started_at,
        duration_seconds,
        token_usage.get("input_tokens"),
        token_usage.get("cached_input_tokens"),
        token_usage.get("cache_write_input_tokens"),
        token_usage.get("output_tokens"),
        token_usage.get("reasoning_tokens"),
    )
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO council_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
    finally:
        connection.close()


def _latest_round(connection: sqlite3.Connection, case_id: str) -> int:
    row = connection.execute(
        "SELECT MAX(round_number) FROM council_verdicts WHERE case_id = ?", (case_id,)
    ).fetchone()
    return int(row[0] or 1)


def adjudicate_case(
    database_path: Path,
    case_id: str,
    decided_at: str,
    *,
    round_number: int | None = None,
) -> CouncilOutcome:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        selected_round = round_number or _latest_round(connection, case_id)
        rows = connection.execute(
            "SELECT * FROM council_verdicts WHERE case_id = ? AND round_number = ? ORDER BY seat",
            (case_id, selected_round),
        ).fetchall()
        votes = {row["seat"]: row["decision"] for row in rows}
        packet_hashes = {row["packet_sha256"] for row in rows}
        blockers = tuple(
            finding
            for row in rows
            for finding in json.loads(row["findings_json"])
            if finding["severity"] == "blocking"
        )
        if set(votes) != set(COUNCIL_SEATS) or len(packet_hashes) != 1:
            outcome, reason = (
                "incomplete",
                "All three valid votes on the same evidence are required.",
            )
        elif sum(value == "reject" for value in votes.values()) >= REJECTION_QUORUM:
            outcome, reason = "rejected", "At least two reviewers rejected the proposed link."
        elif blockers:
            outcome, reason = (
                "unclear",
                "A blocking identity or evidence finding prevents confirmation.",
            )
        elif all(value == "confirm" for value in votes.values()):
            outcome, reason = (
                "confirmed",
                "All three reviewers confirmed the link without a blocker.",
            )
        else:
            outcome, reason = "unclear", "The reviewers did not unanimously confirm the link."
        packet_hash = next(iter(packet_hashes), "")
        result = CouncilOutcome(
            case_id, selected_round, outcome, reason, votes, blockers, packet_hash
        )
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO council_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    case_id,
                    selected_round,
                    outcome,
                    reason,
                    json.dumps(votes, sort_keys=True),
                    json.dumps(blockers),
                    decided_at,
                    packet_hash,
                ),
            )
        return result
    finally:
        connection.close()


def council_status(database_path: Path) -> CouncilStatus:
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        counts = dict(
            connection.execute(
                "WITH latest AS ("
                "SELECT case_id, MAX(round_number) AS round_number FROM council_outcomes "
                "GROUP BY case_id) SELECT o.outcome, COUNT(*) FROM council_outcomes o "
                "JOIN latest l ON o.case_id = l.case_id AND o.round_number = l.round_number "
                "GROUP BY o.outcome"
            ).fetchall()
        )
        completed = sum(counts.values())
        unanimous = connection.execute(
            "WITH latest AS ("
            "SELECT case_id, MAX(round_number) AS round_number FROM council_outcomes "
            "GROUP BY case_id) SELECT COUNT(*) FROM council_outcomes o JOIN latest l "
            "ON o.case_id = l.case_id AND o.round_number = l.round_number WHERE "
            "json_extract(votes_json, '$.source_auditor') = "
            "json_extract(votes_json, '$.identity_skeptic') AND "
            "json_extract(votes_json, '$.source_auditor') = "
            "json_extract(votes_json, '$.quality_reviewer')"
        ).fetchone()[0]
        attempt_count = connection.execute("SELECT COUNT(*) FROM council_attempts").fetchone()[0]
        usage_query = (
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(cached_input_tokens),0), "
            "COALESCE(SUM(cache_write_input_tokens),0), COALESCE(SUM(output_tokens),0), "
            "COALESCE(SUM(reasoning_tokens),0) FROM council_attempts"
            if attempt_count
            else "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(cached_input_tokens),0), "
            "COALESCE(SUM(cache_write_input_tokens),0), COALESCE(SUM(output_tokens),0), "
            "COALESCE(SUM(reasoning_tokens),0) FROM council_verdicts"
        )
        usage = connection.execute(usage_query).fetchone()
    finally:
        connection.close()
    agreement = (unanimous * 10_000) // completed if completed else 0
    return CouncilStatus(
        completed,
        counts.get("confirmed", 0),
        counts.get("rejected", 0),
        counts.get("unclear", 0),
        counts.get("incomplete", 0),
        unanimous,
        agreement,
        *map(int, usage),
    )
