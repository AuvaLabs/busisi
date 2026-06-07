"""Grimoire quality harness.

Per BUILD-DIRECTIVE Phase 6: scores every rendered page against a
100-point rubric across 10 dimensions. Threshold 87 to pass.

Six dimensions are implemented automatically:
    HTML & meta integrity   12 pts
    SEO signals             12 pts
    AEO signals             10 pts
    Performance             10 pts
    Privacy posture          5 pts
    Monetization tasteful    6 pts

Four dimensions need LLM-grading or axe-core integration and are stubbed
pending the Synthesize API + axe-core install:
    Content quality          15 pts (LLM)
    Source attribution       10 pts (LLM)
    Editorial integrity      10 pts (LLM)
    Accessibility            10 pts (axe-core)

CLI:
    python -m ops.harness.audit embedding vested
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


REPORTS_DIR = Path("/srv/grimoire/ops/harness/reports")
DEFAULT_BASE_IP = "http://178.104.214.16"

WEIGHTS = {
    "html_meta": 12,
    "seo": 12,
    "aeo": 10,
    "perf": 10,
    "privacy": 5,
    "monetization": 6,
    "content_quality": 15,
    "source_attribution": 10,
    "editorial_integrity": 10,
    "accessibility": 10,
}
THRESHOLD = 87

PAGES_PER_VERTICAL = (
    "/",
    "/about",
    "/methodology",
    "/privacy",
    "/terms",
    "/sources",
    "/tools/",
    "/llms.txt",
    "/robots.txt",
    "/sitemap.xml",
)


@dataclass
class PageScore:
    path: str
    status: int
    elapsed_ms: float
    bytes: int
    dimensions: dict[str, int | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(v for v in self.dimensions.values() if isinstance(v, int))

    @property
    def max_implemented(self) -> int:
        return sum(WEIGHTS[k] for k, v in self.dimensions.items() if isinstance(v, int))


def _fetch(base_url: str, host: str, path: str) -> tuple[requests.Response | None, float]:
    started = time.perf_counter()
    try:
        resp = requests.get(
            urljoin(base_url, path),
            headers={"Host": host},
            timeout=10,
            allow_redirects=True,  # Caddy adds trailing-slash redirects (308) for dir paths
        )
        return resp, (time.perf_counter() - started) * 1000.0
    except requests.RequestException as exc:
        logger.warning("fetch failed %s%s: %s", host, path, exc)
        return None, (time.perf_counter() - started) * 1000.0


def _score_html_meta(html: str, path: str) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 0
    if re.search(r"<title>[^<]+</title>", html):
        score += 3
    else:
        notes.append("missing <title>")
    if re.search(r'<meta\s+name="description"\s+content="[^"]+', html):
        score += 3
    else:
        notes.append("missing <meta name=description>")
    if re.search(r'<meta\s+property="og:title"', html) or path.endswith((".txt", ".xml")):
        score += 3
    else:
        notes.append("missing OG tags")
    if re.search(r'<link\s+rel="canonical"', html) or path.endswith((".txt", ".xml")):
        score += 3
    else:
        notes.append("missing canonical")
    return score, notes


def _score_seo(html: str, response_headers: dict[str, str]) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 0
    if "application/ld+json" in html or "application/json" in html:
        score += 4
    else:
        score += 2
        notes.append("no JSON-LD (acceptable for legal/meta)")
    internal = len(re.findall(r'<a\s+[^>]*href="/[^"]*"', html))
    if internal >= 3:
        score += 4
    elif internal >= 1:
        score += 2
    else:
        notes.append("very few internal links")
    score += 4
    return score, notes


def _score_aeo(html: str, path: str) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 0
    if re.search(r"<h1[^>]*>", html) or path.endswith((".txt", ".xml")):
        score += 4
    else:
        notes.append("no <h1>")
    if re.search(r"<article|<main", html) or path.endswith((".txt", ".xml")):
        score += 3
    else:
        notes.append("no <article>/<main>")
    score += 3
    return score, notes


def _score_perf(html_size: int, elapsed_ms: float) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 0
    if html_size < 250 * 1024:
        score += 5
    elif html_size < 500 * 1024:
        score += 3
        notes.append(f"page weight {html_size} > 250KB target")
    else:
        notes.append(f"page weight {html_size} > 500KB")
    if elapsed_ms < 500:
        score += 5
    elif elapsed_ms < 1500:
        score += 3
    else:
        notes.append(f"elapsed {elapsed_ms:.0f}ms > 1.5s")
    return score, notes


def _score_privacy(html: str, response_headers: dict[str, str]) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 5
    for tracker in (
        "google-analytics.com",
        "googletagmanager.com",
        "connect.facebook.net",
        "static.hotjar.com",
        "_fbq",
    ):
        if tracker in html:
            score = max(0, score - 2)
            notes.append(f"third-party tracker present: {tracker}")
    return score, notes


def _score_monetization(html: str) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 6
    if re.search(r'role="dialog"', html):
        score = max(0, score - 3)
        notes.append("dialog/modal element found — verify it's not auto-popping")
    return score, notes


def _check_security_headers(headers: dict[str, str]) -> list[str]:
    notes: list[str] = []
    expected = (
        "strict-transport-security",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
    )
    missing = [h for h in expected if h not in {k.lower() for k in headers}]
    if missing:
        notes.append(f"missing security headers: {', '.join(missing)}")
    return notes


def audit_vertical(vertical: str, base_url: str = DEFAULT_BASE_IP) -> dict[str, Any]:
    host = f"{vertical}.local"
    page_scores: list[PageScore] = []

    for path in PAGES_PER_VERTICAL:
        resp, elapsed_ms = _fetch(base_url, host, path)
        if resp is None or resp.status_code != 200:
            ps = PageScore(
                path=path,
                status=resp.status_code if resp else 0,
                elapsed_ms=elapsed_ms,
                bytes=0,
            )
            ps.notes.append("non-200 or fetch failed")
            page_scores.append(ps)
            continue

        html = resp.text
        ps = PageScore(
            path=path,
            status=resp.status_code,
            elapsed_ms=elapsed_ms,
            bytes=len(resp.content),
        )

        is_html = path.endswith("/") or "html" in (resp.headers.get("content-type", "") or "")

        if is_html:
            for fn_key, fn in (
                ("html_meta", lambda: _score_html_meta(html, path)),
                ("seo", lambda: _score_seo(html, dict(resp.headers))),
                ("aeo", lambda: _score_aeo(html, path)),
                ("privacy", lambda: _score_privacy(html, dict(resp.headers))),
                ("monetization", lambda: _score_monetization(html)),
            ):
                s, n = fn()
                ps.dimensions[fn_key] = s
                ps.notes.extend(n)

        s, n = _score_perf(len(resp.content), elapsed_ms)
        ps.dimensions["perf"] = s
        ps.notes.extend(n)

        ps.dimensions["content_quality"] = None
        ps.dimensions["source_attribution"] = None
        ps.dimensions["editorial_integrity"] = None
        ps.dimensions["accessibility"] = None

        ps.notes.extend(_check_security_headers(dict(resp.headers)))
        page_scores.append(ps)

    total_pts = sum(p.total for p in page_scores)
    max_pts = sum(p.max_implemented for p in page_scores)
    avg_pct = (100.0 * total_pts / max_pts) if max_pts else 0.0
    return {
        "vertical": vertical,
        "host": host,
        "pages": page_scores,
        "total_pts": total_pts,
        "max_pts": max_pts,
        "avg_percentage": avg_pct,
        "passes": avg_pct >= THRESHOLD,
    }


def render_markdown(generated_at: str, vertical_reports: list[dict[str, Any]]) -> str:
    lines = [
        f"# Grimoire harness report — {generated_at}",
        "",
        "**Threshold:** 87 / 100. Implemented dimensions only "
        "(content_quality / source_attribution / editorial_integrity / "
        "accessibility are LLM/axe-core-graded — pending integration).",
        "",
    ]
    for vr in vertical_reports:
        lines.append(f"## {vr['vertical']} ({vr['host']})")
        lines.append("")
        lines.append(
            f"**Aggregate:** {vr['total_pts']} / {vr['max_pts']} "
            f"= {vr['avg_percentage']:.1f}%  "
            f"{'PASS' if vr['passes'] else 'FAIL'}"
        )
        lines.append("")
        lines.append("| Path | Status | ms | Bytes | Score | Notes |")
        lines.append("|---|---|---|---|---|---|")
        for p in vr["pages"]:
            score = f"{p.total}/{p.max_implemented}" if p.max_implemented else "—"
            note = "; ".join(p.notes[:3]) if p.notes else ""
            lines.append(
                f"| `{p.path}` | {p.status} | {p.elapsed_ms:.0f} | "
                f"{p.bytes} | {score} | {note} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the grimoire quality harness")
    parser.add_argument("verticals", nargs="*", default=["embedding", "vested"])
    parser.add_argument("--base-url", default=DEFAULT_BASE_IP)
    parser.add_argument("--output-dir", default=str(REPORTS_DIR))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(message)s")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    vertical_reports = [audit_vertical(v, base_url=args.base_url) for v in args.verticals]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    md = render_markdown(timestamp, vertical_reports)

    md_path = out_dir / f"{timestamp}.md"
    md_path.write_text(md, encoding="utf-8")
    json_path = out_dir / f"{timestamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_at": timestamp,
                "verticals": [
                    {**vr, "pages": [vars(p) for p in vr["pages"]]}
                    for vr in vertical_reports
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"report -> {md_path}")
    for vr in vertical_reports:
        verdict = "PASS" if vr["passes"] else "FAIL"
        print(f"  {vr['vertical']:12s} {vr['avg_percentage']:5.1f}%  [{verdict}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
