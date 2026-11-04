import json
from pathlib import Path

import pytest

from engine.budget_watchdog import senate_monitor
from engine.budget_watchdog.senate_monitor import (
    HttpPayload,
    SenateMonitorError,
    run_senate_monitor,
)

ROOT_HTML = b"""
<table><tbody>
<tr class="folder-item portal-library-row" data-folder-id="123">
  <td class="portal-library-name">House Bill No. 10858</td>
  <td data-label="Type">Folder</td><td data-label="Size">-</td><td data-label="Date">-</td>
</tr>
</tbody></table>
"""

EMPTY_ROOT_HTML = b"""
<html><body>
<table><tbody id="court-documents" data-type="Documents" data-offset="0"></tbody></table>
</body></html>
"""

FOLDER_MARKDOWN = b"""Title:

Markdown Content:
1- HB 10858 FOR 3RD READING VOL I-A Document 18 KB October 13, 2026
2- HB 10858 FOR 3RD READING VOL I-B Document 15 KB October 13, 2026
3- HB 10858 FOR 3RD READING VOL I-C Document 9.16 KB October 13, 2026
4-HB 10858 3RD READING VOL II Document 10 KB October 13, 2026
"""

FOLDER_ROWS = (
    ("384", "1- HB 10858 FOR 3RD READING VOL I-A", "18 KB"),
    ("385", "2- HB 10858 FOR 3RD READING VOL I-B", "15 KB"),
    ("386", "3- HB 10858 FOR 3RD READING VOL I-C", "9.16 KB"),
    ("387", "4-HB 10858 3RD READING VOL II", "10 KB"),
)


def _row(record_id: str, title: str, size: str) -> bytes:
    return f"""<tr class="portal-library-row">
      <td class="portal-library-name">{title}</td>
      <td data-label="Type">Document</td><td data-label="Size">{size}</td>
      <td data-label="Date">October 13, 2026</td>
      <td><a data-file-id="{record_id}"></a></td>
    </tr>""".encode()


def _fetcher(*, changed: bool = False):
    def fetch(url: str, headers: dict[str, str]) -> HttpPayload:
        if url.startswith("https://budget-transparency-portal.senate.gov.ph"):
            return HttpPayload(403, url, b"blocked", "text/html")
        if "/public/Documents" in url:
            return HttpPayload(200, url, ROOT_HTML, "text/html")
        if headers.get("X-Return-Format") != "html":
            markdown = FOLDER_MARKDOWN
            if changed:
                markdown += b"Senate Committee Report FY 2027 Document 20 KB November 1, 2026\n"
            return HttpPayload(200, url, markdown, "text/plain")
        offset = int(url.split("offset=", 1)[1].split("&", 1)[0])
        if offset < len(FOLDER_ROWS):
            return HttpPayload(200, url, _row(*FOLDER_ROWS[offset]), "text/html")
        return HttpPayload(
            200,
            url,
            _row("420", "Senate Committee Report FY 2027", "20 KB"),
            "text/html",
        )

    return fetch


def _baseline() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "ops"
        / "harness"
        / "fixtures"
        / "senate_2027_catalog.json"
    )


def test_monitor_accepts_unchanged_secondary_catalogue(tmp_path) -> None:
    result = run_senate_monitor(_baseline(), tmp_path, fetch=_fetcher())

    assert result.changed is False
    assert result.direct_status == "blocked"
    assert result.discovery_mode == "secondary_renderer"
    assert result.expected_document_count == 4
    assert result.observed_document_count == 4
    assert result.differences == ()
    assert len(result.response_artifacts) == 3
    assert (tmp_path / "report.json").is_file()


def test_monitor_loads_async_root_listing_when_rendered_page_is_empty(tmp_path) -> None:
    def fetch(url: str, _headers: dict[str, str]) -> HttpPayload:
        if url.startswith("https://budget-transparency-portal.senate.gov.ph"):
            return HttpPayload(403, url, b"blocked", "text/html")
        if "/public/Documents" in url:
            return HttpPayload(200, url, EMPTY_ROOT_HTML, "text/html")
        if "folder=&" in url:
            return HttpPayload(200, url, ROOT_HTML, "text/html")
        return HttpPayload(200, url, FOLDER_MARKDOWN, "text/plain")

    result = run_senate_monitor(_baseline(), tmp_path, fetch=fetch)

    assert result.changed is False
    assert result.observed_document_count == 4
    assert [artifact.name for artifact in result.response_artifacts] == [
        "direct-root.html",
        "secondary-root.html",
        "secondary-root-listing.html",
        "folder-123-listing.md",
    ]


def test_monitor_retains_reviewed_historical_documents_without_expectation(
    tmp_path,
) -> None:
    baseline = json.loads(_baseline().read_text(encoding="utf-8"))
    baseline["monitor_excluded_source_record_ids"] = ["417"]
    baseline_path = tmp_path / "catalog.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    def fetch(url: str, headers: dict[str, str]) -> HttpPayload:
        payload = _fetcher()(url, headers)
        if "/public/Documents" in url and url.startswith("https://r.jina.ai"):
            return HttpPayload(200, url, ROOT_HTML, "text/html")
        return payload

    result = run_senate_monitor(baseline_path, tmp_path / "output", fetch=fetch)

    assert result.changed is False
    assert result.expected_document_count == 4
    assert result.observed_document_count == 4


