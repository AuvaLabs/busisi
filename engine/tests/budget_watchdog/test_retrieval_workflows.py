import hashlib
import json
from dataclasses import replace

import pytest

from engine.budget_watchdog.evidence_catalog import build_evidence_index
from engine.budget_watchdog.evidence_retrieval import lexical_search
from engine.budget_watchdog.research_evidence import (
    build_research_evidence_packet,
    passage_payload,
    write_research_evidence_packet,
)
from engine.budget_watchdog.review_council import (
    attach_document_evidence,
    packet_sha256,
)


def _result(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Construction of a public hospital in Sample City", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "documents": [
                    {
                        "document_id": "health-budget",
                        "title": "Health Facilities Budget",
                        "publisher": "DBM",
                        "source_url": "https://www.dbm.gov.ph/health-budget",
                        "artifact_path": source.name,
                        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "media_type": "text/plain",
                        "fiscal_year": 2027,
                        "stage": "nep",
                        "agency": "DOH",
                    }
                ],
            }
        )
    )
    index = build_evidence_index(manifest, tmp_path / "index.sqlite3")
    result = lexical_search(index.database_path, "hospital Sample City", limit=3)[0]
    return index, result


def test_council_receives_one_immutable_cited_packet(tmp_path) -> None:
    index, result = _result(tmp_path)
    base = {"schema_version": 2, "case_id": "case-1", "question": "Same work?"}

    packet = attach_document_evidence(
        base,
        query="hospital Sample City",
        results=(result,),
        index_manifest_sha256=index.manifest_sha256,
    )

    assert packet["schema_version"] == 3
    passage = packet["document_evidence"]["passages"][0]
    assert passage["document_id"] == "health-budget"
    assert passage["page_start"] == 1
    assert len(passage["artifact_sha256"]) == 64
    assert len(packet_sha256(packet)) == 64
    assert base == {"schema_version": 2, "case_id": "case-1", "question": "Same work?"}


def test_council_document_evidence_validates_packet_query_and_index(tmp_path) -> None:
    index, result = _result(tmp_path)
    valid = {"schema_version": 2, "case_id": "case-1"}
    for packet, query, digest, message in (
        ({"schema_version": 1}, "question", index.manifest_sha256, "base council"),
        (valid, "", index.manifest_sha256, "query"),
        (valid, "question", "bad", "manifest"),
    ):
        with pytest.raises(ValueError, match=message):
            attach_document_evidence(
                packet,
                query=query,
                results=(result,),
                index_manifest_sha256=digest,
            )


def test_research_packet_keeps_retrieval_as_a_lead_until_review(tmp_path) -> None:
    index, result = _result(tmp_path)

    packet = build_research_evidence_packet(
        story_id="hospital-value",
        question="Where is hospital construction funded?",
        results=(result,),
        index_manifest_sha256=index.manifest_sha256,
    )

    assert packet["status"] == "needs_editor_review"
    assert packet["passages"][0]["evidence_state"] == "review_candidate"
    assert packet["passages"][0]["source_url"].startswith("https://")
    assert "does not verify" in packet["limits"][0].lower()

    output = tmp_path / "private" / "packet.json"
    digest = write_research_evidence_packet(packet, output)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest


def test_research_packet_rejects_invalid_identity_and_state(tmp_path) -> None:
    index, result = _result(tmp_path)
    with pytest.raises(ValueError, match="story_id"):
        build_research_evidence_packet(
            story_id="",
            question="question",
            results=(result,),
            index_manifest_sha256=index.manifest_sha256,
        )
    with pytest.raises(ValueError, match="manifest"):
        build_research_evidence_packet(
            story_id="story",
            question="question",
            results=(result,),
            index_manifest_sha256="bad",
        )
    with pytest.raises(ValueError, match="artifact"):
        passage_payload(replace(result, artifact_sha256="bad"))
    with pytest.raises(ValueError, match="chunk"):
        passage_payload(replace(result, chunk_sha256="bad"))
    with pytest.raises(ValueError, match="editor-review"):
        write_research_evidence_packet({"status": "published"}, tmp_path / "bad.json")
