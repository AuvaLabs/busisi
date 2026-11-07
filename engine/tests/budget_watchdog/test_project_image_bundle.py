import json

import pytest

from engine.budget_watchdog.project_image_bundle import (
    AcquiredProjectImage,
    build_project_image_bundle,
)
from engine.budget_watchdog.project_images import (
    ProjectImageCoverage,
    ProjectImageRecord,
    inspect_jpeg,
)

JPEG = (
    b"\xff\xd8\xff\xc0\x00\x11\x08\x01\x2c\x02\x58\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9"
)


def _coverage(contract_id: str, state: str = "verified_exact") -> ProjectImageCoverage:
    return ProjectImageCoverage(
        contract_id=contract_id,
        summary_count=1,
        endpoint_count=1,
        has_images=True,
        state=state,
        detail_sha256="a" * 64,
        list_sha256="b" * 64,
        note="Counts reconcile." if state == "verified_exact" else "Counts conflict.",
    )


def _image(contract_id: str, image_id: str, source_path) -> AcquiredProjectImage:
    inspection = inspect_jpeg(JPEG, "image/jpeg")
    return AcquiredProjectImage(
        metadata=ProjectImageRecord(
            image_id=image_id,
            contract_id=contract_id,
            component_id="COMPONENT-1",
            source_url=(
                "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/"
                f"{contract_id}/{image_id}.jpg"
            ),
            thumbnail_source_url=(
                "https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/width=400/"
                "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/"
                f"{contract_id}/{image_id}.jpg"
            ),
            purpose="progress",
            status="On-going",
            captured_at="2026-11-03 10:00:00",
            fiscal_year="FY2024",
            photo_number=1,
            latitude=10.7,
            longitude=124.0,
            coordinate_status="within_broad_philippine_bounds",
        ),
        inspection=inspection,
        archive_key=f"project-images/{contract_id}/{image_id}.jpg",
        source_path=source_path,
    )


def test_builds_atomic_verified_and_quarantined_image_bundle(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(JPEG)
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "stale").write_text("replace me", encoding="utf-8")
    images = (
        _image("24EXACT1", "1" * 64, source),
        _image("24HELD01", "2" * 64, source),
    )

    result = build_project_image_bundle(
        (_coverage("24EXACT1"), _coverage("24HELD01", "count_conflict")),
        images,
        "2026-11-03T10:00:00+00:00",
        output,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    sql = (output / "project-images.sql").read_text(encoding="utf-8")
    assert result.contract_count == 2
    assert result.verified_image_count == 1
    assert result.quarantined_image_count == 1
    assert len(result.sql_sha256) == 64
    assert len(result.manifest_sha256) == 64
    assert manifest["image_count"] == 2
    assert len(manifest["media"]) == 2
    assert {item["archive_key"] for item in manifest["media"]} == {
        images[0].archive_key,
        images[1].archive_key,
    }
    media_files = tuple((output / "media").iterdir())
    assert len(media_files) == 1
    assert media_files[0].stat().st_ino == source.stat().st_ino
    assert "'verified'" in sql
    assert "'quarantine'" in sql
    assert not (output / "stale").exists()


def test_rejects_duplicate_missing_empty_and_tampered_inputs(tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(JPEG)
    exact = _coverage("24EXACT1")
    image = _image("24EXACT1", "1" * 64, source)

    with pytest.raises(ValueError, match="duplicate contracts"):
        build_project_image_bundle(
            (exact, exact), (image,), "2026-11-03T10:00:00+00:00", tmp_path / "a"
        )
    with pytest.raises(ValueError, match="no coverage"):
        build_project_image_bundle((), (image,), "2026-11-03T10:00:00+00:00", tmp_path / "b")

    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="payload is empty"):
        build_project_image_bundle(
            (exact,),
            (_image("24EXACT1", "2" * 64, empty),),
            "2026-11-03T10:00:00+00:00",
            tmp_path / "c",
        )

    source.write_bytes(JPEG + b"tampered")
    with pytest.raises(ValueError, match="does not match"):
        build_project_image_bundle((exact,), (image,), "2026-11-03T10:00:00+00:00", tmp_path / "d")


def test_media_materialization_falls_back_to_copy(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(JPEG)

    def unavailable_link(*_args) -> None:
        raise OSError("hard links unavailable")

    monkeypatch.setattr("engine.budget_watchdog.project_image_bundle.os.link", unavailable_link)
    output = tmp_path / "bundle"
    build_project_image_bundle(
        (_coverage("24EXACT1"),),
        (_image("24EXACT1", "1" * 64, source),),
        "2026-11-03T10:00:00+00:00",
        output,
    )

    media = next((output / "media").iterdir())
    assert media.read_bytes() == JPEG
    assert media.stat().st_ino != source.stat().st_ino
