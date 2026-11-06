"""Deterministic lexical retrieval, optional vectors, and evaluation gates."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
BOOLEAN_WORDS = frozenset({"and", "or", "not", "near"})
SHA256 = re.compile(r"[a-f0-9]{64}")
MAX_RESULTS = 100
FULL_BASIS_POINTS = 10_000


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    fiscal_year: int | None = None
    stage: str | None = None
    agency: str | None = None
    contract_id: str | None = None
    project_id: str | None = None
    document_ids: tuple[str, ...] = ()


EMPTY_FILTERS = RetrievalFilters()


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: str
    document_id: str
    title: str
    publisher: str
    source_url: str
    artifact_sha256: str
    page_start: int
    page_end: int
    text: str
    chunk_sha256: str
    score: float
    retrieval_modes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VectorRecord:
    chunk_id: str
    chunk_sha256: str
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_document_ids: tuple[str, ...]
    unanswerable: bool
    filters: RetrievalFilters = RetrievalFilters()


@dataclass(frozen=True, slots=True)
class RetrievalEvaluation:
    case_count: int
    answerable_cases: int
    unanswerable_cases: int
    recalled_cases: int
    correctly_unanswered_cases: int
    recall_bps: int
    unanswerable_accuracy_bps: int
    citation_integrity_bps: int
    failed_case_ids: tuple[str, ...]
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class PublicQaReadiness:
    eligible_for_private_pilot: bool
    public_endpoint_allowed: bool
    reasons: tuple[str, ...]
    evaluation: RetrievalEvaluation


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def retrieval_manifest_sha256(database_path: Path) -> str:
    connection = _readonly(database_path)
    try:
        row = connection.execute(
            "SELECT value FROM retrieval_metadata WHERE key='manifest_sha256'"
        ).fetchone()
    finally:
        connection.close()
    if row is None or SHA256.fullmatch(row[0]) is None:
        raise ValueError("retrieval index has no valid manifest identity")
    return str(row[0])


def _fts_query(question: str) -> str | None:
    words = [
        match.group(0).casefold()
        for match in TOKEN.finditer(question)
        if match.group(0).casefold() not in BOOLEAN_WORDS
    ]
    unique = tuple(dict.fromkeys(words))
    if not unique:
        return None
    return " OR ".join('"' + word.replace('"', '""') + '"' for word in unique)


def _filter_sql(filters: RetrievalFilters) -> tuple[str, list[Any]]:
    if filters.fiscal_year is not None and (
        not isinstance(filters.fiscal_year, int) or isinstance(filters.fiscal_year, bool)
    ):
        raise ValueError("fiscal_year filter must be an integer")
    for field in ("stage", "agency", "contract_id", "project_id"):
        value = getattr(filters, field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{field} filter must be non-empty text")
    if not isinstance(filters.document_ids, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in filters.document_ids
    ):
        raise ValueError("document_ids filter must contain non-empty text")
    clauses: list[str] = []
    values: list[Any] = []
    for field in ("fiscal_year", "stage", "agency", "contract_id", "project_id"):
        value = getattr(filters, field)
        if value is not None:
            clauses.append(f"d.{field} = ?")
            values.append(value)
    if filters.document_ids:
        clauses.append("d.document_id IN (" + ",".join("?" for _ in filters.document_ids) + ")")
        values.extend(filters.document_ids)
    return (" AND " + " AND ".join(clauses) if clauses else ""), values


def _row_result(row: sqlite3.Row, score: float, modes: tuple[str, ...]) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        title=row["title"],
        publisher=row["publisher"],
        source_url=row["source_url"],
        artifact_sha256=row["artifact_sha256"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        text=row["chunk_text"],
        chunk_sha256=row["chunk_sha256"],
        score=score,
        retrieval_modes=modes,
    )


def lexical_search(
    database_path: Path,
    question: str,
    *,
    filters: RetrievalFilters = EMPTY_FILTERS,
    limit: int = 10,
) -> tuple[RetrievalResult, ...]:
    """Search archived passages with FTS5 BM25 and explicit metadata filters."""

    if limit <= 0 or limit > MAX_RESULTS:
        raise ValueError("limit must be between 1 and 100")
    query = _fts_query(question)
    if query is None:
        return ()
    filters_sql, values = _filter_sql(filters)
    sql = (
        "SELECT c.chunk_id,c.document_id,c.page_start,c.page_end,c.chunk_text,c.chunk_sha256,"
        "d.title,d.publisher,d.source_url,d.artifact_sha256,bm25(retrieval_chunks_fts,2.0,1.0,3.0) AS rank "
        "FROM retrieval_chunks_fts f JOIN retrieval_chunks c ON c.rowid=f.rowid "
        "JOIN retrieval_documents d ON d.document_id=c.document_id "
        "WHERE retrieval_chunks_fts MATCH ?" + filters_sql + " ORDER BY rank,c.chunk_id LIMIT ?"
    )
    connection = _readonly(database_path)
    try:
        rows = connection.execute(sql, (query, *values, limit)).fetchall()
    finally:
        connection.close()
    return tuple(_row_result(row, -float(row["rank"]), ("fts5-bm25",)) for row in rows)


def _validated_vector(values: tuple[float, ...], label: str) -> tuple[float, ...]:
    if not values or any(isinstance(value, bool) or not math.isfinite(value) for value in values):
        raise ValueError(f"{label} must contain finite numeric values")
    normalized = tuple(float(value) for value in values)
    if math.sqrt(sum(value * value for value in normalized)) == 0:
        raise ValueError(f"{label} must not be a zero vector")
    return normalized


def store_vectors(
    database_path: Path,
    model_id: str,
    records: tuple[VectorRecord, ...],
) -> None:
    """Attach precomputed private vectors without adding a model provider dependency."""

    if not model_id.strip() or not records:
        raise ValueError("model_id and vector records are required")
    connection = sqlite3.connect(database_path)
    try:
        expected_dimension: int | None = None
        for record in records:
            if SHA256.fullmatch(record.chunk_sha256) is None:
                raise ValueError("vector chunk SHA-256 is invalid")
            vector = _validated_vector(record.vector, "vector")
            if expected_dimension is None:
                expected_dimension = len(vector)
            elif len(vector) != expected_dimension:
                raise ValueError("all vectors for a model must have the same dimension")
            row = connection.execute(
                "SELECT chunk_sha256 FROM retrieval_chunks WHERE chunk_id = ?",
                (record.chunk_id,),
            ).fetchone()
            if row is None or row[0] != record.chunk_sha256:
                raise ValueError("vector chunk SHA-256 does not match the indexed passage")
            existing = connection.execute(
                "SELECT dimension FROM retrieval_vectors WHERE model_id = ? LIMIT 1",
                (model_id,),
            ).fetchone()
            if existing is not None and existing[0] != len(vector):
                raise ValueError("vector dimension does not match the existing model index")
            connection.execute(
                "INSERT INTO retrieval_vectors VALUES (?,?,?,?,?)",
                (
                    record.chunk_id,
                    model_id,
                    len(vector),
                    json.dumps(vector, separators=(",", ":")),
                    record.chunk_sha256,
                ),
            )
        connection.commit()
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise ValueError("vector already exists for this passage and model") from error
    finally:
        connection.close()


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("query vector dimension does not match the stored model")
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator


def vector_search(
    database_path: Path,
    model_id: str,
    query_vector: tuple[float, ...],
    *,
    filters: RetrievalFilters = EMPTY_FILTERS,
    limit: int = 10,
) -> tuple[RetrievalResult, ...]:
    if limit <= 0 or limit > MAX_RESULTS:
        raise ValueError("limit must be between 1 and 100")
    query = _validated_vector(query_vector, "query vector")
    filters_sql, values = _filter_sql(filters)
    sql = (
        "SELECT c.chunk_id,c.document_id,c.page_start,c.page_end,c.chunk_text,c.chunk_sha256,"
        "d.title,d.publisher,d.source_url,d.artifact_sha256,v.vector_json,v.chunk_sha256 AS vector_sha "
        "FROM retrieval_vectors v JOIN retrieval_chunks c ON c.chunk_id=v.chunk_id "
        "JOIN retrieval_documents d ON d.document_id=c.document_id "
        "WHERE v.model_id = ?" + filters_sql
    )
    connection = _readonly(database_path)
    try:
        rows = connection.execute(sql, (model_id, *values)).fetchall()
    finally:
        connection.close()
    scored = []
    for row in rows:
        if row["vector_sha"] != row["chunk_sha256"]:
            raise ValueError("stored vector is stale for its indexed passage")
        stored = tuple(json.loads(row["vector_json"]))
        scored.append(_row_result(row, _cosine(query, stored), ("semantic-vector",)))
    return tuple(sorted(scored, key=lambda item: (-item.score, item.chunk_id))[:limit])


def hybrid_search(
    database_path: Path,
    question: str,
    *,
    model_id: str,
    query_vector: tuple[float, ...],
    filters: RetrievalFilters = EMPTY_FILTERS,
    limit: int = 10,
) -> tuple[RetrievalResult, ...]:
    """Fuse BM25 and an explicitly supplied vector with reciprocal-rank fusion."""

    candidate_limit = min(MAX_RESULTS, max(limit * 4, 20))
    lexical = lexical_search(database_path, question, filters=filters, limit=candidate_limit)
    semantic = vector_search(
        database_path, model_id, query_vector, filters=filters, limit=candidate_limit
    )
    scores: dict[str, float] = {}
    values: dict[str, RetrievalResult] = {}
    modes: dict[str, set[str]] = {}
    for result_set in (lexical, semantic):
        for rank, item in enumerate(result_set, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (60 + rank)
            values[item.chunk_id] = item
            modes.setdefault(item.chunk_id, set()).update(item.retrieval_modes)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
    return tuple(
        replace(
            values[key],
            score=scores[key],
            retrieval_modes=tuple(sorted(modes[key])),
        )
        for key in ordered
    )


def load_evaluation_cases(path: Path) -> tuple[EvaluationCase, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("retrieval evaluation set must be valid JSON") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("retrieval evaluation schema_version must be 1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("retrieval evaluation set must contain cases")
    output = []
    seen = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("retrieval evaluation cases must be objects")
        case_id = item.get("case_id")
        question = item.get("question")
        expected = item.get("expected_document_ids")
        unanswerable = item.get("unanswerable")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("retrieval evaluation case_id must be unique text")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("retrieval evaluation question must be non-empty text")
        if not isinstance(expected, list) or not all(isinstance(value, str) for value in expected):
            raise ValueError("expected_document_ids must be a list of text")
        if not isinstance(unanswerable, bool) or unanswerable == bool(expected):
            raise ValueError("unanswerable cases must have no expected documents")
        raw_filters = item.get("filters", {})
        if not isinstance(raw_filters, dict):
            raise ValueError("evaluation filters must be an object")
        filters = RetrievalFilters(
            fiscal_year=raw_filters.get("fiscal_year"),
            stage=raw_filters.get("stage"),
            agency=raw_filters.get("agency"),
            contract_id=raw_filters.get("contract_id"),
            project_id=raw_filters.get("project_id"),
            document_ids=tuple(raw_filters.get("document_ids", ())),
        )
        output.append(EvaluationCase(case_id, question, tuple(expected), unanswerable, filters))
        seen.add(case_id)
    return tuple(output)


def _citation_valid(connection: sqlite3.Connection, result: RetrievalResult) -> bool:
    row = connection.execute(
        "SELECT c.chunk_sha256,d.artifact_sha256 FROM retrieval_chunks c "
        "JOIN retrieval_documents d USING(document_id) WHERE c.chunk_id = ?",
        (result.chunk_id,),
    ).fetchone()
    return row is not None and tuple(row) == (result.chunk_sha256, result.artifact_sha256)


def evaluate_retrieval(
    database_path: Path,
    cases: tuple[EvaluationCase, ...],
    *,
    limit: int = 5,
) -> RetrievalEvaluation:
    if not cases:
        raise ValueError("retrieval evaluation requires cases")
    case_ids = [item.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("retrieval evaluation case IDs must be unique")
    connection = _readonly(database_path)
    recalled = 0
    correct_empty = 0
    valid_citations = 0
    citation_count = 0
    failed = []
    try:
        manifest_sha256 = connection.execute(
            "SELECT value FROM retrieval_metadata WHERE key='manifest_sha256'"
        ).fetchone()[0]
        for item in cases:
            results = lexical_search(database_path, item.question, filters=item.filters, limit=limit)
            citation_count += len(results)
            valid_citations += sum(_citation_valid(connection, result) for result in results)
            if item.unanswerable:
                if not results:
                    correct_empty += 1
                else:
                    failed.append(item.case_id)
            elif set(item.expected_document_ids) & {result.document_id for result in results}:
                recalled += 1
            else:
                failed.append(item.case_id)
    finally:
        connection.close()
    answerable = sum(not item.unanswerable for item in cases)
    unanswerable = len(cases) - answerable
    return RetrievalEvaluation(
        len(cases),
        answerable,
        unanswerable,
        recalled,
        correct_empty,
        (recalled * 10_000) // answerable if answerable else 10_000,
        (correct_empty * 10_000) // unanswerable if unanswerable else 10_000,
        (valid_citations * 10_000) // citation_count if citation_count else 10_000,
        tuple(failed),
        manifest_sha256,
    )


def public_qa_readiness(
    evaluation: RetrievalEvaluation,
    *,
    minimum_cases: int = 30,
    minimum_recall_bps: int = 9_000,
    minimum_unanswerable_bps: int = 9_000,
) -> PublicQaReadiness:
    """Decide private-pilot eligibility while keeping public model Q&A disabled."""

    reasons = []
    if evaluation.case_count < minimum_cases:
        reasons.append(f"at least {minimum_cases} evaluation cases are required")
    if evaluation.recall_bps < minimum_recall_bps:
        reasons.append("retrieval recall is below the required score")
    if evaluation.unanswerable_accuracy_bps < minimum_unanswerable_bps:
        reasons.append("unanswerable questions are not rejected reliably enough")
    if evaluation.citation_integrity_bps != FULL_BASIS_POINTS:
        reasons.append("one or more retrieved passages failed its source integrity check")
    return PublicQaReadiness(not reasons, False, tuple(reasons), evaluation)
