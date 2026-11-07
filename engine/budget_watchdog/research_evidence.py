"""Private retrieval packets for the Busisi research and editorial workflow."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from engine.budget_watchdog.evidence_retrieval import RetrievalResult

SHA256 = re.compile(r"[a-f0-9]{64}")


def passage_payload(result: RetrievalResult) -> dict[str, Any]:
    if SHA256.fullmatch(result.artifact_sha256) is None:
        raise ValueError("retrieved passage has an invalid artifact SHA-256")
    if SHA256.fullmatch(result.chunk_sha256) is None:
        raise ValueError("retrieved passage has an invalid chunk SHA-256")
    return {
        "chunk_id": result.chunk_id,
        "document_id": result.document_id,
        "title": result.title,
        "publisher": result.publisher,
        "source_url": result.source_url,
        "artifact_sha256": result.artifact_sha256,
        "page_start": result.page_start,
        "page_end": result.page_end,
        "text": result.text,
        "chunk_sha256": result.chunk_sha256,
        "evidence_kinds": list(result.evidence_kinds),
        "retrieval_modes": list(result.retrieval_modes),
    }


def build_research_evidence_packet(
    *,
    story_id: str,
    question: str,
    results: tuple[RetrievalResult, ...],
    index_manifest_sha256: str,
) -> dict[str, Any]:
    """Prepare cited leads without promoting retrieved text into verified claims."""

    if not story_id.strip() or not question.strip():
        raise ValueError("story_id and question are required")
    if SHA256.fullmatch(index_manifest_sha256) is None:
        raise ValueError("index manifest SHA-256 is invalid")
    passages = [
        {**passage_payload(result), "evidence_state": "review_candidate"}
        for result in results
    ]
    return {
        "schema_version": 1,
        "story_id": story_id.strip(),
        "question": question.strip(),
        "status": "needs_editor_review",
        "index_manifest_sha256": index_manifest_sha256,
        "passages": passages,
        "limits": [
            "A retrieved passage does not verify a claim by itself.",
            "An editor must read the cited page and check the archived source before publication.",
            "Missing search results do not prove that no record exists.",
        ],
    }


def write_research_evidence_packet(packet: dict[str, Any], output_path: Path) -> str:
    """Write a private packet and return its content digest."""

    if packet.get("status") != "needs_editor_review":
        raise ValueError("only editor-review packets may enter the research workflow")
    payload = (json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
