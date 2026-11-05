"""Acquire, archive, and reconcile official procurement documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from engine.budget_watchdog.acquisition_runner import RegisteredUrlFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.official_procurement_acquisition import (
    acquire_official_documents,
    attempt_official_source_downloads,
    indexed_records_for_blocked_sources,
    load_official_source_catalog,
)
from engine.budget_watchdog.official_procurement_evidence import (
    merge_indexed_records,
    reconcile_official_documents,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "ops" / "harness" / "fixtures" / "official_procurement_sources.json"
CANDIDATES = (
    ROOT
    / "cloudflare"
    / "busisi"
    / "public"
    / "data"
    / "research"
    / "multipurpose-buildings"
    / "v5"
    / "project-examples.json"
)
DEFAULT_OUTPUT = ROOT / "data" / "budget_watchdog" / "official-procurement-evidence"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _extract_pdf_text(path: Path) -> str:
    completed = subprocess.run(  # noqa: S603
        ["/usr/bin/pdftotext", "-layout", str(path), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or "pdftotext failed"
        raise ValueError(f"could not extract {path.name}: {message}")
    return completed.stdout


def _candidates() -> tuple[dict[str, str], tuple[str, ...]]:
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    rows = payload["public_value_candidates"]
    descriptions = {str(row["contract_id"]): str(row["description"]) for row in rows}
    return descriptions, tuple(sorted(descriptions))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--retrieved-at")
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    timestamp = (
        datetime.fromisoformat(args.retrieved_at) if args.retrieved_at else datetime.now(UTC)
    )
    if timestamp.tzinfo is None:
        raise ValueError("retrieved-at must include a timezone")
    checked_at = timestamp.isoformat()
    catalog_payload = CATALOG.read_bytes()
    sources = load_official_source_catalog(catalog_payload)
    output = args.output.resolve()
    source_dir = (args.source_dir or output / "downloads").resolve()
    source_manifest: list[dict[str, object]] = []
    if not args.skip_download:
        source_manifest = attempt_official_source_downloads(
            sources,
            destination=source_dir,
            fetcher=RegisteredUrlFetcher(),
            retrieved_at=timestamp,
        )
    else:
        source_manifest = [
            {
                "source_id": source.source_id,
                "source_url": source.source_url,
                "status": "downloaded",
                "http_status": 200,
                "retry_eligible": False,
            }
            for source in sources
        ]
    downloaded_ids = {
        str(item["source_id"]) for item in source_manifest if item.get("status") == "downloaded"
    }
    downloaded_sources = tuple(source for source in sources if source.source_id in downloaded_ids)
    documents = acquire_official_documents(
        downloaded_sources,
        source_dir=source_dir,
        archive=ArtifactArchive(output / "archive"),
        retrieved_at=checked_at,
        extract_text=_extract_pdf_text,
    )
    candidates, expected_ids = _candidates()
    review = reconcile_official_documents(
        candidates,
        documents,
        expected_contract_ids=expected_ids,
    )
    review = merge_indexed_records(
        review,
        indexed_records_for_blocked_sources(sources, source_manifest),
    )
    review.update(
        {
            "checked_at": checked_at,
            "catalog_sha256": _sha256(catalog_payload),
            "source_catalog_count": len(sources),
            "archived_source_count": len(documents),
            "blocked_source_count": sum(
                item.get("status") == "blocked" for item in source_manifest
            ),
            "source_manifest": source_manifest,
            "limitations": [
                "An official summary is not the underlying notice, contract, certificate, or receipt.",
                "An indexed official URL is not archived evidence. The source bytes must be acquired and hashed before verification.",
                "A source conflict is quarantined until another official record resolves the identity.",
                "Contracts without an accepted source remain discovery pending, not not-located.",
            ],
        }
    )
    output.mkdir(parents=True, exist_ok=True)
    review_path = output / "review.json"
    review_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": True,
                "review": str(review_path),
                "catalog_sha256": review["catalog_sha256"],
                "summary": review["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
