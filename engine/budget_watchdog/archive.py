"""Content-addressed immutable storage for acquired source artifacts."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


class ArtifactConflictError(RuntimeError):
    """Raised when an existing immutable record conflicts with new evidence."""


@dataclass(frozen=True, slots=True)
class Acquisition:
    source_id: str
    source_url: str
    retrieved_at: datetime
    media_type: str
    payload: bytes
    source_version: str | None = None
    source_last_modified: datetime | None = None


@dataclass(frozen=True, slots=True)
class ArchivedArtifact:
    sha256: str
    byte_size: int
    blob_path: Path
    manifest_path: Path


class ArtifactArchive:
    def __init__(self, root: Path) -> None:
        self._root = root

    def store(self, acquisition: Acquisition) -> ArchivedArtifact:
        self._validate(acquisition)
        digest = hashlib.sha256(acquisition.payload).hexdigest()
        blob_path = self._root / "blobs" / digest
        manifest_path = self._manifest_path(acquisition, digest)
        manifest_bytes = self._manifest_bytes(acquisition, digest)

        self._write_immutable(blob_path, acquisition.payload)
        self._write_immutable(manifest_path, manifest_bytes)
        return ArchivedArtifact(
            sha256=digest,
            byte_size=len(acquisition.payload),
            blob_path=blob_path,
            manifest_path=manifest_path,
        )

    def _manifest_path(self, acquisition: Acquisition, digest: str) -> Path:
        timestamp = acquisition.retrieved_at.isoformat().replace(":", "-")
        filename = f"{timestamp}-{digest}.json"
        return self._root / "manifests" / acquisition.source_id / filename

    @staticmethod
    def _manifest_bytes(acquisition: Acquisition, digest: str) -> bytes:
        manifest = {
            "byte_size": len(acquisition.payload),
            "media_type": acquisition.media_type,
            "retrieved_at": acquisition.retrieved_at.isoformat(),
            "sha256": digest,
            "source_id": acquisition.source_id,
            "source_last_modified": (
                acquisition.source_last_modified.isoformat()
                if acquisition.source_last_modified is not None
                else None
            ),
            "source_url": acquisition.source_url,
            "source_version": acquisition.source_version,
        }
        return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    @staticmethod
    def _write_immutable(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as output:
                output.write(payload)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ArtifactConflictError(f"immutable artifact conflicts at {path}") from None

    @staticmethod
    def _validate(acquisition: Acquisition) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", acquisition.source_id):
            raise ValueError("source_id must be a lowercase slug")
        parsed = urlparse(acquisition.source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("source_url must use HTTPS")
        if acquisition.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if (
            acquisition.source_last_modified is not None
            and acquisition.source_last_modified.tzinfo is None
        ):
            raise ValueError("source_last_modified must be timezone-aware")
        if acquisition.source_version is not None and not acquisition.source_version.strip():
            raise ValueError("source_version must not be empty")
        if not acquisition.media_type.strip():
            raise ValueError("media_type must not be empty")
        if not isinstance(acquisition.payload, bytes) or not acquisition.payload:
            raise ValueError("payload must contain bytes")
