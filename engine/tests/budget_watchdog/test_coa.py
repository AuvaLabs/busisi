import json

import pytest

from engine.budget_watchdog.coa import CoaCatalogError, load_coa_catalog, summarize_coa_catalog


def _payload() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "checked_at": "2026-11-03T12:00:00+00:00",
            "catalogs": [
                {
                    "catalog_id": "coa-aar-nga",
                    "title": "Annual Audit Reports: National Government Agencies",
                    "source_url": "https://www.coa.gov.ph/reports/annual-audit-reports/aar-national-government-agencies/",
                    "checked_status": "reachable_by_index",
                    "evidence_note": "Official COA catalogue checked for relevant reports.",
                }
            ],
            "reports": [
                {
                    "report_id": "coa-cpa-benguet-local-roads-2022",
                    "title": "CPA on Local Road Projects under the 20% Development Fund",
                    "report_type": "citizen_participatory_audit",
                    "audited_entity": "Provincial Government of Benguet",
                    "fiscal_year": 2022,
                    "publication_date": "2024-02-21",
                    "source_url": "https://cpa.coa.gov.ph/wp-content/uploads/2024/02/report.pdf",
                    "landing_url": "https://cpa.coa.gov.ph/reports/",
                    "acquisition_status": "discovered",
                    "artifact_sha256": None,
                    "byte_size": None,
                    "page_count": None,
                    "scope_note": "Local road procurement and implementation.",
                    "evidence_note": "Discovered on the official CPA report catalogue.",
                }
            ],
            "project_coverage": [
                {
                    "case_id": "corazon-2024-phase-1",
                    "contract_id": "24HI0148",
                    "fiscal_year": 2024,
                    "status": "not_covered",
                    "report_id": None,
                    "match_confidence": "none",
                    "match_basis": [],
                    "page_start": None,
                    "page_end": None,
                    "observation_summary": "",
                    "recommendation_summary": "",
                    "management_response": "",
                    "implementation_status": "not_applicable",
                    "review_note": "No qualifying project-level COA evidence was located.",
                    "reviewed_at": "2026-11-03",
                }
            ],
        }
    ).encode()


def test_loads_report_catalogue_and_keeps_no_match_explicit() -> None:
    catalog = load_coa_catalog(_payload())
    summary = summarize_coa_catalog(catalog)

    assert summary.report_count == 1
    assert summary.checked_projects == 1
    assert summary.project_matches == 0
    assert summary.status_counts == {"not_covered": 1}
    assert catalog.project_coverage[0].report_id is None


def test_accepts_verified_archive_and_context_only_report_coverage() -> None:
    payload = json.loads(_payload())
    payload["reports"][0].update(
        acquisition_status="verified_archived",
        artifact_sha256="a" * 64,
        byte_size=2048,
        page_count=80,
    )
    payload["project_coverage"][0].update(
        status="program_audit_available",
        report_id="coa-cpa-benguet-local-roads-2022",
        match_confidence="none",
    )

    catalog = load_coa_catalog(json.dumps(payload).encode())
    summary = summarize_coa_catalog(catalog)

    assert summary.archived_reports == 1
    assert summary.project_matches == 0
    assert catalog.project_coverage[0].status == "program_audit_available"


def _mutate(mutator) -> bytes:
    payload = json.loads(_payload())
    mutator(payload)
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", "JSON is invalid"),
        (_mutate(lambda root: root.update(schema_version=2)), "schema version"),
        (
            _mutate(
                lambda root: root["reports"][0].update(
                    acquisition_status="verified_archived", artifact_sha256=None
                )
            ),
            "verified report",
        ),
        (
            _mutate(
                lambda root: root["project_coverage"][0].update(
                    status="reviewed_observation_match",
                    report_id=None,
                    match_confidence="exact",
                )
            ),
            "matched coverage",
        ),
        (
            _mutate(
                lambda root: root["project_coverage"][0].update(
                    report_id="missing-report", status="candidate_observation_match"
                )
            ),
            "unknown report",
        ),
        (
            _mutate(
                lambda root: root["project_coverage"][0].update(
                    page_start=3, page_end=2
                )
            ),
            "page range",
        ),
        (
            _mutate(lambda root: root["reports"][0].update(source_url="http://coa.test/x")),
            "HTTPS",
        ),
        (_mutate(lambda root: root.update(checked_at="2026-11-03T12:00:00")), "timezone"),
        (_mutate(lambda root: root.update(reports={})), "must be arrays"),
        (
            _mutate(lambda root: root["catalogs"][0].update(checked_status="unknown")),
            "checked_status",
        ),
        (
            _mutate(lambda root: root["reports"].append(root["reports"][0])),
            "duplicate report_id",
        ),
        (
            _mutate(
                lambda root: root["project_coverage"][0].update(match_basis={})
            ),
            "match_basis",
        ),
        (
            _mutate(
                lambda root: root["project_coverage"][0].update(
                    implementation_status="cleared"
                )
            ),
            "implementation_status",
        ),
    ],
)
def test_rejects_unverifiable_or_contradictory_audit_claims(
    payload: bytes, message: str
) -> None:
    with pytest.raises(CoaCatalogError, match=message):
        load_coa_catalog(payload)
