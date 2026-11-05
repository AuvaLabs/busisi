import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.official_procurement_acquisition import (
    OfficialAcquisitionError,
    acquire_official_documents,
    download_official_sources,
    load_official_source_catalog,
)


def _catalog() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "sources": [
                {
                    "source_id": "dpwh-test-app",
                    "source_url": "https://www.dpwh.gov.ph/dpwh/test.pdf",
                    "document_type": "annual_procurement_plan",
                    "bindings": [
                        {
                            "contract_id": "24DD0136",
                            "evidence_type": "procurement_plan",
                            "evidence_class": "official_artifact",
                            "identity_terms": ["DAGATAN", "SAN JOSE"],
                        }
                    ],
                }
            ],
        }
    ).encode()


def test_loads_catalog_and_archives_source_bytes(tmp_path: Path) -> None:
    catalog = load_official_source_catalog(_catalog())
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    payload = b"%PDF-1.7 official test"
    (source_dir / "dpwh-test-app.pdf").write_bytes(payload)

    documents = acquire_official_documents(
        catalog,
        source_dir=source_dir,
        archive=ArtifactArchive(tmp_path / "archive"),
        retrieved_at="2026-11-05T10:00:00+00:00",
        extract_text=lambda _path: "24DD0136 DAGATAN SAN JOSE",
    )

    assert len(documents) == 1
    assert documents[0].payload == payload
    assert documents[0].artifact_sha256 == documents[0].artifact_sha256.lower()
    assert (tmp_path / "archive" / "blobs" / documents[0].artifact_sha256).read_bytes() == payload


def test_rejects_catalog_with_duplicate_sources_or_unsafe_urls() -> None:
    raw = json.loads(_catalog())
    raw["sources"].append(dict(raw["sources"][0]))
    with pytest.raises(OfficialAcquisitionError, match="duplicate"):
        load_official_source_catalog(json.dumps(raw).encode())

    raw = json.loads(_catalog())
    raw["sources"][0]["source_url"] = "https://example.com/test.pdf"
    with pytest.raises(OfficialAcquisitionError, match="official DPWH"):
        load_official_source_catalog(json.dumps(raw).encode())


def test_rejects_missing_or_non_pdf_download(tmp_path: Path) -> None:
    catalog = load_official_source_catalog(_catalog())
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    archive = ArtifactArchive(tmp_path / "archive")

    with pytest.raises(OfficialAcquisitionError, match="missing"):
        acquire_official_documents(
            catalog,
            source_dir=source_dir,
            archive=archive,
            retrieved_at="2026-11-05T10:00:00+00:00",
            extract_text=lambda _path: "text",
        )
    (source_dir / "dpwh-test-app.pdf").write_bytes(b"not a pdf")
    with pytest.raises(OfficialAcquisitionError, match="PDF"):
        acquire_official_documents(
            catalog,
            source_dir=source_dir,
            archive=archive,
            retrieved_at="2026-11-05T10:00:00+00:00",
            extract_text=lambda _path: "text",
        )

def test_downloads_only_pdf_bytes_from_exact_catalog_url(tmp_path: Path) -> None:
    catalog = load_official_source_catalog(_catalog())

    class Fetcher:
        def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
            return Acquisition(
                source_id="dpwh-documents",
                source_url=url,
                retrieved_at=retrieved_at,
                media_type="application/pdf",
                payload=b"%PDF-1.7 downloaded",
            )

    manifest = download_official_sources(
        catalog,
        destination=tmp_path,
        fetcher=Fetcher(),
        retrieved_at=datetime(2026, 11, 5, 10, tzinfo=UTC),
    )

    assert manifest[0]["source_id"] == "dpwh-test-app"
    assert (tmp_path / "dpwh-test-app.pdf").read_bytes().startswith(b"%PDF-")


