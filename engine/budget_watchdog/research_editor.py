"""Generic fail-closed editor and package writer for Busisi research releases."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.budget_watchdog.research_sources import validate_release_evidence

BASE_PAYLOADS = {
    "chart-data.json": "chart_data",
    "claims.json": "claims",
    "findings.json": "findings",
    "investigations.json": "investigations",
    "limitations.json": "limitations",
    "project-examples.json": "project_examples",
    "sources.json": "sources",
}
EDITORIAL_PAYLOADS = {
    "editorial-package.json": "editorial_package",
    "story.json": "story",
}
PUBLISHABLE_STATES = frozenset({"verified", "source_reported"})
ALL_STATES = PUBLISHABLE_STATES | frozenset(
    {"review_candidate", "unresolved", "not_supported"}
)
SHA256 = re.compile(r"[a-f0-9]{64}")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _iso_date(value: object, label: str) -> date:
    text = _required_text(value, label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _metadata(release: dict[str, Any]) -> dict[str, Any]:
    value = release.get("metadata")
    if not isinstance(value, dict):
        raise ValueError("release metadata must be an object")
    for field in ("story_id", "slug", "headline", "canonical_url", "methodology_version"):
        _required_text(value.get(field), f"metadata {field}")
    if value.get("status") != "published":
        raise ValueError("release status must be published")
    if not isinstance(value.get("version"), int) or value["version"] < 1:
        raise ValueError("release version must be a positive integer")
    parsed = urlparse(value["canonical_url"])
    if parsed.scheme != "https" or parsed.hostname != "busisi.org":
        raise ValueError("canonical_url must use the Busisi HTTPS origin")
    digest = value.get("source_artifact_sha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise ValueError("source_artifact_sha256 must be a SHA-256 digest")
    _iso_date(value.get("published_at"), "published_at")
    _iso_date(value.get("data_cutoff"), "data_cutoff")
    return value


def _validate_freshness(metadata: dict[str, Any]) -> None:
    if metadata.get("schema_version") != "1.1":
        return
    checked = _iso_date(metadata.get("source_checked_at"), "source_checked_at")
    published = _iso_date(metadata.get("published_at"), "published_at")
    cutoff = _iso_date(metadata.get("data_cutoff"), "data_cutoff")
    maximum = metadata.get("max_source_age_days")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
        raise ValueError("max_source_age_days must be a non-negative integer")
    if checked < cutoff or checked > published or (published - checked).days > maximum:
        raise ValueError("source check is stale or inconsistent with the publication date")
    if metadata.get("editorial_ready") is not True:
        raise ValueError("schema 1.1 release must be editorial ready")


def _claim_index(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    claims = release.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims must contain at least one claim")
    indexed: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("each claim must be an object")
        claim_id = _required_text(claim.get("id"), "claim id")
        if claim_id in indexed:
            raise ValueError(f"duplicate claim id: {claim_id}")
        _required_text(claim.get("statement"), f"claim {claim_id} statement")
        if claim.get("evidence_state") not in ALL_STATES:
            raise ValueError(f"claim {claim_id} has an unsupported evidence state")
        indexed[claim_id] = claim
    return indexed


def _limitation_ids(release: dict[str, Any], *, required: bool) -> set[str]:
    values = release.get("limitations")
    if not isinstance(values, list) or not values:
        raise ValueError("limitations must contain at least one item")
    if not required:
        return set()
    identifiers: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("schema 1.1 limitations must be identified objects")
        identifier = _required_text(item.get("id"), "limitation id")
        _required_text(item.get("text"), f"limitation {identifier} text")
        if identifier in identifiers:
            raise ValueError(f"duplicate limitation id: {identifier}")
        identifiers.add(identifier)
    return identifiers


def _validate_findings(release: dict[str, Any], claims: set[str]) -> None:
    findings = release.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("each finding must be an object")
        unknown = set(finding.get("claim_ids", [])) - claims
        if unknown:
            raise ValueError(f"finding references unknown claims: {sorted(unknown)}")


def _validate_story_section(
    section: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    sources: set[str],
    limitations: set[str],
) -> None:
    copy = section.get("copy")
    if not isinstance(copy, list) or not copy or not all(
        isinstance(item, str) and item.strip() for item in copy
    ):
        raise ValueError("story section copy must contain non-empty text")
    claim_ids = section.get("claim_ids")
    if not isinstance(claim_ids, list) or not claim_ids:
        raise ValueError("story section must identify at least one claim")
    unknown = set(claim_ids) - claims.keys()
    if unknown:
        raise ValueError(f"story section references unknown claims: {sorted(unknown)}")
    if set(section.get("source_ids", [])) - sources:
        raise ValueError("story section references an unknown source")
    if set(section.get("limitation_ids", [])) - limitations:
        raise ValueError("story section references an unknown limitation")
    roots = {str(item).partition(".")[0] for item in section.get("visual_refs", [])}
    if roots - {"chart_data", "project_examples"}:
        raise ValueError("story section visual reference is outside the public package")
    held = [claim_id for claim_id in claim_ids if claims[claim_id]["evidence_state"] not in PUBLISHABLE_STATES]
    if section.get("narration_eligible") and held:
        raise ValueError("review candidate cannot be eligible for factual narration")
    if held and (section.get("section_type") != "investigation_lead" or not section.get("limitation_ids")):
        raise ValueError("review candidate must remain a limited investigation lead")


def _validate_story(
    release: dict[str, Any], metadata: dict[str, Any], claims: dict[str, dict[str, Any]]
) -> None:
    story = release.get("story")
    if not isinstance(story, dict) or story.get("editorial_status") != "ready":
        raise ValueError("editorial story must be ready")
    if story.get("story_id") != metadata["story_id"] or story.get("version") != metadata["version"]:
        raise ValueError("story identity must match release metadata")
    sources = {item["id"] for item in release["sources"]}
    limitations = _limitation_ids(release, required=True)
    sections = story.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("editorial story must contain ordered sections")
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("story sections must be objects")
        _validate_story_section(section, claims, sources, limitations)


def _package_base(metadata: dict[str, Any]) -> str:
    return (
        f"https://busisi.org/data/research/{metadata['slug']}/"
        f"v{metadata['version']}"
    )


def build_consumption_index(
    metadata: dict[str, Any], sources: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build absolute, immutable links for a downstream editorial consumer."""

    base = _package_base(metadata)
    files = {
        field: f"{base}/{path}"
        for path, field in BASE_PAYLOADS.items()
    }
    return {
        "schema_version": "1.0",
        "story_id": metadata["story_id"],
        "version": metadata["version"],
        "status": "ready_for_consumption",
        "canonical_article_url": metadata["canonical_url"],
        "api_url": f"https://busisi.org/api/v1/research/{metadata['slug']}",
        "package_base_url": base,
        "manifest_url": f"{base}/manifest.json",
        "story_url": f"{base}/story.json",
        "files": files,
        "direct_source_urls": [item["source_url"] for item in sources],
        "integrity": {
            "method": "sha256-manifest",
            "instruction": "Verify every downloaded file against manifest.json before use.",
        },
        "evidence_boundary": "Only verified and source-reported claims are eligible for factual narration. Investigation leads must retain their limitations.",
        "attribution": "Busisi, built and maintained by Auva Labs. Source publishers remain identified in sources.json.",
        "contact": "dev@auvalabs.com",
    }


