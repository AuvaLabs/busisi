"""Anima channel-feeder enrichment — derive the §3 JSON contract per story.

The Vested → Anima feeder turns vested.news stories into a structured story
source for the Anima finance channel. Anima scores each story on
NEED/DEMAND/RARITY + a TIMELINESS axis, drafts a script, and fact-gates every
on-screen number against ``primary_source_url``. So ``key_stat`` +
``primary_source_url`` are the highest-value fields — they drop straight into
Anima's ``claims.json``.

Design note (2026-06-06): enrichment is computed **on read** from data that
already exists in the store (cluster size, per-article ``structured_extract``
numerics, ``story_sources``, article ``labels``, the entity join). This keeps
the feeder purely additive — no schema migration, no pipeline change, nothing
that could break the live site — while fully satisfying the §3 contract. Every
function here is deterministic and side-effect free so it can be unit-tested
without a database; the handler does the SQL and feeds plain data in.

The contract (one array entry per recent story)::

    {
      "id", "headline", "summary", "url", "source",
      "primary_source_url", "key_stat", "entities",
      "lane", "evergreen", "published_at", "momentum"
    }
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import yaml

from engine.core.config import vertical_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lane mapping — vested taxonomy label -> one of the four Anima lanes.
# First label (highest confidence) that maps wins. Stories with labels but no
# mapping fall back to "Money, Explained"; stories with no labels get null.
# ---------------------------------------------------------------------------

LANES = (
    "What It Really Costs",
    "The Cost of Waiting",
    "Where Your Money Goes",
    "Money, Explained",
)

_LANE_BY_LABEL: dict[str, str] = {
    # The Cost of Waiting — compounding, timing, retirement runway.
    "retirement-planning": "The Cost of Waiting",
    "financial-independence": "The Cost of Waiting",
    # What It Really Costs — the price tag / drag of a decision.
    "taxes": "What It Really Costs",
    "insurance-life-stage": "What It Really Costs",
    "real-estate": "What It Really Costs",
    "debt-management": "What It Really Costs",
    "equity-compensation": "What It Really Costs",
    # Where Your Money Goes — flows, accounts, where dollars land.
    "banking": "Where Your Money Goes",
    "credit": "Where Your Money Goes",
    "brokerage-investing": "Where Your Money Goes",
    "side-income": "Where Your Money Goes",
    "salary-negotiation": "Where Your Money Goes",
    # Money, Explained — mechanics / planning explainers.
    "estate-planning": "Money, Explained",
    "charitable-giving": "Money, Explained",
    "layoff-strategy": "Money, Explained",
}

_LANE_DEFAULT = "Money, Explained"

# Topics whose stories are evergreen-explainer material (vs one-off news).
_EVERGREEN_TOPICS: frozenset[str] = frozenset(
    {
        "retirement-planning",
        "financial-independence",
        "taxes",
        "estate-planning",
        "insurance-life-stage",
        "charitable-giving",
        "brokerage-investing",
        "banking",
        "credit",
        "real-estate",
        "debt-management",
        "salary-negotiation",
        "equity-compensation",
    }
)

# Authoritative hosts — primary_source_url enrichment prefers these. Suffix
# matched, so subdomains (data.bls.gov, edgar.sec.gov) resolve too.
PRIMARY_HOSTS: tuple[str, ...] = (
    "bls.gov",
    "bea.gov",
    "federalreserve.gov",
    "stlouisfed.org",  # FRED
    "treasury.gov",
    "treasurydirect.gov",
    "fiscaldata.treasury.gov",
    "ssa.gov",
    "cbo.gov",
    "irs.gov",
    "sec.gov",
    "consumerfinance.gov",
)

# Host substring -> short display source name for the contract's "source".
_SOURCE_LABELS: tuple[tuple[str, str], ...] = (
    ("bls.gov", "BLS"),
    ("bea.gov", "BEA"),
    ("stlouisfed.org", "FRED"),
    ("federalreserve.gov", "Fed"),
    ("treasurydirect.gov", "TreasuryDirect"),
    ("treasury.gov", "Treasury"),
    ("ssa.gov", "SSA"),
    ("cbo.gov", "CBO"),
    ("irs.gov", "IRS"),
    ("sec.gov", "SEC"),
    ("consumerfinance.gov", "CFPB"),
    ("nerdwallet.com", "NerdWallet"),
    ("investopedia.com", "Investopedia"),
    ("bankrate.com", "Bankrate"),
    ("kiplinger.com", "Kiplinger"),
    ("morningstar.com", "Morningstar"),
    ("bloomberg.com", "Bloomberg"),
    ("dj.com", "WSJ"),
    ("wsj.com", "WSJ"),
    ("bbc.co.uk", "BBC"),
    ("bbci.co.uk", "BBC"),
    ("nytimes.com", "NYT"),
    ("theguardian.com", "Guardian"),
    ("npr.org", "NPR"),
    ("fidelity.com", "Fidelity"),
    ("schwab.com", "Schwab"),
    ("vanguard.com", "Vanguard"),
    ("wealthfront.com", "Wealthfront"),
    ("pewresearch.org", "Pew Research"),
    ("taxpolicycenter.org", "Tax Policy Center"),
    ("pgpf.org", "PGPF"),
    ("ici.org", "ICI"),
    ("levels.fyi", "Levels.fyi"),
)


def host_of(url: str) -> str:
    """Lowercased netloc with leading ``www.`` stripped; ``""`` on failure."""
    try:
        host = urlparse(url).netloc.lower()
        return host.removeprefix("www.")
    except Exception:
        return ""


def display_source(url_or_host: str) -> str:
    """Map a URL/host to a short editorial source name (e.g. ``Fed``)."""
    host = url_or_host if "/" not in url_or_host else host_of(url_or_host)
    host = host.lower().removeprefix("www.")
    for needle, label in _SOURCE_LABELS:
        if host.endswith(needle) or needle in host:
            return label
    return host or "unknown"


def _is_primary_host(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in PRIMARY_HOSTS)


def derive_lane(labels: list[str]) -> str | None:
    """Map ordered labels (highest confidence first) to an Anima lane."""
    if not labels:
        return None
    for label in labels:
        lane = _LANE_BY_LABEL.get(label)
        if lane:
            return lane
    return _LANE_DEFAULT


def derive_evergreen(labels: list[str]) -> bool:
    """True when any label is an evergreen-explainer topic."""
    return any(label in _EVERGREEN_TOPICS for label in labels)


# key_stat extraction — pick the single most-central number in the story.
# Priority: a figure that appears in the headline > money > percent > year.
_MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:trillion|billion|million|thousand|[KMBT])?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:percent|%)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _candidate_stats(text: str) -> list[str]:
    """All numeric phrases in ``text``, money first, then percent, then year."""
    out: list[str] = []
    for m in _MONEY_RE.finditer(text):
        out.append(re.sub(r"\s+", "", m.group(0)))
    out.extend(m.group(0) for m in _PERCENT_RE.finditer(text))
    out.extend(m.group(0) for m in _YEAR_RE.finditer(text))
    return out


def derive_key_stat(
    numerics: list[Any],
    headline: str,
    narrative: str | None = None,
) -> str | None:
    """Pick the central number for the story.

    ``numerics`` is the union of member articles' ``structured_extract``
    ``numerics`` (list of ``{"value", "context"}`` dicts or bare strings).
    A figure present in the headline is strongly preferred — that is almost
    always the story's hook. Falls back to headline-then-narrative regex.
    """
    values: list[str] = []
    for n in numerics or []:
        if isinstance(n, dict):
            v = str(n.get("value", "")).strip()
        else:
            v = str(n).strip()
        if v:
            values.append(v)

    head = headline or ""
    head_norm = re.sub(r"\s+", "", head.lower())

    # 1) A structured numeric that also appears in the headline.
    for v in values:
        if re.sub(r"\s+", "", v.lower()) in head_norm:
            return v

    # 2) Any numeric phrase parsed straight from the headline.
    head_cands = _candidate_stats(head)
    if head_cands:
        return head_cands[0]

    # 3) First structured numeric overall.
    if values:
        return values[0]

    # 4) Last resort: scan the narrative.
    if narrative:
        narr_cands = _candidate_stats(narrative)
        if narr_cands:
            return narr_cands[0]

    return None


def pick_primary_source_url(sources: list[dict[str, Any]]) -> str | None:
    """Choose the authoritative link behind the key stat.

    Prefers a cited source on a known primary/official host (BLS, Fed, IRS,
    SSA, ...); falls back to any agency_class ``D`` (primary/official) source.
    Returns ``None`` when the cluster has no primary-grade citation — Anima
    then treats the stat as unverified.
    """
    primary = [s for s in sources if _is_primary_host(str(s.get("host", "")))]
    if primary:
        return str(primary[0].get("source_url") or "") or None
    official = [s for s in sources if str(s.get("agency_class", "")).upper() == "D"]
    if official:
        return str(official[0].get("source_url") or "") or None
    return None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_momentum(
    source_count: int,
    published_at: datetime | None,
    now: datetime | None = None,
) -> float:
    """DEMAND axis: cross-source cluster size with a recency tilt, in [0, 1].

    A story carried by more independent outlets is in higher demand; a fresher
    story is more timely. Weighted 70% cluster size (cap 5 outlets) + 30%
    recency (linear decay over one week).
    """
    cluster_factor = _clamp01(source_count / 5.0)

    recency_factor = 0.0
    if published_at is not None:
        ref = now or datetime.now(timezone.utc)
        pub = published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_hours = (ref - pub).total_seconds() / 3600.0
        recency_factor = _clamp01(1.0 - age_hours / 168.0)

    return round(_clamp01(0.7 * cluster_factor + 0.3 * recency_factor), 3)


def story_to_contract(
    *,
    story_id: int,
    headline: str,
    summary: str,
    url: str,
    labels: list[str],
    numerics: list[Any],
    sources: list[dict[str, Any]],
    entities: list[str],
    narrative: str | None,
    published_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble one §3 contract record from already-fetched story data."""
    source_count = len({s.get("host") for s in sources if s.get("host")}) or len(
        sources
    )
    return {
        "id": str(story_id),
        "headline": headline,
        "summary": summary or "",
        "url": url,
        "source": display_source(url),
        "primary_source_url": pick_primary_source_url(sources),
        "key_stat": derive_key_stat(numerics, headline, narrative),
        "entities": entities,
        "lane": derive_lane(labels),
        "evergreen": derive_evergreen(labels),
        "published_at": _isoformat(published_at),
        "momentum": compute_momentum(source_count, published_at, now),
    }


