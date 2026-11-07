import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from engine.budget_watchdog.evidence_catalog import build_evidence_index


def _document(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return {
        "document_id": name.removesuffix(".txt"),
        "title": name.removesuffix(".txt").replace("-", " ").title(),
        "publisher": "Department of Budget and Management",
        "source_url": f"https://www.dbm.gov.ph/{name}",
        "artifact_path": name,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "media_type": "text/plain",
        "fiscal_year": 2027,
        "stage": "nep",
        "agency": "DPWH",
        "evidence_kinds": ["budget_document"],
    }


def _manifest(tmp_path, documents):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps({"schema_version": 2, "documents": documents}), encoding="utf-8"
    )
    return path


def test_builds_page_catalog_and_content_addressed_chunks(tmp_path) -> None:
    document = _document(
        tmp_path,
        "dpwh.txt",
        "Flood Management Program\nPasig River works\fSchool Building Program\nManila classrooms",
    )

    result = build_evidence_index(_manifest(tmp_path, [document]), tmp_path / "index.sqlite3")

    assert result.document_count == 1
    assert result.page_count == 2
    assert result.chunk_count == 2
    assert len(result.manifest_sha256) == 64
    connection = sqlite3.connect(result.database_path)
    document_row = connection.execute(
        "SELECT document_id, artifact_sha256, extraction_method, evidence_kinds_json "
        "FROM retrieval_documents"
    ).fetchone()
    pages = connection.execute(
        "SELECT page_number, page_sha256 FROM retrieval_pages ORDER BY page_number"
    ).fetchall()
    chunks = connection.execute(
        "SELECT chunk_id, chunk_sha256 FROM retrieval_chunks ORDER BY rowid"
    ).fetchall()
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    connection.close()
    assert document_row == (
        "dpwh",
        document["artifact_sha256"],
        "plain-text",
        '["budget_document"]',
    )
    assert pages[0][0] == 1
    assert pages[1][0] == 2
    assert all(len(item[1]) == 64 for item in pages)
    assert all(len(value) == 64 for item in chunks for value in item)
    assert integrity == "ok"


def test_rejects_changed_bytes_duplicate_ids_and_unsafe_paths(tmp_path) -> None:
    document = _document(tmp_path, "budget.txt", "Original official text")
    document["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        build_evidence_index(_manifest(tmp_path, [document]), tmp_path / "bad.sqlite3")

    valid = _document(tmp_path, "valid.txt", "Verified text")
    with pytest.raises(ValueError, match="duplicate document_id"):
        build_evidence_index(
            _manifest(tmp_path, [valid, valid]), tmp_path / "duplicate.sqlite3"
        )

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("not in the catalog root", encoding="utf-8")
    unsafe = {**valid, "document_id": "outside", "artifact_path": "../outside.txt"}
    unsafe["artifact_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="catalog root"):
        build_evidence_index(_manifest(tmp_path, [unsafe]), tmp_path / "unsafe.sqlite3")


def test_index_is_rebuilt_atomically_and_never_keeps_removed_documents(tmp_path) -> None:
    first = _document(tmp_path, "first.txt", "First budget record")
    second = _document(tmp_path, "second.txt", "Second budget record")
    database = tmp_path / "index.sqlite3"
    build_evidence_index(_manifest(tmp_path, [first, second]), database)

    build_evidence_index(_manifest(tmp_path, [second]), database)

    connection = sqlite3.connect(database)
    identifiers = connection.execute(
        "SELECT document_id FROM retrieval_documents ORDER BY document_id"
    ).fetchall()
    connection.close()
    assert identifiers == [("second",)]


def test_extracts_html_json_pdf_and_long_pages(tmp_path, monkeypatch) -> None:
    html_path = tmp_path / "notice.html"
    html_path.write_text("<h1>Budget &amp; program</h1><p>Official notice</p>")
    json_path = tmp_path / "record.json"
    json_path.write_text('{"amount": 100, "program": "Health"}')
    pdf_path = tmp_path / "volume.pdf"
    pdf_path.write_bytes(b"mock pdf bytes")

    def document(path, document_id, media_type):
        return {
            "document_id": document_id,
            "title": document_id,
            "publisher": "Official publisher",
            "source_url": f"https://example.gov.ph/{path.name}",
            "artifact_path": path.name,
            "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "media_type": media_type,
            "fiscal_year": None,
            "stage": "published",
            "agency": "TEST",
            "contract_id": "C-1",
            "project_id": "P-1",
            "evidence_kinds": ["budget_document"],
        }

    long_text = ("A" * 3_500) + "\n" + ("B" * 3_500) + "\fPDF second page\f"
    monkeypatch.setattr(
        "engine.budget_watchdog.evidence_catalog.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=long_text.encode(), stderr=b""
        ),
    )
    documents = [
        document(html_path, "html-record", "text/html"),
        document(json_path, "json-record", "application/json"),
        document(pdf_path, "pdf-record", "application/pdf"),
    ]

    result = build_evidence_index(_manifest(tmp_path, documents), tmp_path / "mixed.sqlite3")

    assert result.document_count == 3
    assert result.page_count == 4
    assert result.chunk_count >= 4
    connection = sqlite3.connect(result.database_path)
    methods = dict(
        connection.execute(
            "SELECT document_id, extraction_method FROM retrieval_documents"
        ).fetchall()
    )
    connection.close()
    assert methods == {
        "html-record": "html-text",
        "json-record": "json-text",
        "pdf-record": "pdftotext-layout",
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not json", "valid JSON"),
        (json.dumps({"schema_version": 1, "documents": [{}]}), "schema_version"),
        (json.dumps({"schema_version": 2, "documents": []}), "contain documents"),
        (json.dumps({"schema_version": 2, "documents": ["bad"]}), "must be objects"),
    ],
)
def test_rejects_invalid_catalog_shapes(tmp_path, payload, message) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(payload)
    with pytest.raises(ValueError, match=message):
        build_evidence_index(manifest, tmp_path / "index.sqlite3")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"document_id": "BAD ID"}, "stable lowercase"),
        ({"source_url": "http://example.com/file"}, "HTTPS"),
        ({"fiscal_year": True}, "integer or null"),
        ({"media_type": "application/octet-stream"}, "unsupported"),
        ({"title": ""}, "title"),
        ({"artifact_path": ""}, "artifact_path"),
        ({"artifact_path": "missing.txt"}, "missing or empty"),
        ({"evidence_kinds": []}, "evidence_kinds"),
        ({"evidence_kinds": ["budget_document", "budget_document"]}, "unique"),
        ({"evidence_kinds": ["rumor"]}, "recognized"),
    ],
)
def test_rejects_invalid_document_boundaries(tmp_path, override, message) -> None:
    document = _document(tmp_path, "valid.txt", "Verified text") | override
    with pytest.raises(ValueError, match=message):
        build_evidence_index(_manifest(tmp_path, [document]), tmp_path / "index.sqlite3")


