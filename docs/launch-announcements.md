# Launch announcement drafts

**Captured:** 2026-05-02
**Use:** drafts ready to post at launch. Voice is the operator's personal
account, NOT Auva Labs corporate (per BUILD-DIRECTIVE Phase 8).

Replace `<DOMAIN>` with the real committed domain at launch time. The
HN Show, LinkedIn post, and Twitter thread go up in that order, ~24h
apart, after which the subreddit posts follow on day three.

---

## Modelwatch — Hacker News Show

**Title:**

```
Show HN: Modelwatch – Real-time AI/ML knowledge platform
```

**Body:**

```
I built Modelwatch (https://<DOMAIN>) because I was tired of the AI news
cycle being either hype-rewritten by ad-stuffed tech press or scattered
across thirty Substack newsletters with no clustering.

Three things make it different:

  1. Source clustering. The front page reads like a curator's desk —
     when OpenAI announces something and it's covered by ten outlets,
     the page shows one canonical headline plus the source list, not
     ten near-duplicate cards.

  2. AI usage is honest. Summaries are LLM-generated, but the system
     rejects ungrounded outputs — every fact has to derive from the
     linked source. Methodology page documents exactly how
     (https://<DOMAIN>/methodology). The /llms.txt is an actual
     declaration, not boilerplate.

  3. Reference layer alongside the news. 50+ AI/ML glossary entries,
     beginner's guides, comparisons, and live tools (LLM cost
     calculator, token counter, model comparison matrix). The same
     engine that powers the news feed cross-links the glossary into
     every story that uses a term.

Stack: Python 3.12 backend (feedparser, trafilatura, SQLAlchemy 2.0),
Postgres 16, Redis 7, Caddy, Jinja2 templates. ~5K lines.
Word-shingle deduplication ported verbatim from a private cyber-news
project I run, generalised with per-vertical guard regexes (so GPT-4
vs GPT-5 announcements stay distinct stories regardless of similar
headlines).

Happy to answer questions about the dedup algorithm, the LLM grounding
pipeline, or the /llms.txt declaration approach.

Site: https://<DOMAIN>
Methodology: https://<DOMAIN>/methodology
Source list: https://<DOMAIN>/sources
```

---

## Modelwatch — LinkedIn announcement (operator's personal account)

```
After several weekends of work, Modelwatch is live: https://<DOMAIN>

It's a real-time AI/ML knowledge platform. Three reasons it exists:

→ The AI news cycle is fragmented. First-party announcements from labs,
  ArXiv preprints, regulatory filings, and independent commentary all
  live in different places. Modelwatch clusters them by event, so
  parallel coverage of the same story shows up as one headline + the
  source list, not ten near-duplicate cards.

→ AI-generated summaries shouldn't be hand-waved. Every summary on
  Modelwatch is grounded in its source — the system rejects outputs
  that introduce facts not in the linked article. The methodology page
  walks through exactly how.

→ News alone isn't a knowledge platform. Modelwatch ships with a
  glossary (50+ entries on RAG, fine-tuning, RLHF, MoE, quantization,
  etc.), beginner's guides, and live tools — including an LLM cost
  calculator across 12 of the major APIs.

If you work in or alongside AI/ML, take a look. Daily newsletter at
the digest sign-up; Pro tier ($19/mo) for early-access plus the
weekly deep-dive.

Honest about the AI usage, honest about the monetisation. /llms.txt
on the site spells it out.

#AI #MachineLearning
```

---

## Modelwatch — Twitter / X thread

**Tweet 1:**

```
Just shipped Modelwatch — a real-time AI/ML knowledge platform that
treats AI news the way Techmeme treats tech news.

Source clustering. Grounded summaries. A glossary that cross-links
into every story.

https://<DOMAIN>

🧵 1/8
```

**Tweet 2:**

```
2/ The problem: AI news lives in 30 Substacks, six labs' first-party
blogs, ArXiv, half a dozen regulatory bodies, and tech press that
rewrites everything for ad impressions.

Modelwatch ingests 44 sources, dedups within a 7-day window, and
clusters parallel coverage of the same event.
```

**Tweet 3:**

```
3/ Summaries are LLM-generated AND grounded. The pipeline rejects any
output that introduces a fact not in the source. Hallucinated numbers
don't ship.

I'm tired of "AI summarised" headlines that quietly invent data.
```

**Tweet 4:**

```
4/ AI usage is documented, not hidden. /llms.txt is an actual honest
declaration:

  - what the property is
  - how content is sourced
  - what's tracked (no third-party trackers)
  - what's monetised (sponsorship + Pro tier + disclosed affiliates)

https://<DOMAIN>/llms.txt
```

**Tweet 5:**

