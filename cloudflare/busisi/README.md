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

`npm run check` builds deterministic publication bundles, enforces at least 80
percent line, branch and function coverage, and performs a Wrangler dry run.

## Production verification

```bash
npm run verify:live
npm run submit:indexnow
```

The live verifier checks DNS, HTTPS, canonical metadata, discovery files,
security headers, exact dataset counts, artifact hashes, representative source
queries, reviewed and quarantined dossier boundaries, redirects and assets.

Deployment and D1 mutation require operator credentials. The scheduled GitHub
monitor is credential-free and read-only.
