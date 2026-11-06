"""Build the private, balanced project-link review workspace."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.candidate_queue import generate_review_candidates
from engine.budget_watchdog.review_expansion import (
    build_review_workspace,
    evaluate_review_workspace,
)
from engine.budget_watchdog.review_precheck import run_review_prechecks
from engine.budget_watchdog.review_release import (
    export_confirmed_golden_set,
    write_review_status,
)
from engine.budget_watchdog.review_sources import load_delivery_contexts

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "budget_watchdog" / "watchdog.sqlite3",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=ROOT / "data" / "budget_watchdog" / "integrity-d1-bundle" / "chunks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "budget_watchdog" / "project-link-review",
    )
    parser.add_argument("--target", type=int, default=120)
    parser.add_argument("--candidate-limit", type=int, default=100_000)
    parser.add_argument("--export-golden", type=Path)
    args = parser.parse_args()

    candidates = generate_review_candidates(
        args.database,
        fiscal_years=(2024, 2025, 2026),
        limit=args.candidate_limit,
    )
    contexts = load_delivery_contexts(
        args.chunks,
        detail_migration=ROOT
        / "cloudflare"
        / "busisi"
        / "migrations"
        / "0011_delivery_details.sql",
        signal_migration=ROOT / "cloudflare" / "busisi" / "migrations" / "0005_integrity.sql",
        contract_ids=frozenset(item.contract_id for item in candidates),
    )
    result = build_review_workspace(candidates, contexts, args.output, target=args.target)
    precheck = run_review_prechecks(
        result.database_path,
        args.database,
        datetime.now(UTC).isoformat(),
    )
    status = evaluate_review_workspace(result.database_path)
    write_review_status(result.database_path, result.output_dir / "review-status.json")
    if args.export_golden:
        export_confirmed_golden_set(
            result.database_path,
            ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json",
            args.export_golden,
        )
    connection_summary = {
        "candidate_pool": len(candidates),
        "contexts_found": len(contexts),
        "output": str(result.output_dir),
        "selected_cases": result.case_count,
        "reviewed_cases": status.reviewed_cases,
        "precheck_passed": precheck.passed_cases,
        "precheck_failed": precheck.failed_cases,
        "release_ready": status.release_ready,
        "reasons": status.reasons,
    }
    print(json.dumps(connection_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
