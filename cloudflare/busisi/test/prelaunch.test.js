import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import worker from '../src/prelaunch.js';

const fetchPath = (path, hostname = 'busisi.org') => worker.fetch(
  new Request(`https://${hostname}${path}`),
);

test('home publishes canonical prelaunch SEO without exposing records', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /<link rel="canonical" href="https:\/\/busisi\.org\/">/);
  assert.match(document, /<meta name="robots" content="index, follow, max-image-preview:large">/);
  assert.match(document, /<meta property="og:url" content="https:\/\/busisi\.org\/">/);
  assert.match(document, /<meta property="og:image" content="https:\/\/busisi\.org\/assets\/busisi-social-v1\.png">/);
  assert.match(document, /<meta property="og:image:width" content="1200">/);
  assert.match(document, /<meta property="og:image:height" content="630">/);
  assert.match(document, /<meta name="twitter:card" content="summary_large_image">/);
  assert.match(document, /href="\/assets\/site-visual-v9\.css"/);
  assert.match(document, /"@type":"WebSite"/);
  assert.match(document, /Philippine public budget records/);
  assert.doesNotMatch(document, /corazon-2026|25HI0028|api\/v1\/projects/i);
  assert.doesNotMatch(document, /Auva Labs|auvalabs/i);
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.match(
    response.headers.get('content-security-policy'),
    /script-src 'self' https:\/\/static\.cloudflareinsights\.com/,
  );
  assert.match(response.headers.get('content-security-policy'), /connect-src 'self'/);
  assert.match(response.headers.get('content-security-policy'), /form-action 'self'/);
});

test('home provides task-led navigation and a data-led editorial masthead', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /href="\/explore\/"/);
  assert.match(document, /href="\/signals\/"/);
  assert.match(document, /href="\/sulit\/"/);
  assert.match(document, /class="home-ledger"/);
  assert.match(document, /aria-label="Current FY2027 budget evidence"/);
  assert.match(document, /20,431 project rows/);
  assert.match(document, /DPWH delivery records/);
  assert.match(document, /56,887/);
  assert.match(document, /NEP published/);
  assert.match(document, /House partially acquired/);
  assert.match(document, /src="\/assets\/busisi-evidence-banner-v1\.webp"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#appropriations"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#delivery"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#candidate-links"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#compare"/);
  assert.doesNotMatch(document, /busisi-masthead\.webp|Illustrative view/);
  assert.doesNotMatch(document, /class="utility-strip"/);
  assert.equal((document.match(/data-nav-group=/g) ?? []).length, 5);
});

