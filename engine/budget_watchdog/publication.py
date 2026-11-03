"""Reviewed publication views for the local budget-watchdog preview."""

from dataclasses import dataclass
from pathlib import Path

from engine.budget_watchdog.family import build_family_identity
from engine.budget_watchdog.flags import MINIMUM_REPEATED_FUNDING_YEARS
from engine.budget_watchdog.golden import (
    MINIMUM_GOLDEN_CASES,
    GoldenCase,
    evaluate_golden_cases,
    load_golden_cases,
)
from engine.budget_watchdog.identity import match_candidates


@dataclass(frozen=True, slots=True)
class ReleaseGateView:
    reviewed_cases: int
    required_cases: int
    passed_cases: int
    agreement_percent: str
    release_ready: bool


@dataclass(frozen=True, slots=True)
class ProjectDossierView:
    case_id: str
    slug: str
    title: str
    fiscal_year: int
    location: str
    appropriation_centavos: int
    contract_budget_centavos: int
    variance_centavos: int
    contract_id: str
    delivery_title: str
    implementing_office: str
    source_of_funds: str
    confidence: str
    confidence_score: int
    match_signals: tuple[str, ...]
    match_limitations: str
    evidence_urls: tuple[str, ...]
    family_id: str
    family_label: str
    status_label: str
    is_confirmed_link: bool
    is_quarantined: bool


@dataclass(frozen=True, slots=True)
class WatchlistItemView:
    code: str
    summary: str
    family_id: str
    family_label: str
    years: tuple[int, ...]
    amounts_centavos: tuple[int, ...]
    dossier_slugs: tuple[str, ...]
    limitations: str


@dataclass(frozen=True, slots=True)
class PublicationView:
    release_gate: ReleaseGateView
    dossiers: tuple[ProjectDossierView, ...]
    watchlist: tuple[WatchlistItemView, ...]
    available_years: tuple[int, ...]
    total_appropriation_centavos: int
    total_contract_budget_centavos: int


def _dossier(case: GoldenCase) -> ProjectDossierView:
    decision = match_candidates(case.budget, case.candidates)
    candidate = case.candidates[0]
    top_score = decision.candidates[0] if decision.candidates else None
    confirmed = decision.selected_contract_id is not None
    family = build_family_identity(case.budget.description)
    return ProjectDossierView(
        case_id=case.case_id,
        slug=case.case_id,
        title=case.budget.description,
        fiscal_year=case.budget.fiscal_year,
        location=case.budget.location or candidate.location,
        appropriation_centavos=case.budget.amount_centavos,
        contract_budget_centavos=candidate.budget_centavos,
        variance_centavos=case.budget.amount_centavos - candidate.budget_centavos,
        contract_id=candidate.contract_id,
        delivery_title=candidate.description,
        implementing_office=candidate.location,
        source_of_funds=candidate.source_of_funds,
        confidence=decision.confidence.value,
        confidence_score=top_score.score if top_score else 0,
        match_signals=top_score.signals if top_score else (),
        match_limitations=decision.limitations,
        evidence_urls=case.evidence_urls,
        family_id=family.family_id,
        family_label=family.canonical_text,
        status_label="Reviewed link" if confirmed else "Quarantined candidate",
        is_confirmed_link=confirmed,
        is_quarantined=not confirmed,
    )


def _watchlist(dossiers: tuple[ProjectDossierView, ...]) -> tuple[WatchlistItemView, ...]:
    families: dict[str, list[ProjectDossierView]] = {}
    for dossier in dossiers:
        if dossier.is_confirmed_link:
            families.setdefault(dossier.family_id, []).append(dossier)
    items = [_repeated_funding_item(records) for records in families.values()]
    return tuple(item for item in items if item is not None)


def _repeated_funding_item(
    records: list[ProjectDossierView],
) -> WatchlistItemView | None:
    years = sorted({record.fiscal_year for record in records})
    if len(years) < MINIMUM_REPEATED_FUNDING_YEARS:
        return None
    ordered = sorted(records, key=lambda record: (record.fiscal_year, record.case_id))
    amounts = tuple(
        sum(record.appropriation_centavos for record in ordered if record.fiscal_year == year)
        for year in years
    )
    return WatchlistItemView(
        code="repeated_positive_funding",
        summary="A related project family has positive appropriations in multiple years.",
        family_id=ordered[0].family_id,
        family_label=ordered[0].family_label,
        years=tuple(years),
        amounts_centavos=amounts,
        dossier_slugs=tuple(record.slug for record in ordered),
        limitations=(
            "This family can contain separate phases, contracts, or physical assets. "
            "Repeated funding is a review lead, not evidence of wrongdoing."
        ),
    )


def build_publication(golden_path: Path) -> PublicationView:
    cases = load_golden_cases(golden_path)
    summary = evaluate_golden_cases(cases)
    dossiers = tuple(_dossier(case) for case in cases)
    gate = ReleaseGateView(
        reviewed_cases=summary.total,
        required_cases=MINIMUM_GOLDEN_CASES,
        passed_cases=summary.passed,
        agreement_percent=f"{summary.agreement * 100:.0f}%",
        release_ready=summary.release_ready,
    )
    return PublicationView(
        release_gate=gate,
        dossiers=dossiers,
        watchlist=_watchlist(dossiers),
        available_years=tuple(sorted({dossier.fiscal_year for dossier in dossiers})),
        total_appropriation_centavos=sum(dossier.appropriation_centavos for dossier in dossiers),
        total_contract_budget_centavos=sum(
            dossier.contract_budget_centavos for dossier in dossiers
        ),
    )
