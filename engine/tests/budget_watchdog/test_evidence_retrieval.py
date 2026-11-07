import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from engine.budget_watchdog.evidence_catalog import build_evidence_index
from engine.budget_watchdog.evidence_retrieval import (
    EvaluationCase,
    RetrievalFilters,
    VectorRecord,
    evaluate_retrieval,
    hybrid_search,
    lexical_search,
    load_evaluation_cases,
    public_qa_readiness,
    retrieval_manifest_sha256,
    store_vectors,
    vector_search,
)

ROOT = Path(__file__).resolve().parents[3]


def _index(tmp_path):
    documents = []
    for document_id, title, agency, text in (
        (
            "dpwh-nep",
            "DPWH National Expenditure Program",
            "DPWH",
            "Flood management program for the Pasig River and pumping stations.",
        ),
        (
            "deped-nep",
            "DepEd National Expenditure Program",
            "DepEd",
            "School building program for classrooms in Manila and Cebu.",
        ),
    ):
        path = tmp_path / f"{document_id}.txt"
        path.write_text(text, encoding="utf-8")
        documents.append(
            {
                "document_id": document_id,
                "title": title,
                "publisher": "DBM",
                "source_url": f"https://www.dbm.gov.ph/{document_id}",
                "artifact_path": path.name,
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "media_type": "text/plain",
                "fiscal_year": 2027,
                "stage": "nep",
                "agency": agency,
                "contract_id": "C-DPWH" if agency == "DPWH" else None,
                "project_id": "P-DEPED" if agency == "DepEd" else None,
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "documents": documents}))
    database = tmp_path / "retrieval.sqlite3"
    build_evidence_index(manifest, database)
    return database


def test_fts_search_is_ranked_filtered_and_citation_complete(tmp_path) -> None:
    database = _index(tmp_path)

    results = lexical_search(database, "Pasig flood pumping", limit=5)
    filtered = lexical_search(
        database,
        "program",
        filters=RetrievalFilters(fiscal_year=2027, agency="DepEd", stage="nep"),
        limit=5,
    )

    assert results[0].document_id == "dpwh-nep"
    assert results[0].page_start == 1
    assert len(results[0].artifact_sha256) == 64
    assert len(results[0].chunk_sha256) == 64
    assert results[0].source_url.startswith("https://")
    assert [item.document_id for item in filtered] == ["deped-nep"]


def test_query_is_treated_as_text_not_raw_fts_syntax(tmp_path) -> None:
    database = _index(tmp_path)

    assert lexical_search(database, 'flood OR "school" NOT program', limit=10)
    assert lexical_search(database, "!!!", limit=10) == ()


def test_optional_vectors_reject_stale_chunks_and_support_hybrid_search(tmp_path) -> None:
    database = _index(tmp_path)
    lexical = lexical_search(database, "school building", limit=5)
    school = lexical[0]
    flood = lexical_search(database, "flood management", limit=5)[0]
    store_vectors(
        database,
        "local-test-v1",
        (
            VectorRecord(school.chunk_id, school.chunk_sha256, (1.0, 0.0)),
            VectorRecord(flood.chunk_id, flood.chunk_sha256, (0.0, 1.0)),
        ),
    )

    vector = vector_search(database, "local-test-v1", (0.9, 0.1), limit=2)
    hybrid = hybrid_search(
        database,
        "classrooms",
        model_id="local-test-v1",
        query_vector=(0.9, 0.1),
        limit=2,
    )

    assert vector[0].document_id == "deped-nep"
    assert hybrid[0].document_id == "deped-nep"
    with pytest.raises(ValueError, match="chunk SHA-256"):
        store_vectors(
            database,
            "local-test-v1",
            (VectorRecord(school.chunk_id, "0" * 64, (1.0, 0.0)),),
        )


def test_evaluation_and_public_readiness_fail_closed(tmp_path) -> None:
    database = _index(tmp_path)
    cases = (
        EvaluationCase("flood", "Pasig River pumping", ("dpwh-nep",), False),
        EvaluationCase("school", "Manila classrooms", ("deped-nep",), False),
        EvaluationCase("missing", "lunar mining subsidy", (), True),
    )

    report = evaluate_retrieval(database, cases, limit=3)
    held = public_qa_readiness(report, minimum_cases=10)
    eligible = public_qa_readiness(
        report,
        minimum_cases=3,
        minimum_recall_bps=10_000,
        minimum_unanswerable_bps=10_000,
    )

    assert report.recall_bps == 10_000
    assert report.citation_integrity_bps == 10_000
    assert report.unanswerable_accuracy_bps == 10_000
    assert held.public_endpoint_allowed is False
    assert "evaluation cases" in " ".join(held.reasons)
    assert eligible.eligible_for_private_pilot is True
    assert eligible.public_endpoint_allowed is False


def test_tracked_evaluation_covers_the_tracked_document_catalog() -> None:
    manifest = json.loads(
        (ROOT / "ops/harness/fixtures/evidence_documents_2027.json").read_text()
    )
    cases = load_evaluation_cases(
        ROOT / "ops/harness/fixtures/evidence_retrieval_eval.json"
    )
    document_ids = {item["document_id"] for item in manifest["documents"]}
    expected_ids = {
        document_id
        for case in cases
        for document_id in case.expected_document_ids
    }

    assert len(cases) >= 40
    assert sum(case.unanswerable for case in cases) >= 10
    assert sum(
        case.unanswerable and case.case_id.startswith("unsupported-") for case in cases
    ) >= 6
    assert expected_ids == document_ids


