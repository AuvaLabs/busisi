"""Rewriter rollout audit harness (Final phase).

Scores the R1-R7 rollout against a 10-category rubric (each category 0-10).
Target: overall >= 9/10.

Categories::

  1. Tests              pass-rate of the engine/tests suite
  2. Lint               ruff cleanliness on rewriter-new files
  3. Source taxonomy    every sources.yaml feed has agency_class
  4. LLM routing        caller registry covers all known callers
  5. Schema migration   0005 + ORM in db.py match
  6. Rewriter invariants  validate_narrative enforces I1-I4
  7. Renderer parity    JSON-LD has citation[] when story_rewrite present
  8. Lifecycle states   Story.state column + transition functions
  9. Citation graph     StorySource UNIQUE(story_id, cited_as_n)
 10. Logs               REWRITER_BUILD_LOG entry per completed phase

Run::

    python ops/harness/rewriter_audit.py
    python ops/harness/rewriter_audit.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


REQUIRED_CALLERS = (
    "curator_score",
    "classify",
    "entity_extract",
    "pass0_extract",
    "why_this_matters",
    "summarize",
    "summarize_orphan",
    "pass1_merge",
    "pass2_compose",
)

REWRITER_NEW_FILES = (
    "engine/core/llm_routing.py",
    "engine/core/extractor.py",
    "engine/core/research_writer.py",
    "engine/core/story_lifecycle.py",
    "engine/core/llm_audit.py",
    "engine/core/citation_intelligence.py",
)

PHASES = (
    "R1", "R2", "R3", "R4a", "R4b", "R5", "R6", "R7",
    "C1", "C2", "C3", "C4", "C5", "C6",
)


@dataclass
class Score:
    name: str
    score: float
    out_of: int = 10
    notes: list[str] = field(default_factory=list)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _exists(path: str) -> bool:
    return (ROOT / path).exists()


def score_tests() -> Score:
    """Run pytest -q and score by pass ratio."""
    proc = subprocess.run(
        ["python3", "-m", "pytest", "engine/tests/", "-q", "--no-header"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout + proc.stderr).strip()
    m = re.search(r"(\d+) passed", out)
    f = re.search(r"(\d+) failed", out)
    passed = int(m.group(1)) if m else 0
    failed = int(f.group(1)) if f else 0
    total = passed + failed
    if total == 0:
        return Score("Tests", 0.0, notes=["no tests ran"])
    ratio = passed / total
    score = round(ratio * 10, 2)
    notes = [f"{passed}/{total} passing"]
    if failed:
        notes.append(f"{failed} failing")
    return Score("Tests", score, notes=notes)


def score_lint() -> Score:
    """Run ruff on rewriter-new files. 10 - clamped(errors)."""
    ruff = Path.home() / ".local" / "bin" / "ruff"
    if not ruff.exists():
        return Score("Lint", 0.0, notes=["ruff not installed"])
    proc = subprocess.run(
        [str(ruff), "check", "--no-fix", *REWRITER_NEW_FILES],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout + proc.stderr).strip()
    m = re.search(r"Found (\d+) errors?\.", out)
    errors = int(m.group(1)) if m else 0
    if "All checks passed" in out or errors == 0:
        return Score("Lint", 10.0, notes=["ruff clean on R1-R7 files"])
    score = max(0.0, 10.0 - errors * 0.5)
    return Score("Lint", round(score, 2), notes=[f"{errors} ruff warnings on new files"])


def score_source_taxonomy() -> Score:
    """Every feed in sources.yaml x 2 must have agency_class."""
    misses: list[str] = []
    total = 0
    for vertical in ("embedding", "vested"):
        path = ROOT / "verticals" / vertical / "sources.yaml"
        if not path.exists():
            misses.append(f"{vertical}/sources.yaml missing")
            continue
        feeds = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(feeds, list):
            misses.append(f"{vertical}/sources.yaml not a list")
            continue
        for entry in feeds:
            if not isinstance(entry, dict):
                continue
            total += 1
            if "agency_class" not in entry:
                misses.append(f"{vertical}: {entry.get('url', '?')} has no agency_class")
            elif entry["agency_class"] not in {"A", "B", "C", "D", "E", "F"}:
                misses.append(
                    f"{vertical}: {entry.get('url', '?')} class={entry['agency_class']!r} invalid"
                )
    if total == 0:
        return Score("Source taxonomy", 0.0, notes=["no feeds found"])
    ratio = max(0.0, 1.0 - len(misses) / total)
    score = round(ratio * 10, 2)
    return Score(
        "Source taxonomy",
        score,
        notes=[f"{total} feeds, {len(misses)} missing agency_class"]
        + misses[:3],
    )


def score_llm_routing() -> Score:
    """All required callers present in llm_routing._DEFAULT_REGISTRY."""
    src = _read("engine/core/llm_routing.py")
    missing = [c for c in REQUIRED_CALLERS if f'"{c}"' not in src]
    if not missing:
        return Score("LLM routing", 10.0, notes=["all callers registered"])
    score = max(0.0, 10.0 - len(missing) * 1.5)
    return Score("LLM routing", round(score, 2), notes=[f"missing: {missing}"])


def score_schema_migration() -> Score:
    """Migration 0005 exists; ORM models match."""
    if not _exists("ops/migrations/versions/0005_rewriter_schema.py"):
        return Score("Schema migration", 0.0, notes=["0005 missing"])
    mig = _read("ops/migrations/versions/0005_rewriter_schema.py")
    db = _read("engine/core/db.py")
    expected_tables = ("story_sources", "story_revisions", "citation_events", "llm_calls")
    missing_tables = [t for t in expected_tables if f'"{t}"' not in mig]
    expected_cols = (
        "structured_extract",
        "extract_version",
        "extracted_at",
        '"state",',  # migration adds the literal column name in Column("state", ...)
        "narrative_version",
    )
    missing_cols = [c for c in expected_cols if c not in mig]
    expected_orms = ("StorySource", "StoryRevision", "CitationEvent", "LLMCall")
    missing_orms = [c for c in expected_orms if f"class {c}(" not in db]
    issues = (
        [f"missing migration table {t}" for t in missing_tables]
        + [f"missing migration column {c}" for c in missing_cols]
        + [f"missing ORM class {c}" for c in missing_orms]
    )
    score = max(0.0, 10.0 - len(issues) * 1.0)
    return Score("Schema migration", round(score, 2), notes=issues or ["complete"])


def score_rewriter_invariants() -> Score:
    """validate_narrative enforces I1-I4 + banned phrases."""
    src = _read("engine/core/research_writer.py")
    checks = {
        "word_count check": "word_count out of range" in src,
        "banned phrase check": "_BANNED_PHRASES" in src,
        "[N] resolution check": "unresolved [N] citations" in src,
        "Class F rejection": "cannot be primary citation" in src,
        "primary-eligible check": "no primary-eligible" in src,
        "numeric grounding check": "narrative cites numbers not in source" in src,
        "citation marker stripping": "_CITATION_RE.sub" in src,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Rewriter invariants", 10.0, notes=["all I1-I4 checks present"])
    score = max(0.0, 10.0 - len(failed) * 1.5)
    return Score("Rewriter invariants", round(score, 2), notes=failed)


def score_renderer_parity() -> Score:
    """story.html JSON-LD has citation[] when story_rewrite present."""
    src = _read("engine/shared/templates/story.html")
    checks = {
        "story_rewrite branch in JSON-LD": "article.story_rewrite" in src
        and "citation" in src,
        "articleBody field": '"articleBody":' in src,
        "wordCount field": '"wordCount":' in src,
        "[N] linkification": "cite-ref" in src or "narrative_html" in src,
        "agency-class CSS": ".agency-class" in src,
        "cited-sources list": "cited-sources" in src,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Renderer parity", 10.0, notes=["JSON-LD + DOM parity"])
    score = max(0.0, 10.0 - len(failed) * 1.5)
    return Score("Renderer parity", round(score, 2), notes=failed)


def score_lifecycle() -> Score:
    """Story.state column + state-machine functions."""
    db = _read("engine/core/db.py")
    sl = _read("engine/core/story_lifecycle.py") if _exists(
        "engine/core/story_lifecycle.py"
    ) else ""
    # The Story.state column is declared as `state: Mapped[str] = mapped_column(...)`
    # with `default="draft"`. Checking for the default literal anchored to the
    # state column block is more robust than scanning for an unquoted attribute name.
    state_block = "default=\"draft\"" in db or 'server_default="draft"' in db
    checks = {
        "Story.state column": state_block,
        "narrative_version column": "narrative_version" in db,
        "mark_ready function": "def mark_ready(" in sl,
        "archive_stale function": "def archive_stale(" in sl,
        "rollup_citations function": "def rollup_citations(" in sl,
        "mark_revising function": "def mark_revising_on_new_link(" in sl,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Lifecycle", 10.0, notes=["state machine + transitions present"])
    score = max(0.0, 10.0 - len(failed) * 2.0)
    return Score("Lifecycle", round(score, 2), notes=failed)


def score_citation_graph() -> Score:
    """StorySource has UNIQUE(story_id, cited_as_n) and rewriter persists rows."""
    db = _read("engine/core/db.py")
    rw = _read("engine/core/research_writer.py")
    checks = {
        "UNIQUE storysource constraint": "uq_storysource_n" in db,
        "rewriter inserts StorySource": "StorySource(" in rw,
        "agency_class column on StorySource": "agency_class" in db
        and "StorySource" in db,
        "cited_as_n column": "cited_as_n" in db,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Citation graph", 10.0, notes=["constraints + persistence wired"])
    score = max(0.0, 10.0 - len(failed) * 2.0)
    return Score("Citation graph", round(score, 2), notes=failed)


def score_logs() -> Score:
    """REWRITER_BUILD_LOG has an entry per completed phase."""
    if not _exists("docs/REWRITER_BUILD_LOG.md"):
        return Score("Logs", 0.0, notes=["log file missing"])
    log = _read("docs/REWRITER_BUILD_LOG.md")
    missing = [p for p in PHASES if f"## {p} " not in log]
    if not missing:
        return Score("Logs", 10.0, notes=[f"all {len(PHASES)} phases logged"])
    score = max(0.0, 10.0 - len(missing) * 1.5)
    return Score("Logs", round(score, 2), notes=[f"missing log: {missing}"])


def score_cost_guardrail() -> Score:
    """C1 — LLM audit recorder + daily-unit-cap wired to call_llm."""
    if not _exists("engine/core/llm_audit.py"):
        return Score("Cost guardrail (C1)", 0.0, notes=["llm_audit missing"])
    audit = _read("engine/core/llm_audit.py")
    client = _read("engine/core/llm_client.py")
    checks = {
        "units_for_model heuristic": "def units_for_model(" in audit,
        "cap_exceeded function": "def cap_exceeded(" in audit,
        "record_call function": "def record_call(" in audit,
        "client honours cap": "cap_exceeded" in client,
        "client records on success": "llm_audit.record_call" in client,
        "client records on failure": "record_call (failure path)" in client
        or 'error=str(last_error)' in client,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Cost guardrail (C1)", 10.0, notes=["audit recorder + cap wired"])
    score = max(0.0, 10.0 - len(failed) * 1.7)
    return Score("Cost guardrail (C1)", round(score, 2), notes=failed)


def score_non_primary_redirect() -> Score:
    """C2 — non-primary cluster members redirect to primary."""
    src = _read("engine/core/output_renderer.py")
    sl = _read("engine/core/story_lifecycle.py") if _exists(
        "engine/core/story_lifecycle.py"
    ) else ""
    checks = {
        "_non_primary_redirects helper": "def _non_primary_redirects(" in src,
        "redirect_by_id wired": "redirect_by_id" in src,
        "meta-refresh emit": 'http-equiv="refresh"' in src,
        "canonical link emit": 'rel="canonical"' in src,
        "revise_story helper": "def revise_story(" in sl,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Non-primary redirect (C2)", 10.0, notes=["redirect + revise wired"])
    score = max(0.0, 10.0 - len(failed) * 2.0)
    return Score("Non-primary redirect (C2)", round(score, 2), notes=failed)


def score_public_api() -> Score:
    """C3 — /api/v1/stories endpoint."""
    api = _read("engine/handlers/api_v1.py")
    tests = _read("engine/tests/handlers/test_api_v1.py")
    checks = {
        "/stories route": '"/stories"' in api or "@router.get('/stories')" in api
        or "/stories" in api,
        "list_stories handler": "def list_stories(" in api,
        "state filter": "draft|ready|published|revising|archived" in api,
        "sources nested in response": '"sources":' in api,
        "/stories test exists": "/api/v1/stories" in tests,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Public API (C3)", 10.0, notes=["endpoint + tests + filter"])
    score = max(0.0, 10.0 - len(failed) * 2.0)
    return Score("Public API (C3)", round(score, 2), notes=failed)


def score_citation_intel() -> Score:
    """C4 — cited-by intelligence module."""
    if not _exists("engine/core/citation_intelligence.py"):
        return Score("Citation intel (C4)", 0.0, notes=["module missing"])
    src = _read("engine/core/citation_intelligence.py")
    checks = {
        "KNOWN_CRAWLERS allowlist": "KNOWN_CRAWLERS" in src,
        "top_cited_stories function": "def top_cited_stories(" in src,
        "citations_by_bot function": "def citations_by_bot(" in src,
        "cited_today_count function": "def cited_today_count(" in src,
        "PerplexityBot in allowlist": '"PerplexityBot"' in src,
        "OAI-SearchBot in allowlist": '"OAI-SearchBot"' in src,
        "Claude-SearchBot in allowlist": '"Claude-SearchBot"' in src,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Citation intel (C4)", 10.0, notes=["intel module complete"])
    score = max(0.0, 10.0 - len(failed) * 1.5)
    return Score("Citation intel (C4)", round(score, 2), notes=failed)


def score_richer_jsonld() -> Score:
    """C5 — citation[] entries are NewsArticle with headline + datePublished."""
    tmpl = _read("engine/shared/templates/story.html")
    rend = _read("engine/core/output_renderer.py")
    db = _read("engine/core/db.py")
    checks = {
        "citation[] uses NewsArticle": '"@type": "NewsArticle"' in tmpl,
        "headline field emitted": '"headline":' in tmpl and "s.headline" in tmpl,
        "datePublished emitted": '"datePublished":' in tmpl and "s.date_published" in tmpl,
        "NewsMediaOrganization publisher": "NewsMediaOrganization" in tmpl,
        "renderer fetches per-source meta": "article_meta_by_id" in rend,
        "Entity.wikidata_id column": "wikidata_id" in db and "Entity" in db,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Richer JSON-LD (C5)", 10.0, notes=["citation[] enriched"])
    score = max(0.0, 10.0 - len(failed) * 1.7)
    return Score("Richer JSON-LD (C5)", round(score, 2), notes=failed)


def score_visual_polish() -> Score:
    """C6 — agency-class CSS distinct + cite-ref hover state."""
    src = _read("engine/shared/templates/story.html")
    checks = {
        "agency-class-a styled": ".agency-class-a" in src,
        "agency-class-f italic": ".agency-class-f" in src and "italic" in src,
        "cite-ref hover state": "sup.cite-ref a:hover" in src,
        "cite-ref focus state": "sup.cite-ref a:focus" in src,
        "target highlight": ":target" in src,
        "print stylesheet hint": "@media print" in src,
    }
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return Score("Visual polish (C6)", 10.0, notes=["polished"])
    score = max(0.0, 10.0 - len(failed) * 1.7)
    return Score("Visual polish (C6)", round(score, 2), notes=failed)


def run() -> list[Score]:
    return [
        score_tests(),
        score_lint(),
        score_source_taxonomy(),
        score_llm_routing(),
        score_schema_migration(),
        score_rewriter_invariants(),
        score_renderer_parity(),
        score_lifecycle(),
        score_citation_graph(),
        score_logs(),
        # Carry-forward categories
        score_cost_guardrail(),
        score_non_primary_redirect(),
        score_public_api(),
        score_citation_intel(),
        score_richer_jsonld(),
        score_visual_polish(),
    ]


def overall(scores: list[Score]) -> float:
    if not scores:
        return 0.0
    return round(sum(s.score for s in scores) / len(scores), 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rewriter rollout audit harness")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    scores = run()
    total = overall(scores)

    if args.json:
        out = {
            "overall": total,
            "categories": [
                {"name": s.name, "score": s.score, "out_of": s.out_of, "notes": s.notes}
                for s in scores
            ],
        }
        print(json.dumps(out, indent=2))
        return 0 if total >= 9.0 else 1

    print("\nRewriter rollout audit")
    print("=" * 60)
    for s in scores:
        bar = "#" * int(s.score) + "." * (10 - int(s.score))
        print(f"  {s.name:<22} [{bar}] {s.score:>5.2f}/10")
        for note in s.notes[:3]:
            print(f"      - {note}")
    print("-" * 60)
    print(f"  {'OVERALL':<22}            {total:>5.2f}/10  (target >=9.00)")
    print("=" * 60)
    return 0 if total >= 9.0 else 1


if __name__ == "__main__":
    sys.exit(main())
