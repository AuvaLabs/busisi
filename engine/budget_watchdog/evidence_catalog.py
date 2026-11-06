"""Verified document catalogue, page extraction, and disposable retrieval index."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SHA256 = re.compile(r"[a-f0-9]{64}")
DOCUMENT_ID = re.compile(r"[a-z0-9][a-z0-9:._-]{1,127}")
MAX_CHUNK_CHARACTERS = 6_000
CHUNK_OVERLAP_CHARACTERS = 300

SCHEMA = """
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;
CREATE TABLE retrieval_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE retrieval_documents (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    source_url TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256) = 64),
    media_type TEXT NOT NULL,
    fiscal_year INTEGER,
    stage TEXT,
    agency TEXT,
    contract_id TEXT,
    project_id TEXT,
    extraction_method TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK(byte_size > 0)
);
CREATE TABLE retrieval_pages (
    document_id TEXT NOT NULL REFERENCES retrieval_documents(document_id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    page_text TEXT NOT NULL,
    page_sha256 TEXT NOT NULL CHECK(length(page_sha256) = 64),
    PRIMARY KEY (document_id, page_number)
);
CREATE TABLE retrieval_chunks (
    rowid INTEGER PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE CHECK(length(chunk_id) = 64),
    document_id TEXT NOT NULL REFERENCES retrieval_documents(document_id),
    page_start INTEGER NOT NULL CHECK(page_start > 0),
    page_end INTEGER NOT NULL CHECK(page_end >= page_start),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    chunk_text TEXT NOT NULL,
    chunk_sha256 TEXT NOT NULL CHECK(length(chunk_sha256) = 64),
    UNIQUE(document_id, page_start, ordinal)
);
CREATE VIRTUAL TABLE retrieval_chunks_fts USING fts5(
    title,
    chunk_text,
    identifiers,
    content='retrieval_chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE retrieval_vectors (
    chunk_id TEXT NOT NULL REFERENCES retrieval_chunks(chunk_id),
    model_id TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK(dimension > 0),
    vector_json TEXT NOT NULL,
    chunk_sha256 TEXT NOT NULL CHECK(length(chunk_sha256) = 64),
    PRIMARY KEY (chunk_id, model_id)
);
CREATE INDEX retrieval_chunks_document ON retrieval_chunks(document_id);
CREATE INDEX retrieval_documents_filters ON retrieval_documents(fiscal_year, stage, agency);
"""


@dataclass(frozen=True, slots=True)
class EvidenceIndexResult:
    database_path: Path
    manifest_sha256: str
    document_count: int
    page_count: int
    chunk_count: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _document_path(root: Path, value: Any) -> tuple[Path, str]:
    relative = Path(_required_text(value, "artifact_path"))
    if relative.is_absolute():
        raise ValueError("artifact_path must be inside the catalog root")
    root_resolved = root.resolve()
    resolved = (root_resolved / relative).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError("artifact_path must stay inside the catalog root")
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"catalog artifact is missing or empty: {relative}")
    return resolved, relative.as_posix()


def _validate_url(value: Any) -> str:
    source_url = _required_text(value, "source_url")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source_url must use HTTPS")
    return source_url


def _extract_pdf(path: Path) -> tuple[str, str]:
    try:
        completed = subprocess.run(  # noqa: S603
            ["/usr/bin/pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            check=False,
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"PDF extraction failed for {path.name}: {error}") from error
    if completed.returncode:
        message = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"PDF extraction failed for {path.name}: {message}")
    try:
        text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"PDF extraction was not valid UTF-8: {path.name}") from error
    if not text.strip():
        raise ValueError(f"PDF contains no extractable text: {path.name}")
    return text, "pdftotext-layout"


def _extract_text(path: Path, media_type: str) -> tuple[str, str]:
    if media_type == "application/pdf":
        return _extract_pdf(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"artifact is not valid UTF-8: {path.name}") from error
    if media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(text)
        return html.unescape("\n".join(parser.parts)), "html-text"
    if media_type == "application/json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"artifact is not valid JSON: {path.name}") from error
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), "json-text"
    if media_type != "text/plain":
        raise ValueError(f"unsupported document media_type: {media_type}")
    return text, "plain-text"


def _pages(text: str) -> tuple[str, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    values = normalized.split("\f")
    while len(values) > 1 and not values[-1].strip():
        values.pop()
    if not values or not any(item.strip() for item in values):
        raise ValueError("document contains no extractable text")
    return tuple(item.strip() for item in values)


def _chunks(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    values = []
    start = 0
    while start < len(text):
        stop = min(len(text), start + MAX_CHUNK_CHARACTERS)
        if stop < len(text):
            boundary = text.rfind("\n", start + MAX_CHUNK_CHARACTERS // 2, stop)
            if boundary > start:
                stop = boundary
        value = text[start:stop].strip()
        if value:
            values.append(value)
        if stop >= len(text):
            break
        start = max(stop - CHUNK_OVERLAP_CHARACTERS, start + 1)
    return tuple(values)


def _load_manifest(path: Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], str]:
    payload = path.read_bytes()
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("document catalog must be valid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("document catalog schema_version must be 1")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("document catalog must contain documents")
    if not all(isinstance(item, dict) for item in documents):
        raise ValueError("document catalog entries must be objects")
    return manifest, tuple(documents), _sha256(payload)


def _insert_document(
    connection: sqlite3.Connection,
    root: Path,
    document: dict[str, Any],
) -> tuple[int, int]:
    document_id = _required_text(document.get("document_id"), "document_id")
    if DOCUMENT_ID.fullmatch(document_id) is None:
        raise ValueError("document_id must be a stable lowercase identifier")
    path, relative_path = _document_path(root, document.get("artifact_path"))
    expected_digest = _required_text(document.get("artifact_sha256"), "artifact_sha256")
    if SHA256.fullmatch(expected_digest) is None or _file_sha256(path) != expected_digest:
        raise ValueError(f"artifact SHA-256 does not match for {document_id}")
    media_type = _required_text(document.get("media_type"), "media_type").lower()
    extracted, extraction_method = _extract_text(path, media_type)
    fiscal_year = document.get("fiscal_year")
    if fiscal_year is not None and (not isinstance(fiscal_year, int) or isinstance(fiscal_year, bool)):
        raise ValueError("fiscal_year must be an integer or null")
    title = _required_text(document.get("title"), "title")
    values = (
        document_id,
        title,
        _required_text(document.get("publisher"), "publisher"),
        _validate_url(document.get("source_url")),
        relative_path,
        expected_digest,
        media_type,
        fiscal_year,
        _optional_text(document.get("stage"), "stage"),
        _optional_text(document.get("agency"), "agency"),
        _optional_text(document.get("contract_id"), "contract_id"),
        _optional_text(document.get("project_id"), "project_id"),
        extraction_method,
        path.stat().st_size,
    )
    try:
        connection.execute("INSERT INTO retrieval_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
    except sqlite3.IntegrityError as error:
        if "document_id" in str(error):
            raise ValueError(f"duplicate document_id: {document_id}") from error
        raise
    page_count = 0
    chunk_count = 0
    identifiers = " ".join(
        value for value in (document_id, values[9], values[10], values[11]) if value
    )
    for page_number, page_text in enumerate(_pages(extracted), start=1):
        page_digest = _sha256(page_text.encode())
        connection.execute(
            "INSERT INTO retrieval_pages VALUES (?,?,?,?)",
            (document_id, page_number, page_text, page_digest),
        )
        page_count += 1
        for ordinal, chunk_text in enumerate(_chunks(page_text)):
            chunk_digest = _sha256(chunk_text.encode())
            identity = f"{document_id}\0{page_number}\0{ordinal}\0{chunk_digest}".encode()
            chunk_id = _sha256(identity)
            cursor = connection.execute(
                "INSERT INTO retrieval_chunks(chunk_id,document_id,page_start,page_end,ordinal,chunk_text,chunk_sha256) VALUES (?,?,?,?,?,?,?)",
                (chunk_id, document_id, page_number, page_number, ordinal, chunk_text, chunk_digest),
            )
            connection.execute(
                "INSERT INTO retrieval_chunks_fts(rowid,title,chunk_text,identifiers) VALUES (?,?,?,?)",
                (cursor.lastrowid, title, chunk_text, identifiers),
            )
            chunk_count += 1
    return page_count, chunk_count


def build_evidence_index(
    manifest_path: Path,
    database_path: Path,
    *,
    catalog_root: Path | None = None,
) -> EvidenceIndexResult:
    """Build and atomically install a verified, disposable retrieval database."""

    _, documents, manifest_sha256 = _load_manifest(manifest_path)
    root = catalog_root or manifest_path.parent
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_handle, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.", suffix=".tmp", dir=database_path.parent
    )
    os.close(temporary_handle)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO retrieval_metadata VALUES ('manifest_sha256', ?)",
                (manifest_sha256,),
            )
            page_count = 0
            chunk_count = 0
            for document in documents:
                pages, chunks = _insert_document(connection, root, document)
                page_count += pages
                chunk_count += chunks
            if chunk_count == 0:
                raise ValueError("document catalog produced no searchable text")
            connection.execute(
                "INSERT INTO retrieval_metadata VALUES ('schema_version', '1')"
            )
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("retrieval database failed its foreign-key check")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("retrieval database failed its integrity check")
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, database_path)
    finally:
        temporary.unlink(missing_ok=True)
    return EvidenceIndexResult(
        database_path,
        manifest_sha256,
        len(documents),
        page_count,
        chunk_count,
    )
