"""Publish one verified project-image bundle to private R2 and public D1."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "budget_watchdog"
DEFAULT_BUNDLE = DATA / "project-image-d1-bundle"
PUBLICATIONS = DATA / "project-image-publications"
CLOUDFLARE = ROOT / "cloudflare" / "busisi"
R2_UPLOAD_WORKERS = 6


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_verified_bundle(bundle: Path) -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    manifest_path = bundle / "manifest.json"
    sql_path = bundle / "project-images.sql"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release = manifest.get("coverage_release")
    if not isinstance(release, dict) or not isinstance(release.get("release_id"), str):
        raise ValueError("bundle has no gated coverage release")
    if _digest(sql_path) != manifest.get("sql_sha256"):
        raise ValueError("bundle SQL does not match its manifest")
    by_key = {item["archive_key"]: item for item in manifest.get("media", [])}
    uploads = []
    for key in manifest.get("publish_media", []):
        item = by_key.get(key)
        if item is None:
            raise ValueError("publishable media is absent from the bundle manifest")
        path = bundle / "media" / f"{item['sha256']}.jpg"
        if (
            not path.is_file()
            or path.stat().st_size != item["byte_size"]
            or _digest(path) != item["sha256"]
        ):
            raise ValueError("publishable media does not match its manifest")
        uploads.append((key, path))
    return manifest, uploads


def _run(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=CLOUDFLARE, check=True)  # noqa: S603


def _upload_media(uploads: list[tuple[str, Path]]) -> None:
    def upload(item: tuple[str, Path]) -> None:
        key, path = item
        _run(
            [
                "npx",
                "wrangler",
                "r2",
                "object",
                "put",
                f"busisi-project-evidence/{key}",
                f"--file={path}",
                "--remote",
                "--config",
                "wrangler.jsonc",
            ]
        )

    if not uploads:
        return
    worker_count = min(R2_UPLOAD_WORKERS, len(uploads))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        tuple(executor.map(upload, uploads))


def publish_bundle(bundle: Path = DEFAULT_BUNDLE) -> str:
    manifest, uploads = _load_verified_bundle(bundle)
    release_id = manifest["coverage_release"]["release_id"]
    marker = PUBLICATIONS / f"{release_id}.json"
    if marker.is_file():
        return release_id
    _upload_media(uploads)
    _run(
        [
            "npx",
            "wrangler",
            "d1",
            "migrations",
            "apply",
            "busisi-publication",
            "--remote",
            "--config",
            "wrangler.jsonc",
        ]
    )
    _run(
        [
            "npx",
            "wrangler",
            "d1",
            "execute",
            "busisi-publication",
            "--remote",
            f"--file={bundle / 'project-images.sql'}",
            "--config",
            "wrangler.jsonc",
        ]
    )
    PUBLICATIONS.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "sql_sha256": manifest["sql_sha256"],
                "uploaded_media": len(uploads),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return release_id


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    return parser.parse_args()


def main() -> int:
    release_id = publish_bundle(arguments().bundle)
    print(json.dumps({"passed": True, "release_id": release_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
