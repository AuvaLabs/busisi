"""Validate project-image metadata and archived JPEG evidence."""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast
from urllib.parse import unquote, urlparse

_CONTRACT_ID = re.compile(r"^[A-Z0-9-]{4,40}$")
_MEDIA_HOST = "s3.transparency.dpwh.gov.ph"
_INFRATRACK_HOST = "apps2.dpwh.gov.ph"
_IMAGE_PATH = re.compile(r"^/dpwh-gallery/[A-Za-z0-9_./-]+\.(?:jpe?g)$", re.IGNORECASE)
_INFRATRACK_PATH = "/proxy_infratrack/proxy.ashx"
_INFRATRACK_TARGET = re.compile(
    r"^https://services1\.arcgis\.com/[A-Za-z0-9_-]+/arcgis/rest/services/"
    r"[A-Za-z0-9_-]+/FeatureServer/[0-9]+/[0-9]+/attachments/[0-9]+$"
)
_INFRATRACK_THUMBNAIL_SUFFIX = "?f=image&imagesr=96&w=400&h=400"
_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
_PH_LATITUDE_RANGE = (4.0, 22.5)
_PH_LONGITUDE_RANGE = (116.0, 127.0)
_MIN_JPEG_BYTES = 4
_JPEG_MARKER_PREFIX = 0xFF
_JPEG_START_OF_SCAN = 0xDA
_JPEG_STANDALONE_MARKERS = frozenset({0xD8, 0xD9})
_JPEG_LENGTH_BYTES = 2
_MIN_SOF_SEGMENT_LENGTH = 7
_MAX_IMAGE_DIMENSION = 20_000


@dataclass(frozen=True, slots=True)
class ProjectImageCoverage:
    contract_id: str
    summary_count: int
    endpoint_count: int
    has_images: bool
    state: str
    detail_sha256: str
    list_sha256: str
    note: str


@dataclass(frozen=True, slots=True)
class ProjectImageRecord:
    image_id: str
    contract_id: str
    component_id: str
    source_url: str
    thumbnail_source_url: str
    purpose: str
    status: str
    captured_at: str
    fiscal_year: str
    photo_number: int
    latitude: float | None
    longitude: float | None
    coordinate_status: str


@dataclass(frozen=True, slots=True)
class ImageInspection:
    sha256: str
    byte_size: int
    width: int
    height: int
    content_type: str


def _load_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: Any, label: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer of at least {minimum}")
    return cast(int, value)


def _number_or_none(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric or null")
    return float(value)


def _validate_source_url(value: Any) -> str:
    url = _text(value, "project image URL")
    parsed = urlparse(url)
    common_invalid = (
        parsed.scheme != "https"
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
    )
    direct_media = (
        parsed.hostname == _MEDIA_HOST
        and not parsed.query
        and _IMAGE_PATH.fullmatch(unquote(parsed.path)) is not None
    )
    infratrack_media = (
        parsed.hostname == _INFRATRACK_HOST
        and parsed.path == _INFRATRACK_PATH
        and _INFRATRACK_TARGET.fullmatch(parsed.query) is not None
    )
    if common_invalid or not (direct_media or infratrack_media):
        raise ValueError("project image URL must use the registered DPWH media origin")
    return url


def _validate_thumbnail(value: Any, source_url: str) -> str:
    url = _text(value, "project image thumbnail URL")
    source = urlparse(source_url)
    if source.hostname == _INFRATRACK_HOST:
        if url != source_url + _INFRATRACK_THUMBNAIL_SUFFIX:
            raise ValueError("thumbnail URL must use the registered DPWH media origin")
        return url
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _MEDIA_HOST
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/cdn-cgi/image/")
        or not unquote(parsed.path).endswith(source_url)
    ):
        raise ValueError("thumbnail URL must use the registered DPWH media origin")
    return url


def project_image_acquisition_target(source_url: str) -> tuple[str, str]:
    """Return the registered source and root-relative path for validated media."""
    validated = _validate_source_url(source_url)
    parsed = urlparse(validated)
    if parsed.hostname == _MEDIA_HOST:
        return "dpwh-transparency-media", parsed.path
    return "dpwh-infratrack-media", f"{parsed.path}?{parsed.query}"


def _coordinate_status(latitude: float | None, longitude: float | None) -> str:
    if latitude is None and longitude is None:
        return "not_reported"
    if latitude is None or longitude is None:
        return "incomplete"
    if (
        _PH_LATITUDE_RANGE[0] <= latitude <= _PH_LATITUDE_RANGE[1]
        and _PH_LONGITUDE_RANGE[0] <= longitude <= _PH_LONGITUDE_RANGE[1]
    ):
        return "within_broad_philippine_bounds"
    return "outside_broad_philippine_bounds"


