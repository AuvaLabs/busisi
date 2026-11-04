"""Acquire and publish contractor accountability evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from engine.budget_watchdog.acquisition import SourceFetcher
from engine.budget_watchdog.archive import ArtifactArchive
from engine.budget_watchdog.contractor_accountability import (
    AccountabilitySnapshot,
    AwardRecord,
    BlacklistIndex,
    BlacklistOrder,
    ContractorRecord,
    CpesLowRating,
    build_accountability_snapshot,
    normalize_entity_name,
    parse_blacklist_index_pages,
    parse_blacklist_order_pages,
    parse_cpes_low_ratings,
)
from engine.budget_watchdog.contractor_accountability_bundle import (
    build_accountability_bundle,
)
from engine.budget_watchdog.rate_limit import HostRateLimiter
from engine.budget_watchdog.sources import default_source_registry

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "budget_watchdog"
DEFAULT_OUTPUT = DATA / "contractor-accountability"
INTEGRITY_BUNDLE = DATA / "integrity-d1-bundle"
ACQUISITION_BUNDLE = DATA / "acquisition-detail-d1-bundle"
MIGRATIONS = ROOT / "cloudflare" / "busisi" / "migrations"
BLACKLIST_PATH = "/obp-backend/dashboard/list-blacklisted-entities/"
BLACKLIST_CHILD_PATH = "/obp-backend/dashboard/child-list-blacklisted-entities/"
CPES_INDEX_PATH = "/constructors-performance-evaluation-system-cpes-report/"
MAX_PAGES = 100
MAX_ENTITIES = 10_000
TEEN_SUFFIX_START = 10
TEEN_SUFFIX_END = 20


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    blacklist_index: BlacklistIndex
    blacklist_orders: tuple[BlacklistOrder, ...]
    blacklist_duplicate_order_rows: int
    cpes_ratings: tuple[CpesLowRating, ...]
    cpes_release: str
    cpes_source_sha256: str
    cpes_source_url: str


class _CpesLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def discover_latest_cpes_report(payload: bytes) -> tuple[str, str]:
    """Return the highest numbered same-origin CPES release PDF."""

    parser = _CpesLinks()
    parser.feed(payload.decode("utf-8"))
    candidates = []
    for href, text in parser.links:
        match = re.search(r"CPES Report (\d+)(?:st|nd|rd|th) Release", text)
        if match is None:
            continue
        parsed = urlparse(href)
        if parsed.scheme and (parsed.scheme != "https" or parsed.netloc != "www.gppb.gov.ph"):
            continue
        path = parsed.path
        if not path.startswith("/wp-content/uploads/") or not path.lower().endswith(".pdf"):
            continue
        release_number = int(match.group(1))
        label = f"{release_number}{_ordinal(release_number)} Release"
        candidates.append((release_number, label, path))
    if not candidates:
        raise ValueError("no official CPES report link was found")
    _, label, path = max(candidates)
    return label, path


def _ordinal(number: int) -> str:
    if TEEN_SUFFIX_START <= number % 100 <= TEEN_SUFFIX_END:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


def _json_pages(document: bytes, label: str) -> tuple[int, int]:
    try:
        value = json.loads(document)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} response must be an object")
    count = value.get("count")
    pages = value.get("total_pages")
    if not isinstance(count, int) or count < 0 or count > MAX_ENTITIES:
        raise ValueError(f"{label} count is outside bounds")
    if not isinstance(pages, int) or pages < 1 or pages > MAX_PAGES:
        raise ValueError(f"{label} page count is outside bounds")
    return count, pages


def _fetch_pages(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    path: str,
    *,
    retrieved_at: datetime,
    parameters: dict[str, str] | None = None,
) -> tuple[tuple[bytes, ...], tuple[str, ...]]:
    params = dict(parameters or {})
    params["page"] = "1"
    first = fetcher.fetch("gppb-blacklist", path, params=params, retrieved_at=retrieved_at)
    first_artifact = archive.store(first)
    _, total_pages = _json_pages(first.payload, "GPPB blacklist")
    payloads = [first.payload]
    digests = [first_artifact.sha256]
    for page in range(2, total_pages + 1):
        params["page"] = str(page)
        acquisition = fetcher.fetch(
            "gppb-blacklist", path, params=params, retrieved_at=retrieved_at
        )
        payloads.append(acquisition.payload)
        digests.append(archive.store(acquisition).sha256)
    return tuple(payloads), tuple(digests)


def _candidate_names(
    index: BlacklistIndex, contractors: tuple[ContractorRecord, ...]
) -> tuple[str, ...]:
    if not contractors:
        return (index.entities[0].reported_name,) if index.entities else ()
    contractor_names = {normalize_entity_name(item.contractor_name) for item in contractors}
    return tuple(
        sorted(
            {
                item.reported_name
                for item in index.entities
                if normalize_entity_name(item.reported_name) in contractor_names
            }
        )
    )


def _acquire_blacklists(
    fetcher: SourceFetcher,
    archive: ArtifactArchive,
    retrieved_at: datetime,
    contractors: tuple[ContractorRecord, ...],
) -> tuple[BlacklistIndex, tuple[BlacklistOrder, ...], int]:
    payloads, digests = _fetch_pages(fetcher, archive, BLACKLIST_PATH, retrieved_at=retrieved_at)
    index = parse_blacklist_index_pages(payloads, digests)
    orders = []
    duplicate_rows = 0
    for name in _candidate_names(index, contractors):
        child_payloads, child_digests = _fetch_pages(
            fetcher,
            archive,
            BLACKLIST_CHILD_PATH,
            retrieved_at=retrieved_at,
            parameters={"be": name},
        )
        parsed = parse_blacklist_order_pages(
            name, tuple(zip(child_payloads, child_digests, strict=True))
        )
        reported_count, _ = _json_pages(child_payloads[0], "GPPB blacklist orders")
        duplicate_rows += reported_count - len(parsed)
        orders.extend(parsed)
    return index, tuple(orders), duplicate_rows


def _pdf_layout_text(payload: bytes) -> str:
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(BytesIO(payload))
    if reader.is_encrypted or not reader.pages:
        raise ValueError("CPES PDF is encrypted or empty")
    pages = []
    for page in reader.pages:
        text = page.extract_text(extraction_mode="layout")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("CPES PDF contains a page without extractable text")
        pages.append(text)
    return "\f".join(pages)


def _acquire_cpes(
    fetcher: SourceFetcher, archive: ArtifactArchive, retrieved_at: datetime
) -> tuple[tuple[CpesLowRating, ...], str, str, str]:
    index = fetcher.fetch("gppb", CPES_INDEX_PATH, retrieved_at=retrieved_at)
    archive.store(index)
    release, path = discover_latest_cpes_report(index.payload)
    report = fetcher.fetch("gppb", path, retrieved_at=retrieved_at)
    artifact = archive.store(report)
    ratings = parse_cpes_low_ratings(
        _pdf_layout_text(report.payload),
        source_sha256=artifact.sha256,
        source_url=report.source_url,
        release_label=release,
    )
    return ratings, release, artifact.sha256, report.source_url


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _manifest(directory: Path) -> dict:
    path = directory / "manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("chunk_sha256"), dict):
        raise ValueError(f"bundle manifest is invalid: {directory.name}")
    return document


def _apply_chunks(
    database: sqlite3.Connection, directory: Path, manifest: dict, patterns: tuple[str, ...]
) -> None:
    paths = tuple(
        path for pattern in patterns for path in sorted((directory / "chunks").glob(pattern))
    )
    if not paths:
        raise ValueError(f"bundle contains no selected chunks: {directory.name}")
    expected = manifest["chunk_sha256"]
    for path in paths:
        if expected.get(path.name) != _digest(path):
            raise ValueError(f"bundle chunk digest mismatch: {path.name}")
        database.executescript(path.read_text(encoding="utf-8"))


def _context_database() -> tuple[sqlite3.Connection, dict, dict]:
    integrity = _manifest(INTEGRITY_BUNDLE)
    acquisition = _manifest(ACQUISITION_BUNDLE)
    database = sqlite3.connect(":memory:")
    database.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    for name in (
        "0005_integrity.sql",
        "0006_contractor_verification.sql",
        "0011_delivery_details.sql",
        "0024_contractor_project_associations.sql",
        "0018_contract_acquisition_detail.sql",
    ):
        database.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
    _apply_chunks(database, INTEGRITY_BUNDLE, integrity, ("200-contractors-*.sql",))
    _apply_chunks(database, INTEGRITY_BUNDLE, integrity, ("250-contractor-associations-*.sql",))
    _apply_chunks(database, ACQUISITION_BUNDLE, acquisition, ("100-contracts-*.sql",))
    _apply_chunks(database, ACQUISITION_BUNDLE, acquisition, ("200-matches-*.sql",))
    actual = database.execute("SELECT COUNT(*) FROM contractor_rankings").fetchone()[0]
    if actual != int(integrity["contractors"]):
        raise ValueError("contractor context control total does not reconcile")
    return database, integrity, acquisition


def _contractors(database: sqlite3.Connection) -> tuple[ContractorRecord, ...]:
    rows = database.execute(
        "SELECT contractor_key, contractor_name, pcab_id, pcab_name FROM contractor_rankings"
    ).fetchall()
    return tuple(ContractorRecord(*row) for row in rows)


def _awards(database: sqlite3.Connection, keys: tuple[str, ...]) -> tuple[AwardRecord, ...]:
    if not keys:
        return ()
    placeholders = ",".join("?" for _ in keys)
    rows = database.execute(
        f"""
        SELECT award.source_row_id, award.contract_id, association.contractor_key,
          association.relationship, award.match_basis, award.awardee_name, award.award_date,
          award.contract_amount_centavos, award.row_sha256
        FROM contractor_project_associations association
        JOIN contract_acquisition_details detail USING (contract_id)
        JOIN contract_award_matches award USING (contract_id)
        WHERE association.contractor_key IN ({placeholders})
          AND detail.match_state IN ('structured_exact', 'title_exact')
        """,  # noqa: S608
        keys,
    ).fetchall()
    return tuple(AwardRecord(*row) for row in rows)


def _acquire_sources(
    contractors: tuple[ContractorRecord, ...], output: Path, retrieved_at: datetime
) -> SourceEvidence:
    limiter = HostRateLimiter(requests_per_second=2.0)
    fetcher = SourceFetcher(
        default_source_registry(), request_gate=limiter.wait_for_url, max_attempts=3
    )
    archive = ArtifactArchive(output / "archive")
    index, orders, duplicate_rows = _acquire_blacklists(fetcher, archive, retrieved_at, contractors)
    ratings, release, cpes_sha, cpes_url = _acquire_cpes(fetcher, archive, retrieved_at)
    return SourceEvidence(index, orders, duplicate_rows, ratings, release, cpes_sha, cpes_url)


def _write_report(output: Path, report: dict) -> Path:
    stamp = report["checked_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    run_dir = output / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "report.json"
    document = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(document, encoding="utf-8")
    (output / "latest.json").write_text(document, encoding="utf-8")
    return path


def _source_report(evidence: SourceEvidence, checked_at: datetime) -> dict:
    return {
        "passed": True,
        "checked_at": checked_at.isoformat(),
        "blacklist_entities": evidence.blacklist_index.reported_count,
        "blacklist_index_date_anomalies": evidence.blacklist_index.date_anomaly_count,
        "blacklist_duplicate_order_rows": evidence.blacklist_duplicate_order_rows,
        "blacklist_index_sha256": list(evidence.blacklist_index.source_sha256),
        "candidate_blacklist_orders": len(evidence.blacklist_orders),
        "cpes_low_ratings": len(evidence.cpes_ratings),
        "cpes_release": evidence.cpes_release,
        "cpes_source_sha256": evidence.cpes_source_sha256,
        "cpes_source_url": evidence.cpes_source_url,
    }


def _snapshot(
    database: sqlite3.Connection,
    contractors: tuple[ContractorRecord, ...],
    evidence: SourceEvidence,
    acquisition: dict,
    checked_at: datetime,
) -> AccountabilitySnapshot:
    initial = build_accountability_snapshot(
        contractors,
        evidence.blacklist_orders,
        evidence.cpes_ratings,
        (),
        checked_on=checked_at.date().isoformat(),
        blacklist_index_sha256=evidence.blacklist_index.source_sha256,
        award_source_sha256=acquisition["award_sha256"],
        award_source_revision=acquisition["award_revision"],
    )
    keys = tuple(
        sorted(
            {item.contractor_key for item in initial.blacklist_events}
            | {item.contractor_key for item in initial.cpes_events}
        )
    )
    return build_accountability_snapshot(
        contractors,
        evidence.blacklist_orders,
        evidence.cpes_ratings,
        _awards(database, keys),
        checked_on=checked_at.date().isoformat(),
        blacklist_index_sha256=evidence.blacklist_index.source_sha256,
        award_source_sha256=acquisition["award_sha256"],
        award_source_revision=acquisition["award_revision"],
    )


def run_accountability(
    output: Path = DEFAULT_OUTPUT, *, source_only: bool = False, reset_output: bool = False
) -> tuple[dict, int]:
    if reset_output:
        shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    checked_at = datetime.now(UTC)
    database = None
    try:
        if source_only:
            contractors: tuple[ContractorRecord, ...] = ()
            acquisition = None
        else:
            database, _, acquisition = _context_database()
            contractors = _contractors(database)
        evidence = _acquire_sources(contractors, output, checked_at)
        report = _source_report(evidence, checked_at)
        if database is not None and acquisition is not None:
            snapshot = _snapshot(database, contractors, evidence, acquisition, checked_at)
            bundle = build_accountability_bundle(snapshot, output / "d1-bundle")
            report.update(
                blacklist_events=bundle.blacklist_events,
                cpes_events=bundle.cpes_events,
                award_signals=bundle.award_signals,
                quarantine_counts=snapshot.quarantine_counts,
                manifest_sha256=bundle.manifest_sha256,
                sql_path=str(bundle.output_dir / "contractor-accountability.sql"),
            )
        code = 0
    except Exception as exc:
        report = {
            "passed": False,
            "checked_at": checked_at.isoformat(),
            "error_type": type(exc).__name__,
            "status_note": "Contractor accountability evidence failed validation and was not published.",
        }
        code = 2
    finally:
        if database is not None:
            database.close()
    report["report_path"] = str(_write_report(output, report))
    return report, code


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--reset-output", action="store_true")
    return parser.parse_args()


def main() -> int:
    options = arguments()
    report, code = run_accountability(
        options.output,
        source_only=options.source_only,
        reset_output=options.reset_output,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
