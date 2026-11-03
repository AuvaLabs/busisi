import json

import pytest

from engine.budget_watchdog.senate_budget import (
    SenateCatalogError,
    classify_stage,
    load_senate_catalog,
    parse_portal_rows,
    reconcile_senate_catalog,
)

PORTAL_HTML = b"""
<table><tbody id="court-documents">
  <tr class="folder-item portal-library-row" data-folder-id="123">
    <td class="portal-library-name"><span class="folder-name">
      House Bill No. 10858 (FY 2027 General Appropriations Bill)
      as Approved on Third Reading by the House of Representatives
    </span></td><td data-label="Type">Folder</td><td data-label="Size">-</td>
  </tr>
  <tr class="portal-library-row">
    <td class="portal-library-name">SEPO Budget Notes: Proposed 2027 National Budget</td>
    <td data-label="Type">Document</td><td data-label="Size">988 B</td>
    <td data-label="Date">October 13, 2026</td>
    <td><a data-file-id="417" class="open-doc">View</a></td>
  </tr>
</tbody></table>
"""


def _catalog_payload(*, stage: str = "house_gab", status: str = "discovered") -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "fiscal_year": 2027,
            "source": {
                "source_id": "senate-budget-portal",
                "url": "https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027",
                "retrieved_at": "2026-11-03T12:00:00+00:00",
                "acquisition_status": "direct_blocked_secondary_discovery",
                "discovery_source_id": "jina-reader",
            },
            "documents": [
                {
                    "document_id": "senate-portal:384",
                    "source_record_id": "384",
                    "title": "HB 10858 FOR 3RD READING VOL I-A",
                    "stage": stage,
                    "stage_label": "House bill, third reading",
                    "publisher": "Senate Budget Transparency Portal",
                    "volume": "I-A",
                    "publication_date": "2026-10-13",
                    "source_url": "https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027",
                    "viewer_url": "https://budget-transparency-portal.senate.gov.ph/file_viewer?id=384&type=Documents",
                    "acquisition_status": status,
                    "artifact_sha256": None,
                    "byte_size": None,
                    "mirror_url": None,
                    "evidence_note": "Discovered in the rendered official catalogue.",
                }
            ],
            "stage_coverage": [
                {"stage": "nep", "status": "available_elsewhere", "document_count": 0},
                {"stage": "house_gab", "status": "partial", "document_count": 1},
                {"stage": "senate_committee", "status": "unavailable", "document_count": 0},
                {"stage": "senate_amendment", "status": "unavailable", "document_count": 0},
                {"stage": "bicam", "status": "unavailable", "document_count": 0},
                {"stage": "gaa", "status": "unavailable", "document_count": 0},
            ],
        }
    ).encode()


def test_parses_portal_rows_without_treating_folders_as_documents() -> None:
    rows = parse_portal_rows(PORTAL_HTML)

    assert len(rows) == 2
    assert rows[0].kind == "folder"
    assert rows[0].record_id == "123"
    assert rows[1].kind == "document"
    assert rows[1].record_id == "417"
    assert rows[1].size_label == "988 B"
    assert rows[1].publication_date == "2026-10-13"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff", "invalid"),
        (b"<html></html>", "no catalogue rows"),
        (
            b'<tr class="portal-library-row"><td class="portal-library-name">File</td></tr>',
            "numeric record identifier",
        ),
        (
            b'<tr class="portal-library-row"><td class="portal-library-name">File</td>'
            b'<td data-label="Date">Not a date</td><a data-file-id="1"></a></tr>',
            "publication date",
        ),
    ],
)
def test_rejects_malformed_portal_rows(payload: bytes, message: str) -> None:
    with pytest.raises(SenateCatalogError, match=message):
        parse_portal_rows(payload)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("National Expenditure Program FY 2027", "nep"),
        ("HB 10858 FOR 3RD READING VOL I-C", "house_gab"),
        ("Senate Committee Report on the FY 2027 Budget", "senate_committee"),
        ("Senate amendments to House Bill 10858", "senate_amendment"),
        ("Bicameral Conference Committee Report FY 2027", "bicam"),
        ("FY 2027 General Appropriations Act", "gaa"),
        ("SEPO Budget Notes on the Proposed 2027 National Budget", "supporting"),
    ],
)
def test_classifies_documents_by_title_evidence(title: str, expected: str) -> None:
    assert classify_stage(title) == expected


def test_does_not_infer_enacted_gaa_from_portal_year_or_ambiguous_title() -> None:
    assert classify_stage("GAA 2027 documents") == "unknown"
    assert classify_stage("FY 2027 budget documents") == "unknown"


def test_loads_and_reconciles_catalog_with_explicit_missing_stages() -> None:
    catalog = load_senate_catalog(_catalog_payload())
    summary = reconcile_senate_catalog(catalog)

    assert summary.document_count == 1
    assert summary.verified_document_count == 0
    assert summary.discovered_document_count == 1
    assert summary.stage_counts["house_gab"] == 1
    assert summary.unavailable_stages == (
        "senate_committee",
        "senate_amendment",
        "bicam",
        "gaa",
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_catalog_payload(stage="gaa"), "classified stage"),
        (_catalog_payload(status="verified_archived"), "verified document"),
    ],
)
def test_rejects_stage_claims_and_verification_without_evidence(
    payload: bytes, message: str
) -> None:
    with pytest.raises(SenateCatalogError, match=message):
        load_senate_catalog(payload)


def _mutated_catalog(mutator) -> bytes:
    payload = json.loads(_catalog_payload())
    mutator(payload)
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", "JSON is invalid"),
        (_mutated_catalog(lambda root: root.update(schema_version=2)), "schema or fiscal year"),
        (
            _mutated_catalog(lambda root: root["source"].update(source_id="other")),
            "not the Senate portal",
        ),
        (_mutated_catalog(lambda root: root.update(documents={})), "must be arrays"),
        (
            _mutated_catalog(lambda root: root["documents"].append(root["documents"][0])),
            "duplicate document",
        ),
        (
            _mutated_catalog(lambda root: root["stage_coverage"].reverse()),
            "every budget stage in order",
        ),
        (
            _mutated_catalog(lambda root: root["stage_coverage"][1].update(document_count=2)),
            "does not reconcile",
        ),
        (
            _mutated_catalog(lambda root: root["documents"][0].update(source_record_id="abc")),
            "must be numeric",
        ),
        (
            _mutated_catalog(
                lambda root: root["documents"][0].update(
                    viewer_url="https://budget-transparency-portal.senate.gov.ph/file_viewer?id=9&type=Documents"
                )
            ),
            "does not match",
        ),
        (
            _mutated_catalog(
                lambda root: root["documents"][0].update(publication_date="13/10/2026")
            ),
            "ISO formatted",
        ),
        (
            _mutated_catalog(lambda root: root["documents"][0].update(artifact_sha256="a" * 64)),
            "must not claim",
        ),
    ],
)
def test_rejects_catalogue_boundary_violations(payload: bytes, message: str) -> None:
    with pytest.raises(SenateCatalogError, match=message):
        load_senate_catalog(payload)
