import hashlib
from dataclasses import replace

import pytest

from engine.budget_watchdog.official_procurement_evidence import (
    EvidenceBinding,
    OfficialDocument,
    ProcurementEvidenceError,
    reconcile_official_documents,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _document(
    text: str,
    bindings: tuple[EvidenceBinding, ...],
    *,
    payload: bytes = b"official-pdf",
    source_id: str = "dpwh-test-pmr",
) -> OfficialDocument:
    return OfficialDocument(
        source_id=source_id,
        source_url="https://www.dpwh.gov.ph/dpwh/test.pdf",
        document_type="procurement_monitoring_report",
        retrieved_at="2026-11-05T10:00:00+00:00",
        artifact_sha256=_digest(payload),
        payload=payload,
        extracted_text=text,
        bindings=bindings,
    )


def test_reconciles_exact_official_summary_without_overstating_artifact() -> None:
    binding = EvidenceBinding(
        contract_id="24DD0136",
        evidence_type="procurement_monitoring_report",
        evidence_class="official_summary",
        identity_terms=("MULTI PURPOSE BUILDING", "DAGATAN", "SAN JOSE"),
    )
    document = _document(
        "24DD0136 Completion of Multi-Purpose Building at Barangay Dagatan, San Jose",
        (binding,),
    )

    review = reconcile_official_documents(
        {
            "24DD0136": "Completion of Multi-Purpose Building at Dagatan, San Jose",
            "24CD0251": "Construction of Multi-Purpose Building in Bulacan",
        },
        (document,),
        expected_contract_ids=("24DD0136", "24CD0251"),
    )

    assert review["summary"] == {
        "targeted_contracts": 2,
        "contracts_with_official_sources": 1,
        "official_artifact_records": 0,
        "official_summary_records": 1,
        "quarantined_contracts": 0,
        "discovery_pending_contracts": 1,
    }
    assert review["records"][0]["status"] == "official_summary_archived"
    assert review["contracts"]["24CD0251"]["state"] == "discovery_pending"


def test_quarantines_identity_conflict_even_when_another_source_matches() -> None:
    exact = EvidenceBinding(
        contract_id="24OD0280",
        evidence_type="bid_notice",
        evidence_class="official_summary",
        identity_terms=("MULTI PURPOSE BUILDING", "LAON", "VEINTE REALES"),
    )
    conflict = EvidenceBinding(
        contract_id="24OD0280",
        evidence_type="procurement_plan",
        evidence_class="identity_conflict",
        identity_terms=("WATER SUPPLY SYSTEM", "BIGNAY"),
        limitation="Official sources associate this contract number with different projects.",
    )
    documents = (
        _document(
            "24OD0280 Construction of Multi-Purpose Building, Laon, Veinte Reales",
            (exact,),
        ),
        _document(
            "24OD0280 Construction of Water Supply System, Barangay Bignay",
            (conflict,),
            payload=b"different-official-pdf",
            source_id="dpwh-test-app",
        ),
    )

    review = reconcile_official_documents(
        {"24OD0280": "Construction of Multi-Purpose Building, Laon, Veinte Reales"},
        documents,
        expected_contract_ids=("24OD0280",),
    )

    assert review["summary"]["quarantined_contracts"] == 1
    assert review["contracts"]["24OD0280"]["state"] == "source_conflict_quarantined"
    assert {row["status"] for row in review["records"]} == {
        "official_summary_archived",
        "source_conflict_quarantined",
    }


def test_rejects_missing_identity_terms_and_untrusted_source() -> None:
    binding = EvidenceBinding(
        contract_id="24DD0136",
        evidence_type="procurement_monitoring_report",
        evidence_class="official_summary",
        identity_terms=("DAGATAN", "SAN JOSE"),
    )
    missing = _document("24DD0136 unrelated road project", (binding,))

    with pytest.raises(ProcurementEvidenceError, match="identity terms"):
        reconcile_official_documents(
            {"24DD0136": "Completion of Multi-Purpose Building at Dagatan"},
            (missing,),
            expected_contract_ids=("24DD0136",),
        )

    untrusted = OfficialDocument(
        source_id="mirror",
        source_url="https://example.com/test.pdf",
        document_type="procurement_monitoring_report",
        retrieved_at="2026-11-05T10:00:00+00:00",
        artifact_sha256=_digest(b"official-pdf"),
        payload=b"official-pdf",
        extracted_text="24DD0136 DAGATAN SAN JOSE",
        bindings=(binding,),
    )
    with pytest.raises(ProcurementEvidenceError, match="official DPWH"):
        reconcile_official_documents(
            {"24DD0136": "Completion of Multi-Purpose Building at Dagatan"},
            (untrusted,),
            expected_contract_ids=("24DD0136",),
        )


def test_rejects_payload_digest_mismatch() -> None:
    binding = EvidenceBinding(
        contract_id="24DD0136",
        evidence_type="procurement_plan",
        evidence_class="official_artifact",
        identity_terms=("DAGATAN",),
    )
    document = OfficialDocument(
        source_id="dpwh-test-app",
        source_url="https://www.dpwh.gov.ph/dpwh/test.pdf",
        document_type="annual_procurement_plan",
        retrieved_at="2026-11-05T10:00:00+00:00",
        artifact_sha256="a" * 64,
        payload=b"official-pdf",
        extracted_text="24DD0136 DAGATAN",
        bindings=(binding,),
    )

    with pytest.raises(ProcurementEvidenceError, match="digest"):
        reconcile_official_documents(
            {"24DD0136": "Completion of Multi-Purpose Building at Dagatan"},
            (document,),
            expected_contract_ids=("24DD0136",),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_type", "unknown", "document type"),
        ("retrieved_at", "not-a-time", "ISO timestamp"),
        ("retrieved_at", "2026-11-05T10:00:00", "timezone-aware"),
        ("extracted_text", "", "extracted text"),
        ("bindings", (), "at least one binding"),
    ],
)
def test_rejects_invalid_official_document_metadata(
    field: str, value: object, message: str
) -> None:
    binding = EvidenceBinding(
        contract_id="24DD0136",
        evidence_type="procurement_plan",
        evidence_class="official_artifact",
        identity_terms=("DAGATAN",),
    )
    document = replace(_document("24DD0136 DAGATAN", (binding,)), **{field: value})
    with pytest.raises(ProcurementEvidenceError, match=message):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (document,),
            expected_contract_ids=("24DD0136",),
        )


