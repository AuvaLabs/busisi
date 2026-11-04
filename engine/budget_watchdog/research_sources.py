"""Evidence-source validation for public Busisi research releases."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

ALLOWED_SOURCE_KINDS = frozenset(
    {
        "official_record",
        "official_dataset",
        "curated_official_extract",
        "academic_research",
        "established_news",
        "civil_society_research",
    }
)
PRIMARY_SOURCE_KINDS = frozenset(
    {"official_record", "official_dataset", "curated_official_extract"}
)
DIRECT_EVIDENCE_STATES = frozenset({"verified", "source_reported"})
DISCOVERY_HOSTS = frozenset(
    {
        "api.exa.ai",
        "exa.ai",
        "www.exa.ai",
        "perplexity.ai",
        "www.perplexity.ai",
    }
)


class ResearchEvidenceError(ValueError):
    """Raised when a public release lacks traceable evidence."""


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchEvidenceError(f"{label} must be non-empty text")
    return value.strip()


def _https_url(value: object, label: str) -> str:
    url = _required_text(value, label)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ResearchEvidenceError(f"{label} must be a direct HTTPS URL")
    if parsed.hostname.casefold() in DISCOVERY_HOSTS:
        raise ResearchEvidenceError(f"{label} cannot identify a discovery service")
    return url


def _source_index(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ResearchEvidenceError("sources must contain at least one source")
    sources: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ResearchEvidenceError("each source must be an object")
        source_id = _required_text(item.get("id"), "source id")
        if source_id in sources:
            raise ResearchEvidenceError(f"duplicate source id: {source_id}")
        source_kind = _required_text(item.get("source_kind"), f"source {source_id} source_kind")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise ResearchEvidenceError(
                f"source {source_id} source_kind is not allowed: {source_kind}"
            )
        _required_text(item.get("publisher"), f"source {source_id} publisher")
        _required_text(item.get("access_provider"), f"source {source_id} access_provider")
        _https_url(item.get("source_url"), f"source {source_id} source_url")
        origin_url = item.get("origin_url")
        if origin_url is not None:
            _https_url(origin_url, f"source {source_id} origin_url")
        retrieved_at = _required_text(item.get("retrieved_at"), f"source {source_id} retrieved_at")
        try:
            date.fromisoformat(retrieved_at)
        except ValueError as exc:
            raise ResearchEvidenceError(
                f"source {source_id} retrieved_at must be an ISO date"
            ) from exc
        digest = _required_text(item.get("sha256"), f"source {source_id} sha256")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ResearchEvidenceError(f"source {source_id} sha256 is invalid")
        sources[source_id] = item
    return sources


def validate_release_evidence(release: dict[str, Any]) -> None:
    """Require every claim to resolve to archived, direct source evidence.

    Exa and Perplexity may discover a document during private research, but the
    document's publisher and direct URL must be recorded here instead of the
    discovery service.
    """

    sources = _source_index(release.get("sources"))
    claims = release.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ResearchEvidenceError("claims must contain at least one claim")
    for item in claims:
        if not isinstance(item, dict):
            raise ResearchEvidenceError("each claim must be an object")
        claim_id = _required_text(item.get("id"), "claim id")
        source_ids = item.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ResearchEvidenceError(f"claim {claim_id} must identify its sources")
        if not all(isinstance(source_id, str) and source_id for source_id in source_ids):
            raise ResearchEvidenceError(f"claim {claim_id} source_ids must be text")
        unknown = sorted(set(source_ids) - sources.keys())
        if unknown:
            raise ResearchEvidenceError(
                f"claim {claim_id} references an unknown source: {', '.join(unknown)}"
            )
        if item.get("evidence_state") in DIRECT_EVIDENCE_STATES and not any(
            sources[source_id]["source_kind"] in PRIMARY_SOURCE_KINDS for source_id in source_ids
        ):
            raise ResearchEvidenceError(
                f"claim {claim_id} needs an official or curated official source"
            )