def test_rejects_download_redirect_or_non_pdf_payload(tmp_path: Path) -> None:
    catalog = load_official_source_catalog(_catalog())

    class Fetcher:
        def __init__(self, *, redirected: bool) -> None:
            self.redirected = redirected

        def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
            return Acquisition(
                source_id="dpwh-documents",
                source_url="https://example.com/escape.pdf" if self.redirected else url,
                retrieved_at=retrieved_at,
                media_type="application/pdf",
                payload=b"%PDF-1.7" if self.redirected else b"blocked html",
            )

    with pytest.raises(OfficialAcquisitionError, match="URL changed"):
        download_official_sources(
            catalog,
            destination=tmp_path,
            fetcher=Fetcher(redirected=True),
            retrieved_at=datetime(2026, 11, 5, 10, tzinfo=UTC),
        )
    with pytest.raises(OfficialAcquisitionError, match="PDF"):
        download_official_sources(
            catalog,
            destination=tmp_path,
            fetcher=Fetcher(redirected=False),
            retrieved_at=datetime(2026, 11, 5, 10, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.update({"schema_version": 2}), "unsupported"),
        (lambda raw: raw.update({"sources": []}), "contain sources"),
        (lambda raw: raw["sources"].__setitem__(0, "bad"), "sources must be objects"),
        (
            lambda raw: raw["sources"][0].update({"document_type": "unknown"}),
            "document_type",
        ),
        (lambda raw: raw["sources"][0].update({"bindings": []}), "non-empty list"),
        (lambda raw: raw["sources"][0]["bindings"].__setitem__(0, "bad"), "objects"),
        (
            lambda raw: raw["sources"][0]["bindings"][0].update(
                {"evidence_type": "unknown"}
            ),
            "evidence_type",
        ),
        (
            lambda raw: raw["sources"][0]["bindings"][0].update(
                {"evidence_class": "unknown"}
            ),
            "evidence_class",
        ),
        (
            lambda raw: raw["sources"][0]["bindings"][0].update(
                {"identity_terms": []}
            ),
            "identity_terms",
        ),
    ],
)
def test_rejects_invalid_catalog_boundaries(mutate: object, message: str) -> None:
    raw = json.loads(_catalog())
    mutate(raw)  # type: ignore[operator]
    with pytest.raises(OfficialAcquisitionError, match=message):
        load_official_source_catalog(json.dumps(raw).encode())


def test_rejects_invalid_json_and_download_timestamps(tmp_path: Path) -> None:
    with pytest.raises(OfficialAcquisitionError, match="JSON"):
        load_official_source_catalog(b"{")
    catalog = load_official_source_catalog(_catalog())

    class Fetcher:
        def fetch_url(self, url: str, retrieved_at: datetime) -> Acquisition:
            raise AssertionError((url, retrieved_at))

    with pytest.raises(OfficialAcquisitionError, match="timezone-aware"):
        download_official_sources(
            catalog,
            destination=tmp_path,
            fetcher=Fetcher(),
            retrieved_at=datetime(2026, 11, 5, 10),
        )


def test_rejects_empty_extracted_text_and_bad_review_time(tmp_path: Path) -> None:
    catalog = load_official_source_catalog(_catalog())
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "dpwh-test-app.pdf").write_bytes(b"%PDF-1.7 test")
    archive = ArtifactArchive(tmp_path / "archive")
    with pytest.raises(OfficialAcquisitionError, match="ISO timestamp"):
        acquire_official_documents(
            catalog,
            source_dir=source_dir,
            archive=archive,
            retrieved_at="invalid",
            extract_text=lambda _path: "text",
        )
    with pytest.raises(OfficialAcquisitionError, match="timezone-aware"):
        acquire_official_documents(
            catalog,
            source_dir=source_dir,
            archive=archive,
            retrieved_at="2026-11-05T10:00:00",
            extract_text=lambda _path: "text",
        )
    with pytest.raises(OfficialAcquisitionError, match="text is empty"):
        acquire_official_documents(
            catalog,
            source_dir=source_dir,
            archive=archive,
            retrieved_at="2026-11-05T10:00:00+00:00",
            extract_text=lambda _path: "",
        )