test('publishes the source-record explorer without implying reviewed links', async () => {
  const response = await fetchPath('/explore/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Explore official budget records/);
  assert.match(document, /data-explorer-view/);
  assert.match(document, /GAA appropriations/);
  assert.match(document, /DPWH delivery records/);
  assert.match(document, /Candidate links/);
  assert.match(document, /Unreviewed candidates are not public findings/);
  assert.doesNotMatch(document, /ghost project/i);
});

test('publishes the deterministic review desk and names unavailable analyses', async () => {
  const response = await fetchPath('/signals/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Start with the records that moved/);
  assert.match(document, /data-review-desk/);
  assert.match(document, /Prior-year family candidates/);
  assert.match(document, /Similar FY2027 family candidates/);
  assert.match(document, /Download evidence CSV/);
  assert.match(document, /How to read a review signal/);
  assert.match(document, /src="\/assets\/review-v1\.js"/);
  assert.match(document, /Physical existence verification/);
});

test('publishes the project-integrity desk and contractor leaderboard', async () => {
  const response = await fetchPath('/integrity/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Inspect contradictions in delivery records/);
  assert.match(document, /data-integrity-desk/);
  assert.match(document, /Contractors with the most projects/);
  assert.match(document, /Rank by project count/);
  assert.match(document, /Rank by associated project budget/);
  assert.match(document, /data-concentration-desk/);
  assert.match(document, /contractor-party associations/);
  assert.match(document, /Current PCAB-table status/);
  assert.match(document, /Congressional district context/);
  assert.match(document, /does not establish political authorship/);
  assert.match(document, /What this desk flags/);
  assert.match(document, /src="\/assets\/integrity-v1\.js"/);
  assert.doesNotMatch(document, /proves? (?:fraud|corruption)/i);
});

test('publishes an interactive FY2027 budget change ledger with careful labels', async () => {
  const response = await fetchPath('/changes/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Trace what changed between the NEP and House bill/);
  assert.match(document, /20,431/);
  assert.match(document, /data-change-ledger/);
  assert.match(document, /In the House bill only/);
  assert.match(document, /How to read a change/);
  assert.match(document, /src="\/assets\/changes-v1\.js"/);
  assert.doesNotMatch(document, /proves? (?:an )?insertion/i);
});

test('publishes a reconciled FY2027 appropriation-head ledger', async () => {
  const response = await fetchPath('/agencies/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /See how agency budgets changed in the House bill/);
  assert.match(document, /39 appropriation heads/);
  assert.match(document, /Senate and House are shown separately/);
  assert.match(document, /data-agency-ledger/);
  assert.match(document, /Automatic Appropriations/);
  assert.match(document, /How to read this comparison/);
  assert.match(document, /src="\/assets\/agencies-v1\.js"/);
});

test('publishes a budget trail without claiming missing Senate or GAA stages', async () => {
  const response = await fetchPath('/budget-trail/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Follow the FY2027 budget through each published stage/);
  assert.match(document, /data-budget-cycle/);
  assert.match(document, /House bill, third reading/);
  assert.match(document, /Senate committee stage/);
  assert.match(document, /Not yet acquired/);
  assert.match(document, /A Senate-hosted document is not automatically a Senate-stage document/);
  assert.match(document, /src="\/assets\/budget-cycle-v1\.js"/);
});

test('publishes the Sulit Ba public-value desk as the primary civic question', async () => {
  const response = await fetchPath('/sulit/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /₱7\.2 trillion\. Sulit ba para sa Pilipino\?/);
  assert.match(document, /Mixed fiscal direction/);
  assert.match(document, /data-public-value-desk/);
  assert.match(document, /Need and plan alignment/);
  assert.match(document, /Opportunity cost/);
  assert.match(document, /Motive cannot be inferred/);
  assert.match(document, /not enacted appropriations, releases, payments, or outcomes/i);
  assert.match(document, /src="\/assets\/public-value-v1\.js"/);
  assert.doesNotMatch(document, /overall score|AI score|Auva Labs/i);
});

test('home uses the monochrome Busisi identity and direct evidence desks', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /src="\/assets\/busisi-mark-v2\.svg"/);
  assert.doesNotMatch(document, /src="\/assets\/busisi-mark\.webp"/);
  assert.doesNotMatch(document, /busisi-masthead\.webp/);
  assert.match(document, /Philippine budget evidence/);
  assert.match(document, /Start with the public record/);
  assert.match(document, /GAA appropriations/);
  assert.match(document, /DPWH delivery records/);
  assert.match(document, /Candidate links/);
  assert.match(document, /Human review required/);
  assert.match(document, /Where the evidence stops/);
});

test('methodology is canonical and explains the publication gate', async () => {
  const response = await fetchPath('/methodology/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /https:\/\/busisi\.org\/methodology\//);
  assert.match(document, /100 reviewed linkage cases/);
  assert.match(document, /not evidence of wrongdoing/i);
  assert.match(document, /href="#pipeline"/);
  assert.match(document, /href="#source-policy"/);
  assert.match(document, /href="#corrections"/);
  assert.match(document, /Congressional district context/);
  assert.match(document, /Machine-readable provenance stays in the JSON API/);
  assert.match(document, /not a coordinate or boundary-polygon determination/);
  assert.doesNotMatch(document, /Auva Labs|auvalabs/i);
});

test('publishes machine-readable discovery files', async () => {
  const robots = await fetchPath('/robots.txt');
  const sitemap = await fetchPath('/sitemap.xml');
  const llms = await fetchPath('/llms.txt');
  const sitemapText = await sitemap.text();

  const robotsText = await robots.text();
  assert.match(robotsText, /Sitemap: https:\/\/busisi\.org\/sitemap\.xml/);
  assert.doesNotMatch(robotsText, /Disallow: \/projects\//);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/methodology\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/explore\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/signals\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/changes\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/agencies\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/budget-trail\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/audit\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/audit\/reports\/coa-oda-consolidated-2024\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/integrity\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/sulit\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/projects\/corazon-2024-phase-1\/<\/loc>/);
  assert.doesNotMatch(sitemapText, /corazon-2026-completion/);
  const llmsText = await llms.text();
  assert.match(llmsText, /Evidence and publication rules/);
  assert.match(llmsText, /Project integrity desk/);
  assert.match(llmsText, /Appropriation heads/);
  assert.match(llmsText, /Public value desk/);
  assert.match(llms.headers.get('content-type'), /^text\/plain/);
});

test('serves the public IndexNow ownership key', async () => {
  const key = '4754cd4a99b473376bef19b5bbf858f0';
  const response = await fetchPath(`/${key}.txt`);

  assert.equal(response.status, 200);
  assert.equal((await response.text()).trim(), key);
});

test('redirects www and returns a useful 404', async () => {
  const redirect = await fetchPath('/methodology/', 'www.busisi.org');
  const missing = await fetchPath('/not-a-page');

  assert.equal(redirect.status, 301);
  assert.equal(redirect.headers.get('location'), 'https://busisi.org/methodology/');
  assert.equal(missing.status, 404);
  assert.match(await missing.text(), /Page not found/);
});

test('keeps the unreleased register and API unavailable', async () => {
  for (const path of ['/projects/example', '/api/v1/projects']) {
    const response = await fetchPath(path);
    assert.equal(response.status, 404, path);
    assert.match(await response.text(), /noindex, nofollow/, path);
  }
});

test('redirects the former watchlist route to the explorer', async () => {
  const response = await fetchPath('/watchlist/');

  assert.equal(response.status, 302);
  assert.equal(response.headers.get('location'), 'https://busisi.org/explore/?view=reviewed');
});

test('renders a reviewed evidence dossier when the publication database is bound', async () => {
  const row = {
    case_id: 'case-1', slug: 'reviewed-project', title: 'Reviewed public project',
    fiscal_year: 2025, location: 'Cebu', appropriation_centavos: 5_000_000,
    contract_budget_centavos: 4_800_000, variance_centavos: 200_000,
    contract_id: '25TEST', delivery_title: 'Reviewed delivery record',
    implementing_office: 'Cebu District Office', source_of_funds: 'GAA 2025',
    confidence: 'high', confidence_score: 90,
    match_signals_json: '["year_match","location_match"]',
    match_limitations: 'The records may describe separate phases.',
    evidence_urls_json: '["https://budget.example","https://dpwh.example"]',
    family_id: 'family:1', family_label: 'reviewed public project',
    status_label: 'Reviewed link', publication_status: 'reviewed', is_confirmed_link: 1,
  };
  const environment = {
    DB: {
      prepare: (sql) => ({
        all: async () => ({ results: [] }),
        bind: () => ({
          first: async () => sql.includes('FROM projects WHERE slug') ? row : null,
          all: async () => ({ results: [] }),
        }),
      }),
    },
  };
  const response = await worker.fetch(
    new Request('https://busisi.org/projects/reviewed-project/'),
    environment,
  );
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Reviewed public project/);
  assert.match(document, /Reviewed project evidence dossier/);
  assert.match(document, /Authority to spend/);
  assert.match(document, /Reader evidence links/);
  assert.doesNotMatch(document, /budget\.example|dpwh\.example/);
});

test('serves the monochrome editorial system and safe method boundaries', async () => {
  const css = await fetchPath('/assets/site-visual-v9.css');
  const icon = await fetchPath('/assets/favicon.svg');
  const missingAsset = await fetchPath('/assets/missing.svg');
  const head = await worker.fetch(new Request('https://busisi.org/', { method: 'HEAD' }));
  const post = await worker.fetch(new Request('https://busisi.org/', { method: 'POST' }));

  assert.match(css.headers.get('content-type'), /^text\/css/);
  assert.match(css.headers.get('cache-control'), /immutable/);
  const cssText = await css.clone().text();
  assert.match(cssText, /font-family:'Source Sans 3'/);
  assert.doesNotMatch(cssText, /Merriweather|Georgia|Times New Roman/i);
  assert.match(cssText, /--paper:#fff/);
  assert.match(cssText, /--ink:#111/);
  assert.match(cssText, /--accent:#111/);
  assert.match(cssText, /--signal-red:#a12b1f/);
  assert.match(cssText, /--text-xs:\.8125rem/);
  assert.match(cssText, /body\{[^}]*font-size:var\(--text-md\)[^}]*line-height:1\.6/);
  assert.match(cssText, /body:before\{display:none/);
  assert.match(cssText, /@media\(prefers-contrast:more\)/);
  assert.match(cssText, /\.integrity-shell/);
  assert.match(cssText, /\.contractor-shell/);
  assert.match(cssText, /\.home-ledger/);
  assert.match(cssText, /\.editorial-banner/);
  assert.match(cssText, /\.section-icon/);
  assert.match(cssText, /\.budget-stage-line/);
  assert.match(cssText, /\.primary-nav/);
  assert.match(cssText, /\.preview-panels>a>span[^}]*border-radius:0/);
  assert.match(await css.text(), /prefers-reduced-motion:reduce/);
  assert.match(icon.headers.get('content-type'), /^image\/svg\+xml/);
  assert.equal(missingAsset.status, 404);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal(post.status, 405);
});

test('passes self-hosted fonts through the static asset binding', async () => {
  const env = {
    ASSETS: {
      fetch: async (request) => new Response(new URL(request.url).pathname, {
        headers: { 'content-type': 'image/webp' },
      }),
    },
  };
  const asset = await worker.fetch(
    new Request('https://busisi.org/assets/source-sans-3-latin.woff2'),
    env,
  );

  assert.equal(asset.status, 200);
  assert.equal(await asset.text(), '/assets/source-sans-3-latin.woff2');
});

test('passes the editorial social card through the static asset binding', async () => {
  const env = {
    ASSETS: {
      fetch: async (request) => new Response(new URL(request.url).pathname, {
        headers: { 'content-type': 'image/png' },
      }),
    },
  };
  const asset = await worker.fetch(
    new Request('https://busisi.org/assets/busisi-social-v1.png'),
    env,
  );

  assert.equal(asset.status, 200);
  assert.equal(asset.headers.get('content-type'), 'image/png');
  assert.equal(await asset.text(), '/assets/busisi-social-v1.png');
});

test('passes the editorial banner and icon system through the static asset binding', async () => {
  const env = {
    ASSETS: {
      fetch: async (request) => {
        const path = new URL(request.url).pathname;
        const type = path.endsWith('.svg') ? 'image/svg+xml' : 'image/webp';
        return new Response(path, { headers: { 'content-type': type } });
      },
    },
  };
  const banner = await worker.fetch(
    new Request('https://busisi.org/assets/busisi-evidence-banner-v1.webp'),
    env,
  );
  const icons = await worker.fetch(
    new Request('https://busisi.org/assets/busisi-icons-v1.svg'),
    env,
  );

  assert.equal(banner.status, 200);
  assert.equal(banner.headers.get('content-type'), 'image/webp');
  assert.equal(icons.status, 200);
  assert.equal(icons.headers.get('content-type'), 'image/svg+xml');
});

test('reader actions use human-readable evidence instead of raw JSON endpoints', () => {
  const assets = Object.fromEntries(
    ['explorer', 'agencies', 'changes', 'review', 'integrity'].map((name) => [
      name,
      readFileSync(new URL(`../public/assets/${name}-v1.js`, import.meta.url), 'utf8'),
    ]),
  );

  assert.match(assets.explorer, /record\.reader_source_url/);
  assert.doesNotMatch(assets.explorer, /Open official source.*record\.source_url/);
  assert.doesNotMatch(assets.explorer, /Open DPWH source.*record\.source_url/);
  assert.match(assets.agencies, /record\.nep_reader_url/);
  assert.doesNotMatch(assets.agencies, /NEP dataset.*record\.nep_source_url/);
  assert.doesNotMatch(assets.changes, /Comparison record.*record\.source_url/);
  assert.doesNotMatch(assets.review, /Comparison.*record\.source_url/);
  assert.doesNotMatch(assets.integrity, /Open archived source record.*record\.source_url/);
});
