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
        "updated_at": "2026-11-23",
        "items": [
            {
                "topic_id": "multipurpose-buildings",
                "question": "How many multipurpose-building records are active, and what can their titles and recorded amounts establish?",
                "status": "published",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/data/research/multipurpose-buildings/v6/sources.json"
                ],
                "missing_evidence": [],
                "target_slug": "multipurpose-buildings",
                "published_package_url": "https://busisi.org/data/research/multipurpose-buildings/v6/editorial-package.json",
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
            {
                "topic_id": "community-projects-versus-local-needs",
                "question": "Are communities getting projects that match their documented needs?",
                "status": "blocked",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/data/research/multipurpose-buildings/v6/sources.json",
                    "https://psa.gov.ph/content/2024-census-population-popcen-population-counts-declared-official-president",
                    "https://psa.gov.ph/statistics/poverty",
                    "https://www.deped.gov.ph/2026/03/10/deped-katuwang-ang-mga-lgu-sa-pagpuno-ng-165000-classroom-gap/",
                ],
                "missing_evidence": [
                    "Archived official local need counts with place identifiers that can be matched to projects",
                    "Complete project purpose, service area, and beneficiary evidence",
                    "District boundaries and project locations that pass identity checks",
                ],
                "comparison_plan": {
                    "article_format": "question-led-v1",
                    "reader_value": "Shows whether recorded projects respond to needs documented for the same communities.",
                    "peer_places": [
                        "Philippine regions",
                        "Philippine provinces",
                        "Philippine legislative districts",
                    ],
                    "measures": [
                        "recorded project count and amount",
                        "population and household count",
                        "officially documented service gap or deprivation",
                    ],
                    "normalization": [
                        "pesos per resident",
                        "projects per 10,000 residents",
                        "service gap per 1,000 intended users",
                    ],
                    "same_year_required": True,
                    "release_requirements": [
                        "Archived official source files with SHA-256 identities",
                        "Matching official place identifiers",
                        "Matching reference years and definitions",
                        "Separate display of each need measure without a black-box score",
                    ],
                },
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
            {
                "topic_id": "flood-control-versus-exposure",
                "question": "Is flood-control spending going where the most people are exposed to flooding?",
                "status": "blocked",
                "priority": 1,
                "evidence_sources": [
                    "https://busisi.org/sources/",
                    "https://psa.gov.ph/content/2024-census-population-popcen-population-counts-declared-official-president",
                ],
                "missing_evidence": [
                    "Archived official flood-hazard and exposed-population data with a reusable license",
                    "Project coordinates or service-area geometry that pass location checks",
                    "Project purpose and design evidence sufficient to link spending to a specific hazard area",
                ],
                "comparison_plan": {
                    "article_format": "question-led-v1",
                    "reader_value": "Shows where recorded flood-control money and documented flood exposure do or do not line up.",
                    "peer_places": [
                        "Philippine regions",
                        "Philippine provinces",
                        "Philippine legislative districts",
                    ],
                    "measures": [
                        "recorded flood-control amount",
                        "people exposed to flooding",
                        "land area in each comparable hazard band",
                    ],
                    "normalization": [
                        "pesos per exposed resident",
                        "projects per 10,000 exposed residents",
                        "pesos per square kilometre in the same hazard band",
                    ],
                    "same_year_required": True,
                    "release_requirements": [
                        "Archived official source files with SHA-256 identities",
                        "A published geographic matching rule",
                        "Separate results for missing, approximate, and exact locations",
                        "No claim that spending alone proves protection or effectiveness",
                    ],
                },
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
            {
                "topic_id": "classroom-gap-asean-comparison",
                "question": "How does the Philippines' classroom shortage compare with similar ASEAN countries?",
                "status": "blocked",
                "priority": 2,
                "evidence_sources": [
                    "https://www.deped.gov.ph/2026/03/10/deped-katuwang-ang-mga-lgu-sa-pagpuno-ng-165000-classroom-gap/",
                    "https://databrowser.uis.unesco.org/",
                    "https://data.worldbank.org/indicator/SE.XPD.TOTL.GD.ZS?locations=PH",
                ],
                "missing_evidence": [
                    "Same-year classroom stock, learner count, and shortage measures for every peer country",
                    "A verified definition crosswalk for classrooms, schools, shifts, and enrolled learners",
                    "Archived machine-readable observations from the official or multilateral publishers",
                ],
                "comparison_plan": {
                    "article_format": "question-led-v1",
                    "reader_value": "Places the Philippine classroom gap beside comparable countries without turning unlike figures into a ranking.",
                    "peer_places": [
                        "Indonesia",
                        "Malaysia",
                        "Thailand",
                        "Vietnam",
                    ],
                    "measures": [
                        "classroom stock",
                        "enrolled learner count",
                        "officially reported classroom gap",
                        "education spending as a share of gross domestic product",
                    ],
                    "normalization": [
                        "classrooms per 1,000 enrolled learners",
                        "missing classrooms per 1,000 enrolled learners",
                        "education spending as a percentage of gross domestic product",
                    ],
                    "same_year_required": True,
                    "release_requirements": [
                        "Archived official or multilateral source files with SHA-256 identities",
                        "One definition and one reference year across all displayed countries",
                        "Visible missing-data and definition notes",
                        "No country ranking when coverage or definitions do not match",
                    ],
                },
                "target_slug": None,
                "published_package_url": None,
                "downstream_ready": False,
            },
            {
                "topic_id": "project-trail-country-comparison",
                "question": "What public-project information do other governments publish that the Philippines still does not?",
                "status": "blocked",
                "priority": 2,
                "evidence_sources": [
                    "https://internationalbudget.org/open-budget-survey/country-results/2023/philippines",
                ],
                "missing_evidence": [
                    "Archived official portal documentation and sample records for each peer country",
                    "A field-by-field crosswalk from budget through release, award, payment, completion, and audit",
                    "A current Philippine publication-coverage baseline using the same field definitions",
                ],
                "comparison_plan": {
                    "article_format": "question-led-v1",
                    "reader_value": "Shows which missing public records prevent citizens from following a project from approval to result.",
                    "peer_places": ["Indonesia", "South Korea"],
                    "measures": [
                        "budget fields published",
                        "release and award fields published",
                        "payment, completion, and audit fields published",
                        "stable identifiers available across stages",
                    ],
                    "normalization": [
                        "share of required fields publicly available",
                        "share of stages connected by a stable identifier",
                        "days between official event and public release",
                    ],
                    "same_year_required": True,
                    "release_requirements": [
                        "Archived official portal records with SHA-256 identities",
                        "The same field and stage definitions for every country",
                        "A visible distinction between published, restricted, and not found",
                        "No claim that a missing online field proves the underlying record does not exist",
                    ],
                },
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
