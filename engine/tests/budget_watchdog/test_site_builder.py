from pathlib import Path

from engine.budget_watchdog.site_builder import build_site, validate_site

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "ops" / "harness" / "fixtures" / "budget_watchdog_golden.json"
PAGE_COUNT = 9
PROJECT_PAGE_COUNT = 6


def test_site_builder_writes_watchlist_and_every_dossier(tmp_path) -> None:
    result = build_site(GOLDEN_PATH, tmp_path)

    assert result.pages_written == PAGE_COUNT
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "watchlist" / "index.html").is_file()
    assert (tmp_path / "methodology" / "index.html").is_file()
    assert len(tuple((tmp_path / "projects").glob("*/index.html"))) == PROJECT_PAGE_COUNT
    assert (tmp_path / "assets" / "site.css").is_file()
    assert (tmp_path / "assets" / "site.js").is_file()


def test_rendered_pages_keep_evidence_and_release_caveats_visible(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)
    watchlist = (tmp_path / "watchlist" / "index.html").read_text(encoding="utf-8")
    project = (tmp_path / "projects" / "corazon-2026-completion" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "6 of 100 reviewed cases" in watchlist
    assert "Not approved for public release" in watchlist
    assert "not evidence of wrongdoing" in watchlist
    assert "Quarantined candidate" in project
    assert "https://budget.bettergov.ph/" in project
    assert "https://api.dpwh.bettergov.ph/projects/26HI0094" in project


def test_site_has_distinct_identity_and_data_controls(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    watchlist = (tmp_path / "watchlist" / "index.html").read_text(encoding="utf-8")

    assert '<span class="brand-name">Busisi</span>' in home
    assert "Suriin ang pondo. Sundan ang proyekto." in home
    assert "data-year-filter" in watchlist
    assert "data-sort" in watchlist
    assert "data-export" in watchlist
    assert "data-reset" in watchlist
    assert 'aria-live="polite"' in watchlist
    assert 'data-year="2026"' in watchlist
    assert 'data-appropriation="2500000000"' in watchlist


def test_site_route_harness_resolves_internal_links(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)

    report = validate_site(tmp_path)

    assert report.pages_checked == PAGE_COUNT
    assert report.missing_routes == ()
    assert report.pages_missing_viewport == ()
    assert report.pages_missing_main_landmark == ()


def test_site_assets_preserve_filtered_hidden_state(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)

    stylesheet = (tmp_path / "assets" / "site.css").read_text(encoding="utf-8")

    assert "[hidden] { display: none !important; }" in stylesheet


def test_site_assets_use_accessible_sans_typography_on_white(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)

    stylesheet = (tmp_path / "assets" / "site.css").read_text(encoding="utf-8")

    assert "--paper: #fff;" in stylesheet
    assert "--text-xs: .8125rem;" in stylesheet
    assert "Georgia" not in stylesheet
    assert "Times New Roman" not in stylesheet
    assert "font-size: var(--text-md);" in stylesheet
    assert "@media (prefers-contrast: more)" in stylesheet


def test_site_interactions_preserve_url_state_and_filtered_export(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)

    script = (tmp_path / "assets" / "site.js").read_text(encoding="utf-8")

    assert "new URLSearchParams(location.search)" in script
    assert "history.replaceState" in script
    assert "data:text/csv" in script
    assert "visibleRows()" in script


def test_watchlist_progressively_hydrates_from_publication_api(tmp_path) -> None:
    build_site(GOLDEN_PATH, tmp_path)
    watchlist = (tmp_path / "watchlist" / "index.html").read_text(encoding="utf-8")
    script = (tmp_path / "assets" / "site.js").read_text(encoding="utf-8")

    assert "data-load-more" in watchlist
    assert "data-source-status" in watchlist
    assert "fetch(`/api/v1/projects?" in script
    assert "/api/v1/projects.csv" in script
    assert "document.createElement" in script
    assert ".innerHTML" not in script
