import json

import pytest

from engine.budget_watchdog.project_images import (
    inspect_jpeg,
    parse_project_image_evidence,
    project_image_acquisition_target,
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


def test_accepts_strict_official_infratrack_proxy_attachments() -> None:
    source = (
        "https://apps2.dpwh.gov.ph/proxy_infratrack/proxy.ashx?"
        "https://services1.arcgis.com/IwZZTMxZCmAmFYvF/arcgis/rest/services/"
        "service_6639703e129e41e5952f88f0b8de8bd7/FeatureServer/0/148958/"
        "attachments/321001"
    )
    image = _image(source)
    image["thumbnailUrl"] = source + "?f=image&imagesr=96&w=400&h=400"

    coverage, records = parse_project_image_evidence("24HI0148", _detail(), _images([image]))

    assert coverage.state == "verified_exact"
    assert records[0].source_url == source
    assert project_image_acquisition_target(source) == (
        "dpwh-infratrack-media",
        source.removeprefix("https://apps2.dpwh.gov.ph"),
    )


@pytest.mark.parametrize(
    "source",
    [
        ("https://apps2.dpwh.gov.ph/proxy_infratrack/proxy.ashx?https://example.test/attachment/1"),
        (
            "https://apps2.dpwh.gov.ph/proxy_infratrack/proxy.ashx?"
            "http://services1.arcgis.com/a/arcgis/rest/services/b/FeatureServer/0/1/"
            "attachments/2"
        ),
        (
            "https://apps2.dpwh.gov.ph/proxy_infratrack/proxy.ashx?"
            "https://services1.arcgis.com/a/arcgis/rest/services/b/FeatureServer/0/1/"
            "attachments/2?download=https://example.test"
        ),
    ],
)
def test_rejects_untrusted_infratrack_proxy_targets(source: str) -> None:
    with pytest.raises(ValueError, match="registered DPWH media origin"):
        parse_project_image_evidence("24HI0148", _detail(), _images([_image(source)]))


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


def test_rejects_malformed_metadata_boundaries() -> None:
    with pytest.raises(ValueError, match="invalid contract identifier"):
        parse_project_image_evidence("../bad", _detail(), _images([]))
    with pytest.raises(ValueError, match="valid JSON"):
        parse_project_image_evidence("24HI0148", b"{", _images([]))
    with pytest.raises(ValueError, match="JSON object"):
        parse_project_image_evidence("24HI0148", b"[]", _images([]))

    missing_data = _payload({"status": 200, "data": []})
    with pytest.raises(ValueError, match="project detail data"):
        parse_project_image_evidence("24HI0148", missing_data, _images([]))

    invalid_summary = json.loads(_detail())
    invalid_summary["data"]["imageSummary"]["hasImages"] = "yes"
    with pytest.raises(ValueError, match="hasImages"):
        parse_project_image_evidence("24HI0148", _payload(invalid_summary), _images([_image()]))

    invalid_list = _payload({"status": 200, "data": {"images": {}}})
    with pytest.raises(ValueError, match="must be a list"):
        parse_project_image_evidence("24HI0148", _detail(), invalid_list)

    with pytest.raises(ValueError, match="duplicate source URL"):
        parse_project_image_evidence("24HI0148", _detail(count=2), _images([_image(), _image()]))

    invalid_thumbnail = _image()
    invalid_thumbnail["thumbnailUrl"] = "https://example.test/thumb.jpg"
    with pytest.raises(ValueError, match="thumbnail URL"):
        parse_project_image_evidence("24HI0148", _detail(), _images([invalid_thumbnail]))

    invalid_coordinate = _image()
    invalid_coordinate["coordinates"] = {"latitude": "north", "longitude": 124.0}
    with pytest.raises(ValueError, match="must be numeric"):
        parse_project_image_evidence("24HI0148", _detail(), _images([invalid_coordinate]))


def test_classifies_incomplete_and_outside_coordinates_without_filling_values() -> None:
    incomplete = _image()
    incomplete["purpose"] = None
    incomplete["status"] = None
    incomplete["coordinates"] = {"latitude": None, "longitude": 124.0}
    outside = _image(
        "https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/P00833283VS-CW1/outside.jpg"
    )
    outside["coordinates"] = {"latitude": 40.0, "longitude": 124.0}

    coverage, records = parse_project_image_evidence(
        "24HI0148", _detail(count=2), _images([incomplete, outside])
    )

    assert coverage.state == "verified_exact"
    assert records[0].purpose == ""
    assert records[0].status == ""
    assert records[0].coordinate_status == "incomplete"
    assert records[1].coordinate_status == "outside_broad_philippine_bounds"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff\xd8\x00\x00\x00\x00", "invalid JPEG marker"),
        (b"\xff\xd8\xff\xe0\x00\x01", "invalid JPEG segment"),
        (b"\xff\xd8\xff\xda\x00\x02", "dimensions could not be read"),
        (b"\xff\xd8\xff\xc0\x00\x06\x08\x00\x01\x00", "invalid JPEG frame"),
        (
            b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x00\x02\x58\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00",
            "outside safe bounds",
        ),
    ],
)
def test_rejects_malformed_jpeg_structures(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        inspect_jpeg(payload, "image/jpeg")