def _validate_consumption_index(release: dict[str, Any], metadata: dict[str, Any]) -> None:
    package = release.get("editorial_package")
    if not isinstance(package, dict) or package.get("status") != "ready_for_consumption":
        raise ValueError("release requires a ready consumption index")
    expected = build_consumption_index(metadata, release["sources"])
    for field in (
        "story_id", "version", "canonical_article_url", "api_url", "package_base_url",
        "manifest_url", "story_url", "files", "direct_source_urls",
    ):
        if package.get(field) != expected[field]:
            if field == "files":
                raise ValueError("consumption index must link every release data file")
            raise ValueError(f"consumption index {field} does not match the release")


def validate_research_release(release: dict[str, Any]) -> None:
    """Validate a release before any public bytes are written."""

    metadata = _metadata(release)
    _validate_freshness(metadata)
    validate_release_evidence(release)
    claims = _claim_index(release)
    _validate_findings(release, set(claims))
    has_story = "story" in release or "editorial_package" in release
    if has_story and not ({"story", "editorial_package"} <= release.keys()):
        raise ValueError("story and consumption index must be published together")
    _limitation_ids(
        release,
        required=metadata.get("schema_version") == "1.1" or has_story,
    )
    if metadata.get("schema_version") == "1.1" or has_story:
        _validate_story(release, metadata, claims)
        _validate_consumption_index(release, metadata)


def _payload_map(release: dict[str, Any]) -> dict[str, object]:
    mapping = dict(BASE_PAYLOADS)
    if "story" in release and "editorial_package" in release:
        mapping.update(EDITORIAL_PAYLOADS)
    return {path: release[field] for path, field in mapping.items()}


def write_research_release(release: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write one immutable package and authenticate every public payload."""

    validate_research_release(release)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise FileExistsError("research package output must be empty")
    files = []
    for path, value in sorted(_payload_map(release).items()):
        payload = _json_bytes(value)
        (output_dir / path).write_bytes(payload)
        files.append(
            {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        )
    identity = "".join(f"{item['path']}\0{item['sha256']}\n" for item in files).encode()
    manifest = {
        **release["metadata"],
        "files": files,
        "package_sha256": hashlib.sha256(identity).hexdigest(),
    }
    (output_dir / "manifest.json").write_bytes(_json_bytes(manifest))
    verify_published_package(output_dir)
    return manifest


def verify_published_package(package_dir: Path) -> dict[str, Any]:
    """Rebuild and validate a release contract only from its published files."""

    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("published package manifest is missing")
    manifest = json.loads(manifest_path.read_bytes())
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("published package manifest has no files")
    payloads: dict[str, Any] = {}
    identity = []
    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or Path(path).name != path:
            raise ValueError("manifest contains an unsafe file path")
        payload = (package_dir / path).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != entry.get("bytes") or digest != entry.get("sha256"):
            raise ValueError(f"published package file failed authentication: {path}")
        payloads[path] = json.loads(payload)
        identity.append(f"{path}\0{digest}\n")
    package_sha256 = hashlib.sha256("".join(identity).encode()).hexdigest()
    if package_sha256 != manifest.get("package_sha256"):
        raise ValueError("published package digest does not match its files")
    metadata = {key: value for key, value in manifest.items() if key not in {"files", "package_sha256"}}
    mapping = {**BASE_PAYLOADS, **EDITORIAL_PAYLOADS}
    release = {"metadata": metadata, **{field: payloads[path] for path, field in mapping.items() if path in payloads}}
    validate_research_release(release)
    return manifest