def test_all_structured_filters_and_limits_are_enforced(tmp_path) -> None:
    database = _index(tmp_path)
    filters = RetrievalFilters(
        fiscal_year=2027,
        stage="nep",
        agency="DPWH",
        contract_id="C-DPWH",
        document_ids=("dpwh-nep",),
    )

    assert lexical_search(database, "program", filters=filters)[0].document_id == "dpwh-nep"
    assert lexical_search(
        database, "classrooms", filters=RetrievalFilters(project_id="P-DEPED")
    )[0].document_id == "deped-nep"
    for limit in (0, 101):
        with pytest.raises(ValueError, match="limit"):
            lexical_search(database, "program", limit=limit)
        with pytest.raises(ValueError, match="limit"):
            vector_search(database, "none", (1.0,), limit=limit)

    invalid_filters = (
        RetrievalFilters(fiscal_year=True),
        RetrievalFilters(stage=""),
        RetrievalFilters(document_ids=("",)),
    )
    for invalid in invalid_filters:
        with pytest.raises(ValueError, match="filter"):
            lexical_search(database, "program", filters=invalid)


def test_manifest_identity_must_exist_and_be_valid(tmp_path) -> None:
    database = _index(tmp_path)
    assert len(retrieval_manifest_sha256(database)) == 64
    connection = sqlite3.connect(database)
    with connection:
        connection.execute("DELETE FROM retrieval_metadata WHERE key='manifest_sha256'")
    connection.close()
    with pytest.raises(ValueError, match="manifest identity"):
        retrieval_manifest_sha256(database)


def test_vector_boundaries_fail_closed(tmp_path) -> None:
    database = _index(tmp_path)
    school = lexical_search(database, "school", limit=1)[0]
    flood = lexical_search(database, "flood", limit=1)[0]

    with pytest.raises(ValueError, match="required"):
        store_vectors(database, "", ())
    with pytest.raises(ValueError, match="invalid"):
        store_vectors(database, "model", (VectorRecord(school.chunk_id, "bad", (1.0,)),))
    for vector in ((), (0.0, 0.0), (float("nan"), 1.0), (True, 1.0)):
        with pytest.raises(ValueError, match="vector"):
            store_vectors(
                database,
                "model",
                (VectorRecord(school.chunk_id, school.chunk_sha256, vector),),
            )
    with pytest.raises(ValueError, match="same dimension"):
        store_vectors(
            database,
            "model",
            (
                VectorRecord(school.chunk_id, school.chunk_sha256, (1.0, 0.0)),
                VectorRecord(flood.chunk_id, flood.chunk_sha256, (1.0, 0.0, 0.0)),
            ),
        )

    store_vectors(
        database,
        "model",
        (VectorRecord(school.chunk_id, school.chunk_sha256, (1.0, 0.0)),),
    )
    with pytest.raises(ValueError, match="already exists"):
        store_vectors(
            database,
            "model",
            (VectorRecord(school.chunk_id, school.chunk_sha256, (1.0, 0.0)),),
        )
    with pytest.raises(ValueError, match="existing model"):
        store_vectors(
            database,
            "model",
            (VectorRecord(flood.chunk_id, flood.chunk_sha256, (1.0, 0.0, 0.0)),),
        )
    with pytest.raises(ValueError, match="dimension"):
        vector_search(database, "model", (1.0,), limit=1)

    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "UPDATE retrieval_vectors SET chunk_sha256 = ? WHERE model_id = ?",
            ("0" * 64, "model"),
        )
    connection.close()
    with pytest.raises(ValueError, match="stale"):
        vector_search(database, "model", (1.0, 0.0), limit=1)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not json", "valid JSON"),
        (json.dumps({"schema_version": 2, "cases": []}), "schema_version"),
        (json.dumps({"schema_version": 1, "cases": []}), "contain cases"),
        (json.dumps({"schema_version": 1, "cases": ["bad"]}), "must be objects"),
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "cases": [
                        {
                            "case_id": "x",
                            "question": "q",
                            "expected_document_ids": [],
                            "unanswerable": False,
                        }
                    ],
                }
            ),
            "unanswerable cases",
        ),
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "cases": [
                        {
                            "case_id": "x",
                            "question": "q",
                            "expected_document_ids": ["doc"],
                            "unanswerable": False,
                            "filters": "bad",
                        }
                    ],
                }
            ),
            "filters",
        ),
    ],
)
def test_invalid_evaluation_files_are_rejected(tmp_path, payload, message) -> None:
    path = tmp_path / "evaluation.json"
    path.write_text(payload)
    with pytest.raises(ValueError, match=message):
        load_evaluation_cases(path)


def test_evaluation_reports_misses_false_answers_and_bad_citations(tmp_path, monkeypatch) -> None:
    database = _index(tmp_path)
    actual = lexical_search(database, "flood", limit=1)[0]
    stale = replace(actual, chunk_sha256="0" * 64)
    monkeypatch.setattr(
        "engine.budget_watchdog.evidence_retrieval.lexical_search",
        lambda *args, **kwargs: (stale,),
    )
    cases = (
        EvaluationCase("miss", "flood", ("missing-document",), False),
        EvaluationCase("false-answer", "missing", (), True),
    )
    report = evaluate_retrieval(database, cases)
    held = public_qa_readiness(report, minimum_cases=2)

    assert report.recall_bps == 0
    assert report.unanswerable_accuracy_bps == 0
    assert report.citation_integrity_bps == 0
    assert report.failed_case_ids == ("miss", "false-answer")
    assert len(held.reasons) == 3


def test_evaluation_requires_unique_nonempty_cases(tmp_path) -> None:
    database = _index(tmp_path)
    with pytest.raises(ValueError, match="requires cases"):
        evaluate_retrieval(database, ())
    duplicate = EvaluationCase("same", "flood", ("dpwh-nep",), False)
    with pytest.raises(ValueError, match="unique"):
        evaluate_retrieval(database, (duplicate, duplicate))
