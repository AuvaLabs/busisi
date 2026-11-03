"""Conservative project-family identities for cross-year comparison."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass

COORDINATE_PAIR = re.compile(r"\(?\s*-?\d{1,3}\.\d+\s*[,/]\s*-?\d{1,3}\.\d+\s*\)?")
PHASE_MARKER = re.compile(r"\bphase\s*(?:[0-9]+|[ivx]+)\b", re.IGNORECASE)
COMPLETION_MARKER = re.compile(r"\b(?:completion|completed)\b", re.IGNORECASE)
NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
ACTION_MARKER = re.compile(
    r"\b(?:construction|rehabilitation|repair|improvement)\b",
    re.IGNORECASE,
)
PROGRAM_MARKER = re.compile(r"\b(?:program|cssp|bip)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProjectFamilyIdentity:
    family_id: str
    canonical_text: str


def build_family_identity(description: str) -> ProjectFamilyIdentity:
    """Remove phase markers while retaining asset type and location evidence."""

    if not description or not description.strip():
        raise ValueError("description must not be empty")
    action = ACTION_MARKER.search(description)
    prefix = description[: action.start()] if action is not None else ""
    without_program_prefix = (
        description[action.start() :]
        if action is not None and PROGRAM_MARKER.search(prefix)
        else description
    )
    without_coordinates = COORDINATE_PAIR.sub(" ", without_program_prefix)
    without_phase = PHASE_MARKER.sub(" ", without_coordinates)
    without_completion = COMPLETION_MARKER.sub(" ", without_phase)
    normalized = unicodedata.normalize("NFKD", without_completion.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    canonical = NON_ALPHANUMERIC.sub(" ", ascii_text).strip()
    canonical = " ".join(canonical.split())
    if not canonical:
        raise ValueError("description has no canonical text")
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return ProjectFamilyIdentity(family_id=f"family:{digest}", canonical_text=canonical)
