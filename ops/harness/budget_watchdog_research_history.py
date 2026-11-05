"""Build the public research correction and release-history register."""

from __future__ import annotations

import json
from pathlib import Path

from engine.budget_watchdog.research_history import build_release_history

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT / "cloudflare" / "busisi" / "public" / "data" / "research"
NOTES_PATH = ROOT / "ops" / "harness" / "fixtures" / "research_release_notes.json"
OUTPUT_PATH = PUBLIC_ROOT / "release-history.json"


def main() -> None:
    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    history = build_release_history(PUBLIC_ROOT, notes)
    OUTPUT_PATH.write_text(
        json.dumps(history, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": True,
                "story_count": history["story_count"],
                "release_count": history["release_count"],
                "correction_count": history["correction_count"],
                "output": str(OUTPUT_PATH),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
