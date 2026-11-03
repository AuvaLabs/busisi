"""Validated source registry with explicit evidentiary authority."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlparse


class SourceRegistryError(ValueError):
    """Raised when source configuration is unsafe or ambiguous."""


class SourceAuthority(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_id: str
    name: str
    base_url: str
    authority: SourceAuthority

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.replace("-", "").isalnum():
            raise SourceRegistryError("source_id must contain letters, numbers, or hyphens")
        if not self.name.strip():
            raise SourceRegistryError("source name must not be empty")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SourceRegistryError("source base URL must use HTTPS")
        if parsed.username or parsed.password:
            raise SourceRegistryError("source base URL must not contain credentials")


class SourceRegistry:
    def __init__(self, sources: tuple[SourceDefinition, ...]) -> None:
        by_id: dict[str, SourceDefinition] = {}
        for source in sources:
            if source.source_id in by_id:
                raise SourceRegistryError(f"duplicate source_id: {source.source_id}")
            by_id[source.source_id] = source
        if not by_id:
            raise SourceRegistryError("source registry must not be empty")
        self._sources = MappingProxyType(by_id)

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise SourceRegistryError(f"unknown source_id: {source_id}") from exc

    def all(self) -> tuple[SourceDefinition, ...]:
        return tuple(self._sources.values())


def default_source_registry() -> SourceRegistry:
    return SourceRegistry(
        (
            SourceDefinition(
                "dbm-gaa",
                "Department of Budget and Management GAA",
                "https://www.dbm.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dbm-nep",
                "Department of Budget and Management NEP",
                "https://www.dbm.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dbm-saaodb",
                "Department of Budget and Management SAAODB",
                "https://www.dbm.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dbm-compass",
                "DBM COMPASS",
                "https://compass.dbm.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dpwh-projects",
                "DPWH Transparency Portal",
                "https://civic.transparency.dpwh.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dpwh-transparency-media",
                "DPWH Transparency project media",
                "https://s3.transparency.dpwh.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dpwh-infratrack-media",
                "DPWH Infratrack project media proxy",
                "https://apps2.dpwh.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dpwh-documents",
                "DPWH public documents",
                "https://www.dpwh.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "dpwh-documents-apex",
                "DPWH public documents apex host",
                "https://dpwh.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "philgeps",
                "PhilGEPS Open Data",
                "https://open.philgeps.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "pcab",
                "PCAB License Verification",
                "https://pcab.construction.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "coa",
                "Commission on Audit eLibrary",
                "https://elibrary.coa.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "senate-budget-portal",
                "Senate Budget Transparency Portal",
                "https://budget-transparency-portal.senate.gov.ph",
                SourceAuthority.PRIMARY,
            ),
            SourceDefinition(
                "bettergov-budget",
                "BetterGov Budget API",
                "https://budget.bettergov.ph",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-dpwh",
                "BetterGov DPWH API",
                "https://api.dpwh.bettergov.ph",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-budget-assets",
                "BetterGov Budget Document Mirror",
                "https://budget-assets.bettergov.ph",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-analysis-github",
                "BetterGov Budget Analysis GitHub Mirror",
                "https://raw.githubusercontent.com",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-gaa-snapshot",
                "BetterGov GAA Parquet Snapshot",
                "https://huggingface.co",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-dpwh-snapshot",
                "BetterGov DPWH Parquet Snapshot",
                "https://huggingface.co",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "bettergov-philgeps-snapshot",
                "BetterGov PhilGEPS Parquet Snapshot",
                "https://huggingface.co",
                SourceAuthority.SECONDARY,
            ),
            SourceDefinition(
                "jina-reader",
                "Jina Reader rendered-page discovery",
                "https://r.jina.ai",
                SourceAuthority.SECONDARY,
            ),
        )
    )
