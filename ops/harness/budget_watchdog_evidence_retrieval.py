"""Build, test, and use the private Busisi document retrieval index."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.budget_watchdog.evidence_catalog import build_evidence_index
from engine.budget_watchdog.evidence_retrieval import (
    RetrievalFilters,
    VectorRecord,
    evaluate_retrieval,
    hybrid_search,
    lexical_search,
    load_evaluation_cases,
    public_qa_readiness,
    retrieval_manifest_sha256,
    store_vectors,
)
from engine.budget_watchdog.research_evidence import (
    build_research_evidence_packet,
    passage_payload,
    write_research_evidence_packet,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "ops" / "harness" / "fixtures" / "evidence_documents_2027.json"
DEFAULT_EVALUATION = ROOT / "ops" / "harness" / "fixtures" / "evidence_retrieval_eval.json"
DEFAULT_DIRECTORY = ROOT / "data" / "budget_watchdog" / "evidence-retrieval"
DEFAULT_DATABASE = DEFAULT_DIRECTORY / "evidence-retrieval.sqlite3"
DEFAULT_REPORT = DEFAULT_DIRECTORY / "retrieval-evaluation.json"


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _filters(args: argparse.Namespace) -> RetrievalFilters:
    return RetrievalFilters(
        fiscal_year=args.fiscal_year,
        stage=args.stage,
        agency=args.agency,
        contract_id=args.contract_id,
        project_id=args.project_id,
        document_ids=tuple(args.document_id),
    )


def _require_database(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"retrieval database does not exist: {path}")


def _build(args: argparse.Namespace) -> dict[str, Any]:
    result = build_evidence_index(args.manifest, args.database, catalog_root=ROOT)
    return asdict(result)


def _query(args: argparse.Namespace) -> dict[str, Any]:
    _require_database(args.database)
    if args.query_vector is None:
        results = lexical_search(
            args.database, args.question, filters=_filters(args), limit=args.limit
        )
    else:
        if not args.model_id:
            raise ValueError("--model-id is required with --query-vector")
        vector = tuple(float(value) for value in args.query_vector.split(","))
        results = hybrid_search(
            args.database,
            args.question,
            model_id=args.model_id,
            query_vector=vector,
            filters=_filters(args),
            limit=args.limit,
        )
    return {
        "schema_version": 1,
        "question": args.question,
        "index_manifest_sha256": retrieval_manifest_sha256(args.database),
        "results": [passage_payload(item) | {"score": item.score} for item in results],
    }


def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    _require_database(args.database)
    evaluation = evaluate_retrieval(
        args.database, load_evaluation_cases(args.evaluation), limit=args.limit
    )
    readiness = public_qa_readiness(evaluation)
    payload = {
        "schema_version": 1,
        "evaluation": asdict(evaluation),
        "readiness": asdict(readiness),
        "public_endpoint_present": False,
        "decision": (
            "eligible_for_private_pilot"
            if readiness.eligible_for_private_pilot
            else "hold_and_improve_retrieval"
        ),
    }
    _json_write(args.report, payload)
    return payload


def _research(args: argparse.Namespace) -> dict[str, Any]:
    _require_database(args.database)
    results = lexical_search(
        args.database, args.question, filters=_filters(args), limit=args.limit
    )
    packet = build_research_evidence_packet(
        story_id=args.story_id,
        question=args.question,
        results=results,
        index_manifest_sha256=retrieval_manifest_sha256(args.database),
    )
    digest = write_research_evidence_packet(packet, args.output)
    return {"output": str(args.output), "sha256": digest, "passages": len(results)}


def _vectors(args: argparse.Namespace) -> dict[str, Any]:
    _require_database(args.database)
    payload = json.loads(args.vector_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("vector import schema_version must be 1")
    model_id = payload.get("model_id")
    raw_records = payload.get("vectors")
    if not isinstance(model_id, str) or not isinstance(raw_records, list):
        raise ValueError("vector import requires model_id and vectors")
    records = tuple(
        VectorRecord(
            item["chunk_id"],
            item["chunk_sha256"],
            tuple(item["vector"]),
        )
        for item in raw_records
        if isinstance(item, dict)
    )
    if len(records) != len(raw_records):
        raise ValueError("every vector import entry must be an object")
    store_vectors(args.database, model_id, records)
    return {"model_id": model_id, "stored_vectors": len(records)}


def _audit(args: argparse.Namespace) -> dict[str, Any]:
    build = _build(args)
    evaluation = _evaluate(args)
    return {"build": build, **evaluation}


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--limit", type=int, default=5)


def _search_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("question")
    parser.add_argument("--fiscal-year", type=int)
    parser.add_argument("--stage")
    parser.add_argument("--agency")
    parser.add_argument("--contract-id")
    parser.add_argument("--project-id")
    parser.add_argument("--document-id", action="append", default=[])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build")
    build.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--database", type=Path, default=DEFAULT_DATABASE)

    query = commands.add_parser("query")
    _common(query)
    _search_arguments(query)
    query.add_argument("--model-id")
    query.add_argument("--query-vector")

    evaluate = commands.add_parser("evaluate")
    _common(evaluate)
    evaluate.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    evaluate.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    research = commands.add_parser("research")
    _common(research)
    _search_arguments(research)
    research.add_argument("--story-id", required=True)
    research.add_argument("--output", type=Path, required=True)

    vectors = commands.add_parser("import-vectors")
    vectors.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    vectors.add_argument("vector_file", type=Path)

    audit = commands.add_parser("audit")
    _common(audit)
    audit.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    audit.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    audit.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if getattr(args, "limit", 1) < 1:
        raise ValueError("limit must be positive")
    handlers = {
        "build": _build,
        "query": _query,
        "evaluate": _evaluate,
        "research": _research,
        "import-vectors": _vectors,
        "audit": _audit,
    }
    print(json.dumps(handlers[args.command](args), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
