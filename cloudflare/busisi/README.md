# Busisi Cloudflare publication

This package contains the production Worker, D1 publication schema, static
assets, tests and the read-only live verification contract for busisi.org.

D1 stores publication records only. The canonical acquisition database is
never bound to the Worker.

## Local checks

```bash
npm ci
npm test
npm run check
```

`npm run check` builds deterministic publication bundles, enforces at least 95
percent line and function coverage and 90 percent branch coverage, and performs
a Wrangler dry run.

The COA bundle keeps report discovery, archived source copies, agency or program
context, and reviewed project-observation matches as separate states. A missing
match is never presented as audit clearance.

The contract outcome endpoint derives read-only cross-checks from exact
procurement evidence, three version-pinned secondary PhilGEPS mirror rows, and
the DPWH delivery snapshot. Mirror awardees and amounts stay visibly secondary
because the complete mirror file and original award pages are not archived. It
does not infer inspection, payment, or audit results from a contractor name or
status.

The contract evidence endpoint publishes 27 lifecycle acquisition checks for
three reviewed contracts. The checklist covers procurement plan, bid notice,
procurement monitoring report, award notice, signed contract, Notice to
Proceed, completion certificate, inspection and acceptance, and payment
record. One original official artifact is archived and verified, three
official-source acquisitions are blocked and retryable, three extracted rows
are secondary evidence, and 20 target documents have not been located. Reported
dates remain separate from document acquisition.

## Production verification

```bash
npm run verify:live
npm run submit:indexnow
```

The live verifier checks DNS, HTTPS, canonical metadata, discovery files,
security headers, exact dataset counts, artifact hashes, representative source
queries, stage-change controls, deterministic review-queue counts, evidence CSV,
reviewed and quarantined dossier boundaries, redirects and assets.

Deployment and D1 mutation require operator credentials. The scheduled GitHub
monitor is credential-free and read-only.
