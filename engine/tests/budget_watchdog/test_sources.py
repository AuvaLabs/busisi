import pytest

from engine.budget_watchdog.sources import (
    SourceAuthority,
    SourceDefinition,
    SourceRegistry,
    SourceRegistryError,
    default_source_registry,
)


def test_default_registry_distinguishes_primary_and_secondary_sources() -> None:
    registry = default_source_registry()

    assert registry.get("dbm-gaa").authority is SourceAuthority.PRIMARY
    assert registry.get("dpwh-projects").authority is SourceAuthority.PRIMARY
    assert registry.get("bettergov-budget").authority is SourceAuthority.SECONDARY
    assert registry.get("bettergov-dpwh").authority is SourceAuthority.SECONDARY
    assert registry.get("dpwh-transparency-media").authority is SourceAuthority.PRIMARY
    assert registry.get("dpwh-infratrack-media").authority is SourceAuthority.PRIMARY
    assert registry.get("bettergov-budget-assets").authority is SourceAuthority.SECONDARY
    assert registry.get("bettergov-analysis-github").authority is SourceAuthority.SECONDARY
    assert registry.get("bettergov-gaa-snapshot").authority is SourceAuthority.SECONDARY
    assert registry.get("bettergov-dpwh-snapshot").authority is SourceAuthority.SECONDARY
    assert registry.get("senate-budget-portal").authority is SourceAuthority.PRIMARY
    assert registry.get("jina-reader").authority is SourceAuthority.SECONDARY


def test_registry_rejects_duplicate_ids_and_non_https_urls() -> None:
    source = SourceDefinition(
        source_id="duplicate",
        name="Example",
        base_url="https://example.gov.ph",
        authority=SourceAuthority.PRIMARY,
    )
    with pytest.raises(SourceRegistryError, match="duplicate"):
        SourceRegistry((source, source))

    with pytest.raises(SourceRegistryError, match="HTTPS"):
        SourceDefinition(
            source_id="insecure",
            name="Insecure",
            base_url="http://example.gov.ph",
            authority=SourceAuthority.PRIMARY,
        )