```
5/ The reference layer is the part that took longest. 50+ glossary
entries on the terms you'd hit reading any AI story. Beginner's
guides, comparisons. Each entry carries a "last verified" date.

This is durable SEO and durable utility, in that order.
```

**Tweet 6:**

```
6/ Live tools, not links to other sites' tools. LLM cost calculator
across 12 APIs. Token counter. Model comparison matrix. Open-source
vs proprietary decision tool.

If a tool requires a formula, the formula is visible.
```

**Tweet 7:**

```
7/ Stack: Python 3.12, Postgres 16, Redis 7, Caddy, Jinja2 templates.
Word-shingle deduplication with per-vertical guard regexes. Cron-driven
ingestion every 10 minutes.

Multi-tenant — Vested (PF for tech workers) launches next on the same engine.
```

**Tweet 8:**

```
8/ Daily newsletter at https://<DOMAIN>/newsletter
Methodology at https://<DOMAIN>/methodology
Sources at https://<DOMAIN>/sources

Feedback welcome. Honest critique of the dedup, the grounding rules,
or the editorial line — please reply.
```

---

## Modelwatch — r/MachineLearning post

**Subreddit:** r/MachineLearning
**Post type:** [P]roject (verify subreddit rules at submission time;
some weeks ban project posts on certain days).

**Title:**

```
[P] Modelwatch — open-stack AI/ML knowledge platform with grounded summaries
```

**Body:**

```
Hi r/MachineLearning. I built Modelwatch as a personal answer to "where
is the canonical place to read about AI/ML right now without trawling
30 Substacks."

What it does:
  - Aggregates 44 first-party + research + tech-press feeds
  - Deduplicates with a word-shingle inverted index over a 7-day window
  - Clusters parallel coverage of the same story
  - Generates grounded summaries (LLM-assisted, but the system rejects
    any output that introduces a fact not in the source)
  - Ships a glossary, beginner's guides, comparisons, and a live LLM
    cost calculator across the major APIs

What's open about it:
  - The dedup algorithm is documented on the methodology page
  - /llms.txt is an honest declaration of sourcing + AI usage
  - /sources lists every feed with its priority weight
  - Source code structure mirrors a public threat-intelligence aggregator
    (architecture is described in the methodology page)

What I'd love feedback on:
  - The grounding rules — does the methodology rule out the failure
    modes you'd worry about?
  - The dedup similarity threshold (0.65 for news, with per-vertical
    guard regexes for model identifiers like GPT-5 vs GPT-4)
  - The taxonomy and source list

https://<DOMAIN>
```

---

## Vested — Hacker News Show (drafted; post when Vested ships)

**Title:**

```
Show HN: Vested – Personal finance built only for tech workers
```

**Body sketch:**

```
Vested (https://<DOMAIN>) is a personal finance platform whose audience
is software engineers, data scientists, AI researchers, and technical
founders earning $100K-$500K. Every other PF site treats this audience
as one demographic among many; Vested treats them as the only audience.

What this means concretely:

  - Coverage centred on equity compensation (RSUs, ISOs, NSOs, ESPP),
    AMT, QSBS, mega backdoor Roth, and tech-industry-specific risks
    (layoffs, vesting cliffs, golden handcuffs).
  - Live tools: RSU vesting + tax calculator (federal + state, AMT-aware),
    ISO exercise decision tool, mega-backdoor Roth contribution
    calculator, FIRE-at-tech-salary calculator, 1099 vs W-2 take-home.
  - Editorial discipline: every tax claim is verified against IRS
    publications, every brokerage feature claim against current docs.
    "General information, not professional advice" is on every tax page.

Same engine as Modelwatch (https://<MODELWATCH_DOMAIN>) — multi-tenant
content platform; the difference between the two properties is config.

[continue when Vested launches]
```

---

## Vested — LinkedIn (operator's personal account)

```
[Drafted on launch day; mirrors the structure of the Modelwatch
LinkedIn post but speaks to the high-income tech-worker audience and
emphasises the YMYL editorial discipline.]
```

---

## Vested — Twitter/X thread

```
[Thread structure mirrors Modelwatch — eight tweets opening with the
audience-specific pain (every PF site treats tech workers as one
demographic among many), then the differentiation (engine-driven
content, live tools, editorial integrity for YMYL).]
```

---

## Operator notes

- Sequence: HN Show first (Tuesday morning Pacific is the historical sweet spot). LinkedIn 24h after. Twitter thread 24h after that. Subreddit posts on day three. Threads/Bluesky on day four as a batch.
- Don't cross-promote between Auva Labs properties as if they're independent. Editorial mention OK; "check out our other site" is forbidden per BUILD-DIRECTIVE operating ethics.
- Watch the first-72-hours observation window for: source health, harness score, sponsor-inquiry inbox, Pro-tier signups, error logs.