def test_rejects_unreadable_or_empty_extracted_content(tmp_path) -> None:
    invalid_utf8 = tmp_path / "invalid.txt"
    invalid_utf8.write_bytes(b"\xff\xfe")
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{")
    empty = tmp_path / "empty.txt"
    empty.write_text(" \f \x00 ")

    for path, media_type, message in (
        (invalid_utf8, "text/plain", "valid UTF-8"),
        (invalid_json, "application/json", "valid JSON"),
        (empty, "text/plain", "no extractable text"),
    ):
        document = _document(tmp_path, "base.txt", "base")
        document.update(
            {
                "document_id": f"doc-{path.stem}",
                "artifact_path": path.name,
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "media_type": media_type,
            }
        )
        with pytest.raises(ValueError, match=message):
            build_evidence_index(
                _manifest(tmp_path, [document]), tmp_path / f"{path.stem}.sqlite3"
            )


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (SimpleNamespace(returncode=1, stdout=b"", stderr=b"broken"), "broken"),
        (SimpleNamespace(returncode=0, stdout=b"\xff", stderr=b""), "valid UTF-8"),
        (SimpleNamespace(returncode=0, stdout=b" ", stderr=b""), "no extractable text"),
    ],
)
def test_pdf_extraction_failures_are_explicit(tmp_path, monkeypatch, result, message) -> None:
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"pdf")
    document = _document(tmp_path, "base.txt", "base")
    document.update(
        {
            "document_id": "pdf-document",
            "artifact_path": pdf.name,
            "artifact_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "media_type": "application/pdf",
        }
    )
    monkeypatch.setattr(
        "engine.budget_watchdog.evidence_catalog.subprocess.run",
        lambda *args, **kwargs: result,
    )
    with pytest.raises(ValueError, match=message):
        build_evidence_index(_manifest(tmp_path, [document]), tmp_path / "pdf.sqlite3")


def test_pdf_process_error_is_explicit(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"pdf")
    document = _document(tmp_path, "base.txt", "base")
    document.update(
        {
            "document_id": "pdf-document",
            "artifact_path": pdf.name,
            "artifact_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "media_type": "application/pdf",
        }
    )

    def fail(*args, **kwargs):
        raise OSError("extractor unavailable")

    monkeypatch.setattr("engine.budget_watchdog.evidence_catalog.subprocess.run", fail)
    with pytest.raises(ValueError, match="extractor unavailable"):
        build_evidence_index(_manifest(tmp_path, [document]), tmp_path / "pdf.sqlite3")
