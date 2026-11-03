import json

import pytest

from engine.budget_watchdog.project_images import (
    inspect_jpeg,
    parse_project_image_evidence,
)


def _payload(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _detail(count: int = 1, has_images: bool = True) -> bytes:
    return _payload(
        {
            "status": 200,
            "data": {
                "contractId": "24HI0148",
                "imageSummary": {
                    "totalImages": count,
                    "latestImageDate": "2025-04-08 01:03:50.040999",
                    "hasImages": has_images,
                },
            },
        }
    )


def _image(url: str | None = None) -> dict[str, object]:
    source = url or (
        "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/"
        "P00833283VS-CW1/1_77382f88-156f-4808-929f-e0d0f7d41061.jpg"
    )
    return {
        "componentId": "P00833283VS-CW1",
        "url": source,
        "thumbnailUrl": (
            "https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/"
            "width=400,height=400,fit=cover/"
            f"{source}"
        ),
        "purpose": "completion",
        "status": "Completed",
        "capturedAt": "2025-04-08 01:03:50.040999",
        "fiscalYear": "FY2024",
        "photoNumber": 1,
        "coordinates": {"latitude": 10.7218472, "longitude": 124.0110944},
    }


def _images(records: list[dict[str, object]]) -> bytes:
    return _payload({"status": 200, "data": {"images": records}})


def test_parses_exact_project_image_metadata_with_provenance() -> None:
    coverage, records = parse_project_image_evidence("24HI0148", _detail(), _images([_image()]))

    assert coverage.state == "verified_exact"
    assert coverage.summary_count == 1
    assert coverage.endpoint_count == 1
    assert len(coverage.detail_sha256) == 64
    assert len(coverage.list_sha256) == 64
    assert len(records) == 1
    assert records[0].component_id == "P00833283VS-CW1"
    assert records[0].coordinate_status == "within_broad_philippine_bounds"
    assert records[0].captured_at == "2025-04-08 01:03:50.040999"
    assert len(records[0].image_id) == 64


def test_quarantines_source_count_conflicts_without_discarding_metadata() -> None:
    second = _image(
        "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/"
        "P00833283VS-CW1/2_b376d2b5-b8e9-4cee-9b46-5dafdb74c595.jpg"
    )
    second["photoNumber"] = 2
    coverage, records = parse_project_image_evidence(
        "24HI0148", _detail(count=1), _images([_image(), second])
    )

    assert coverage.state == "count_conflict"
    assert coverage.summary_count == 1
    assert coverage.endpoint_count == 2
    assert len(records) == 2


def test_accepts_an_explicit_zero_image_state() -> None:
    coverage, records = parse_project_image_evidence(
        "24HI0148", _detail(count=0, has_images=False), _images([])
    )

    assert coverage.state == "no_images"
    assert records == ()


def test_rejects_untrusted_image_origins_and_contract_drift() -> None:
    with pytest.raises(ValueError, match="registered DPWH media origin"):
        parse_project_image_evidence(
            "24HI0148", _detail(), _images([_image("https://example.test/image.jpg")])
        )
    drifted = json.loads(_detail())
    drifted["data"]["contractId"] = "24HI0131"
    with pytest.raises(ValueError, match="contract identifier"):
        parse_project_image_evidence("24HI0148", _payload(drifted), _images([_image()]))


def test_reads_jpeg_dimensions_and_rejects_non_images() -> None:
    jpeg = (
        b"\xff\xd8"
        b"\xff\xc0\x00\x11\x08\x01\x2c\x02\x58\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        b"\xff\xd9"
    )
    inspection = inspect_jpeg(jpeg, "image/jpeg")

    assert inspection.width == 600
    assert inspection.height == 300
    assert inspection.byte_size == len(jpeg)
    assert len(inspection.sha256) == 64
    with pytest.raises(ValueError, match="JPEG"):
        inspect_jpeg(b"not an image", "image/jpeg")
    with pytest.raises(ValueError, match="media type"):
        inspect_jpeg(jpeg, "text/html")