@pytest.mark.parametrize(
    ("binding", "message"),
    [
        (
            EvidenceBinding("bad", "procurement_plan", "official_artifact", ("DAGATAN",)),
            "contract ID",
        ),
        (
            EvidenceBinding("24DD0137", "procurement_plan", "official_artifact", ("DAGATAN",)),
            "candidate set",
        ),
        (
            EvidenceBinding("24DD0136", "unknown", "official_artifact", ("DAGATAN",)),
            "evidence type",
        ),
        (
            EvidenceBinding("24DD0136", "procurement_plan", "unknown", ("DAGATAN",)),
            "evidence class",
        ),
        (
            EvidenceBinding("24DD0136", "procurement_plan", "official_artifact", ()),
            "identity terms",
        ),
        (
            EvidenceBinding("24DD0136", "procurement_plan", "identity_conflict", ("DAGATAN",)),
            "limitation",
        ),
    ],
)
def test_rejects_invalid_bindings(binding: EvidenceBinding, message: str) -> None:
    document = _document("24DD0136 24DD0137 DAGATAN", (binding,))
    with pytest.raises(ProcurementEvidenceError, match=message):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (document,),
            expected_contract_ids=("24DD0136",),
        )


def test_rejects_contract_set_and_source_identity_errors() -> None:
    binding = EvidenceBinding(
        "24DD0136", "procurement_plan", "official_artifact", ("DAGATAN",)
    )
    document = _document("24DD0136 DAGATAN", (binding,))
    with pytest.raises(ProcurementEvidenceError, match="unique and non-empty"):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (document,),
            expected_contract_ids=("24DD0136", "24DD0136"),
        )
    with pytest.raises(ProcurementEvidenceError, match="candidate descriptions"):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (document,),
            expected_contract_ids=("24DD0136", "24CD0251"),
        )
    with pytest.raises(ProcurementEvidenceError, match="duplicate official source"):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (document, document),
            expected_contract_ids=("24DD0136",),
        )


def test_rejects_document_without_bound_contract_id() -> None:
    binding = EvidenceBinding(
        "24DD0136", "procurement_plan", "official_artifact", ("DAGATAN",)
    )
    with pytest.raises(ProcurementEvidenceError, match="does not contain"):
        reconcile_official_documents(
            {"24DD0136": "DAGATAN"},
            (_document("DAGATAN only", (binding,)),),
            expected_contract_ids=("24DD0136",),
        )