def test_monitor_quarantines_new_catalogue_records(tmp_path) -> None:
    result = run_senate_monitor(_baseline(), tmp_path, fetch=_fetcher(changed=True))

    assert result.changed is True
    assert result.observed_document_count == 5
    assert len(result.differences) == 1
    assert result.differences[0].startswith("new source record unresolved:")
    assert result.differences[0].endswith(": Senate Committee Report FY 2027")


def test_monitor_reports_missing_or_changed_records(tmp_path) -> None:
    def fetch(url: str, headers: dict[str, str]) -> HttpPayload:
        payload = _fetcher()(url, headers)
        if "/index/file_card" in url and headers.get("X-Return-Format") != "html":
            return HttpPayload(
                200,
                url,
                FOLDER_MARKDOWN.replace(
                    b"3- HB 10858 FOR 3RD READING VOL I-C",
                    b"3- HB 10858 ALTERED TITLE",
                ),
                "text/plain",
            )
        return payload

    result = run_senate_monitor(_baseline(), tmp_path, fetch=fetch)

    assert result.changed is True
    assert result.differences[0] == "missing source record 386"
    assert result.differences[1].startswith("new source record unresolved:")
    assert result.differences[1].endswith(": 3- HB 10858 ALTERED TITLE")


def test_monitor_uses_official_catalogue_when_direct_access_works(tmp_path) -> None:
    def fetch(url: str, _headers: dict[str, str]) -> HttpPayload:
        if "/public/Documents" in url:
            return HttpPayload(200, url, ROOT_HTML, "text/html")
        offset = int(url.split("offset=", 1)[1].split("&", 1)[0])
        content = _row(*FOLDER_ROWS[offset]) if offset < len(FOLDER_ROWS) else b""
        return HttpPayload(200, url, content, "text/html")

    result = run_senate_monitor(_baseline(), tmp_path, fetch=fetch)

    assert result.changed is False
    assert result.direct_status == "available"
    assert result.discovery_mode == "official_direct"
    assert result.observed_document_count == 4
    assert len(result.response_artifacts) == 6


def test_monitor_retries_transient_challenges(monkeypatch) -> None:
    calls = 0

    def fetch(url: str, _headers: dict[str, str]) -> HttpPayload:
        nonlocal calls
        calls += 1
        content = b"<title>Just a moment</title> Cloudflare" if calls < 3 else b"ready"
        return HttpPayload(200, url, content, "text/html")

    monkeypatch.setattr(senate_monitor.time, "sleep", lambda _seconds: None)
    result = senate_monitor._fetch_checked(fetch, "https://r.jina.ai/test", {})

    assert result.content == b"ready"
    assert calls == 3


def test_monitor_records_forbidden_challenge_without_retry(monkeypatch) -> None:
    calls = 0

    def fetch(url: str, _headers: dict[str, str]) -> HttpPayload:
        nonlocal calls
        calls += 1
        return HttpPayload(
            403,
            url,
            b"<title>Just a moment</title> Cloudflare",
            "text/html",
        )

    monkeypatch.setattr(senate_monitor.time, "sleep", lambda _seconds: None)
    result = senate_monitor._fetch_checked(fetch, "https://example.test", {})

    assert result.status_code == 403
    assert calls == 1


def test_monitor_rejects_empty_secondary_folder_listing(tmp_path) -> None:
    def fetch(url: str, headers: dict[str, str]) -> HttpPayload:
        payload = _fetcher()(url, headers)
        if "/index/file_card" in url:
            return HttpPayload(200, url, b"Markdown Content: no documents", "text/plain")
        return payload

    with pytest.raises(SenateMonitorError, match="contains no documents"):
        run_senate_monitor(_baseline(), tmp_path, fetch=fetch)


class _FakeResponse:
    def __init__(self, *, content: bytes = b"payload", url: str) -> None:
        self.status_code = 200
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        yield self._content


def test_bounded_http_fetcher_accepts_only_allowlisted_origins(monkeypatch) -> None:
    url = "https://r.jina.ai/https://example.test"
    monkeypatch.setattr(
        senate_monitor.requests,
        "get",
        lambda *_args, **_kwargs: _FakeResponse(url=url),
    )

    result = senate_monitor._request(url, {"X-Return-Format": "html"})

    assert result.status_code == 200
    assert result.content == b"payload"
    assert result.media_type == "text/html"
    with pytest.raises(SenateMonitorError, match="allowlist"):
        senate_monitor._request("https://example.test/private", {})


def test_bounded_http_fetcher_rejects_oversize_and_origin_escape(monkeypatch) -> None:
    url = "https://r.jina.ai/test"
    monkeypatch.setattr(
        senate_monitor.requests,
        "get",
        lambda *_args, **_kwargs: _FakeResponse(
            content=b"x" * (senate_monitor.MAX_RESPONSE_BYTES + 1),
            url=url,
        ),
    )
    with pytest.raises(SenateMonitorError, match="size limit"):
        senate_monitor._request(url, {})

    monkeypatch.setattr(
        senate_monitor.requests,
        "get",
        lambda *_args, **_kwargs: _FakeResponse(url="https://example.test/escaped"),
    )
    with pytest.raises(SenateMonitorError, match="escaped"):
        senate_monitor._request(url, {})
