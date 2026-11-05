"""Maintain the private Busisi research queue without publishing draft content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.budget_watchdog.research_queue import build_private_queue_receipt

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = ROOT / "data" / "budget_watchdog" / "research-editor"
DEFAULT_QUEUE = PRIVATE_ROOT / "queue.json"
DEFAULT_RECEIPT = PRIVATE_ROOT / "queue-receipt.json"


def initial_queue() -> dict:
    return {
        "schema_version": "1.0",
        "updated_at": "2026-11-05",
        "items": [
            {
                "topic_id": "multipurpose-buildings",
                "question": "How many multipurpose-building records are active, and what can their titles and recorded amounts establish?",
                "status": "published",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/data/research/multipurpose-buildings/v4/sources.json"
                ],
                "missing_evidence": [],
                "target_slug": "multipurpose-buildings",
                "published_package_url": "https://busisi.org/data/research/multipurpose-buildings/v4/editorial-package.json",
                "downstream_ready": True,
            },
            {
                "topic_id": "fy2027-nep-house-changes",
                "question": "What changed between the FY2027 NEP and House project lists?",
                "status": "published",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/data/research/fy2027-nep-house-changes/v1/sources.json"
                ],
                "missing_evidence": [],
                "target_slug": "fy2027-nep-house-changes",
                "published_package_url": "https://busisi.org/data/research/fy2027-nep-house-changes/v1/editorial-package.json",
                "downstream_ready": True,
            },
            {
                "topic_id": "fy2027-change-concentration",
                "question": "Where are FY2027 House-stage project-list changes concentrated?",
                "status": "published",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/data/research/fy2027-change-concentration/v1/sources.json"
                ],
                "missing_evidence": [],
                "target_slug": "fy2027-change-concentration",
                "published_package_url": "https://busisi.org/data/research/fy2027-change-concentration/v1/editorial-package.json",
                "downstream_ready": True,
            },
            {
                "topic_id": "fy2027-health-facility-changes",
                "question": "What changed in the FY2027 health-facility project list, and where do the differences appear?",
                "status": "evidence_ready",
                "priority": 2,
                "evidence_sources": [
                    "https://busisi.org/data/research/fy2027-nep-house-changes/v1/sources.json"
                ],
                "missing_evidence": [],
                "target_slug": "fy2027-health-facility-changes",
                "published_package_url": None,
                "downstream_ready": False,
            },
            {
                "topic_id": "fy2027-later-stage-survival",
                "question": "Which House-stage project-list changes survived the Senate, bicameral, and enacted GAA stages?",
                "status": "blocked",
                "priority": 1,
                "evidence_sources": [],
                "missing_evidence": [
                    "Complete project-level Senate comparison",
                    "Bicameral project-level documents",
                    "Enacted FY2027 GAA project-level documents",
                ],
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
            {
                "topic_id": "project-payment-trace",
                "question": "Which selected projects can be followed from appropriation through release, award, payment, and completion evidence?",
                "status": "blocked",
                "priority": 2,
                "evidence_sources": [],
                "missing_evidence": [
                    "Contract-level official payment records",
                    "Complete acceptance and completion records",
                ],
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
        ],
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--initialize", action="store_true")
    return parser.parse_args()


def main() -> None:
    options = arguments()
    if options.initialize:
        options.queue.parent.mkdir(parents=True, exist_ok=True)
        if options.queue.exists():
            raise FileExistsError(f"private research queue already exists: {options.queue}")
        options.queue.write_text(
            json.dumps(initial_queue(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if not options.queue.is_file():
        raise FileNotFoundError(f"private research queue is unavailable: {options.queue}")
    queue = json.loads(options.queue.read_text(encoding="utf-8"))
    receipt = build_private_queue_receipt(queue, options.queue)
    options.receipt.parent.mkdir(parents=True, exist_ok=True)
    options.receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
