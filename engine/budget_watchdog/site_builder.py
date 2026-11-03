"""Build and validate the isolated static budget-watchdog preview."""

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from shutil import copyfile
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from engine.budget_watchdog.publication import PublicationView, build_publication

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = PACKAGE_ROOT / "site_templates"
ASSET_ROOT = PACKAGE_ROOT / "site_assets"


@dataclass(frozen=True, slots=True)
class SiteBuildResult:
    output_dir: Path
    pages_written: int
    project_pages: int


@dataclass(frozen=True, slots=True)
class SiteValidationReport:
    pages_checked: int
    missing_routes: tuple[str, ...]
    pages_missing_viewport: tuple[str, ...]
    pages_missing_main_landmark: tuple[str, ...]


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.has_viewport = False
        self.has_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")
        if tag == "meta" and attributes.get("name") == "viewport":
            self.has_viewport = True
        if tag == "main":
            self.has_main = True


def _environment() -> Environment:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_ROOT),
        autoescape=select_autoescape(("html",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["peso"] = _format_peso
    environment.filters["signal"] = lambda value: str(value).replace("_", " ").title()
    return environment


def _format_peso(centavos: int) -> str:
    sign = "−" if centavos < 0 else ""
    pesos, remainder = divmod(abs(centavos), 100)
    return f"{sign}₱{pesos:,}.{remainder:02d}"


def _write_page(output_dir: Path, route: str, template: str, **context: object) -> Path:
    destination = output_dir / route / "index.html" if route else output_dir / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = _environment().get_template(template).render(**context)
    destination.write_text(rendered, encoding="utf-8")
    return destination


def _write_assets(output_dir: Path) -> None:
    destination = output_dir / "assets"
    destination.mkdir(parents=True, exist_ok=True)
    for asset in ("favicon.svg", "site.css", "site.js"):
        copyfile(ASSET_ROOT / asset, destination / asset)


def _write_core_pages(output_dir: Path, publication: PublicationView) -> list[Path]:
    return [
        _write_page(output_dir, "", "home.html", publication=publication),
        _write_page(output_dir, "watchlist", "watchlist.html", publication=publication),
        _write_page(output_dir, "methodology", "methodology.html", publication=publication),
    ]


def build_site(golden_path: Path, output_dir: Path) -> SiteBuildResult:
    publication = build_publication(golden_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = _write_core_pages(output_dir, publication)
    for dossier in publication.dossiers:
        pages.append(
            _write_page(
                output_dir,
                f"projects/{dossier.slug}",
                "project.html",
                publication=publication,
                dossier=dossier,
            )
        )
    _write_assets(output_dir)
    return SiteBuildResult(output_dir, len(pages), len(publication.dossiers))


def _route_target(site_root: Path, href: str) -> Path | None:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    path = parsed.path.strip("/")
    if not path:
        return site_root / "index.html"
    target = site_root / path
    return target / "index.html" if parsed.path.endswith("/") else target


def validate_site(site_root: Path) -> SiteValidationReport:
    pages = tuple(sorted(site_root.rglob("*.html")))
    missing: set[str] = set()
    no_viewport: list[str] = []
    no_main: list[str] = []
    for page in pages:
        parser = _PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        relative = str(page.relative_to(site_root))
        if not parser.has_viewport:
            no_viewport.append(relative)
        if not parser.has_main:
            no_main.append(relative)
        for link in parser.links:
            target = _route_target(site_root, link)
            if target is not None and not target.exists():
                missing.add(link)
    return SiteValidationReport(
        pages_checked=len(pages),
        missing_routes=tuple(sorted(missing)),
        pages_missing_viewport=tuple(no_viewport),
        pages_missing_main_landmark=tuple(no_main),
    )
