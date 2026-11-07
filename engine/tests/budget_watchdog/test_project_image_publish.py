import threading
import time
from pathlib import Path

import pytest
from ops.harness import budget_watchdog_project_image_publish as publisher


def test_uploads_verified_media_with_bounded_parallelism(monkeypatch, tmp_path) -> None:
    active = 0
    peak = 0
    calls: list[list[str]] = []
    lock = threading.Lock()

    def run(arguments: list[str]) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(arguments)
        time.sleep(0.02)
        with lock:
            active -= 1

    monkeypatch.setattr(publisher, "_run", run)
    uploads = [
        (f"project-images/24TEST/{index}.jpg", Path(tmp_path / f"{index}.jpg"))
        for index in range(publisher.R2_UPLOAD_WORKERS + 2)
    ]

    publisher._upload_media(uploads)

    assert peak == publisher.R2_UPLOAD_WORKERS
    assert len(calls) == len(uploads)
    assert all(call[:5] == ["npx", "wrangler", "r2", "object", "put"] for call in calls)
    assert {
        call[5].removeprefix("busisi-project-evidence/") for call in calls
    } == {key for key, _ in uploads}


def test_skips_executor_when_there_is_no_media(monkeypatch) -> None:
    def fail(_arguments: list[str]) -> None:
        raise AssertionError("no upload command should run")

    monkeypatch.setattr(publisher, "_run", fail)

    publisher._upload_media([])


def test_propagates_media_upload_failure(monkeypatch, tmp_path) -> None:
    def fail(_arguments: list[str]) -> None:
        raise RuntimeError("upload failed")

    monkeypatch.setattr(publisher, "_run", fail)

    with pytest.raises(RuntimeError, match="upload failed"):
        publisher._upload_media([("project-images/24TEST/1.jpg", tmp_path / "1.jpg")])