def _isoformat(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Economic-release calendar
# ---------------------------------------------------------------------------

_CALENDAR_FIELDS = (
    "id",
    "name",
    "agency",
    "date",
    "recurrence",
    "primary_source_url",
    "lane",
    "entities",
    "note",
)


def load_calendar(
    vertical_id: str, *, today: datetime | None = None
) -> list[dict[str, Any]]:
    """Load ``verticals/<id>/calendar.yaml`` -> normalised release list.

    Permissive like the feed loader: a malformed row is skipped, never fatal.
    Each row gains an ``is_upcoming`` bool (date >= today) so the channel can
    filter to forward-looking drops. Sorted by date ascending.
    """
    path = vertical_dir(vertical_id) / "calendar.yaml"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fp:
            raw = yaml.safe_load(fp) or {}
    except yaml.YAMLError as exc:
        logger.error("calendar.yaml parse error in %s: %s", path, exc)
        return []

    releases = raw.get("releases") if isinstance(raw, dict) else None
    if not isinstance(releases, list):
        return []

    ref_date = (today or datetime.now(timezone.utc)).date()
    out: list[dict[str, Any]] = []
    for row in releases:
        if not isinstance(row, dict):
            continue
        if not row.get("id") or not row.get("date"):
            logger.warning("Skipping calendar row missing id/date: %r", row)
            continue
        rec = {k: row.get(k) for k in _CALENDAR_FIELDS}
        try:
            # PyYAML may parse `date:` into a date object; normalise to an ISO
            # string so the row is JSON-serialisable downstream.
            d = datetime.fromisoformat(str(row["date"])).date()
            rec["date"] = d.isoformat()
            rec["is_upcoming"] = d >= ref_date
        except ValueError:
            logger.warning("Skipping calendar row with bad date: %r", row.get("date"))
            continue
        out.append(rec)

    out.sort(key=lambda r: str(r.get("date")))
    return out