def parse_project_image_evidence(
    contract_id: str, detail_raw: bytes, image_list_raw: bytes
) -> tuple[ProjectImageCoverage, tuple[ProjectImageRecord, ...]]:
    """Parse source metadata while preserving count conflicts for quarantine."""
    contract = contract_id.strip().upper()
    if not _CONTRACT_ID.fullmatch(contract):
        raise ValueError("invalid contract identifier")

    detail_root = _load_object(detail_raw, "project detail response")
    detail = _mapping(detail_root.get("data"), "project detail data")
    if _text(detail.get("contractId"), "project contract identifier").upper() != contract:
        raise ValueError("source contract identifier does not match the requested contract")
    summary = _mapping(detail.get("imageSummary"), "project image summary")
    summary_count = _integer(summary.get("totalImages"), "summary image count")
    has_images = summary.get("hasImages")
    if not isinstance(has_images, bool):
        raise ValueError("summary hasImages must be boolean")

    list_root = _load_object(image_list_raw, "project image response")
    list_data = _mapping(list_root.get("data"), "project image data")
    images = list_data.get("images")
    if not isinstance(images, list):
        raise ValueError("project image records must be a list")

    records: list[ProjectImageRecord] = []
    seen_urls: set[str] = set()
    for index, value in enumerate(images):
        item = _mapping(value, f"project image record {index}")
        source_url = _validate_source_url(item.get("url"))
        if source_url in seen_urls:
            raise ValueError("project image records contain a duplicate source URL")
        seen_urls.add(source_url)
        thumbnail = _validate_thumbnail(item.get("thumbnailUrl"), source_url)
        coordinates = _mapping(item.get("coordinates") or {}, "project image coordinates")
        latitude = _number_or_none(coordinates.get("latitude"), "image latitude")
        longitude = _number_or_none(coordinates.get("longitude"), "image longitude")
        image_id = sha256(f"{contract}\0{source_url}".encode()).hexdigest()
        records.append(
            ProjectImageRecord(
                image_id=image_id,
                contract_id=contract,
                component_id=_text(item.get("componentId"), "image component identifier"),
                source_url=source_url,
                thumbnail_source_url=thumbnail,
                purpose=_text(item.get("purpose"), "image purpose", required=False),
                status=_text(item.get("status"), "image status", required=False),
                captured_at=_text(item.get("capturedAt"), "image capture time"),
                fiscal_year=_text(item.get("fiscalYear"), "image fiscal year"),
                photo_number=_integer(item.get("photoNumber"), "image photo number", minimum=1),
                latitude=latitude,
                longitude=longitude,
                coordinate_status=_coordinate_status(latitude, longitude),
            )
        )

    endpoint_count = len(records)
    if summary_count == 0 and endpoint_count == 0 and not has_images:
        state = "no_images"
        note = "Both source representations report no project images."
    elif summary_count == endpoint_count and endpoint_count > 0 and has_images:
        state = "verified_exact"
        note = "Project detail and image endpoint counts reconcile exactly."
    else:
        state = "count_conflict"
        note = "Source image summary and image endpoint do not reconcile."

    return (
        ProjectImageCoverage(
            contract_id=contract,
            summary_count=summary_count,
            endpoint_count=endpoint_count,
            has_images=has_images,
            state=state,
            detail_sha256=sha256(detail_raw).hexdigest(),
            list_sha256=sha256(image_list_raw).hexdigest(),
            note=note,
        ),
        tuple(records),
    )


def inspect_jpeg(content: bytes, content_type: str) -> ImageInspection:  # noqa: PLR0912
    """Return deterministic JPEG facts without relying on decoder libraries."""
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type not in {"image/jpeg", "image/jpg"}:
        raise ValueError("project evidence media type must be JPEG")
    if len(content) < _MIN_JPEG_BYTES or content[:2] != b"\xff\xd8":
        raise ValueError("project evidence must contain valid JPEG bytes")

    offset = 2
    while offset + 4 <= len(content):
        if content[offset] != _JPEG_MARKER_PREFIX:
            raise ValueError("project evidence contains an invalid JPEG marker")
        while offset < len(content) and content[offset] == _JPEG_MARKER_PREFIX:
            offset += 1
        if offset >= len(content):
            break
        marker = content[offset]
        offset += 1
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if marker == _JPEG_START_OF_SCAN:
            break
        if offset + 2 > len(content):
            break
        segment_length = struct.unpack(">H", content[offset : offset + _JPEG_LENGTH_BYTES])[0]
        if segment_length < _JPEG_LENGTH_BYTES or offset + segment_length > len(content):
            raise ValueError("project evidence contains an invalid JPEG segment")
        if marker in _SOF_MARKERS:
            if segment_length < _MIN_SOF_SEGMENT_LENGTH:
                raise ValueError("project evidence contains an invalid JPEG frame")
            height, width = struct.unpack(">HH", content[offset + 3 : offset + 7])
            if not (0 < width <= _MAX_IMAGE_DIMENSION and 0 < height <= _MAX_IMAGE_DIMENSION):
                raise ValueError("project evidence JPEG dimensions are outside safe bounds")
            return ImageInspection(
                sha256=sha256(content).hexdigest(),
                byte_size=len(content),
                width=width,
                height=height,
                content_type="image/jpeg",
            )
        offset += segment_length
    raise ValueError("project evidence JPEG dimensions could not be read")
