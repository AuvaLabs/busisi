import assert from 'node:assert/strict';
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
  assert.match(document, /href="\/assets\/site-visual-v4\.css"/);
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
});

test('home provides direct navigation and substantive motion-led visuals', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /href="\/#mission"/);
  assert.match(document, /href="\/#system"/);
  assert.match(document, /href="\/#gate"/);
  assert.match(document, /href="\/explore\/"/);
  assert.match(document, /href="\/signals\/"/);
  assert.match(document, /class="evidence-orbit"/);
  assert.match(document, /aria-label="Evidence moves from official source to reviewed publication"/);
  assert.match(document, /Illustrative sequence/);
  assert.match(document, /Not a ranking\. Not an accusation\./);
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

test('publishes supported signals and names unavailable analyses', async () => {
  const response = await fetchPath('/signals/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Review signals/);
  assert.match(document, /Repeated funding/);
  assert.match(document, /Zero downstream budget/);
  assert.match(document, /Insertion analysis/);
  assert.match(document, /Unavailable until budget-stage records are acquired/);
  assert.match(document, /Physical existence verification/);
});

test('home uses the original Busisi identity and professional exploration panels', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /src="\/assets\/busisi-mark-v2\.svg"/);
  assert.doesNotMatch(document, /src="\/assets\/busisi-mark\.webp"/);
  assert.match(document, /src="\/assets\/busisi-masthead\.webp"/);
  assert.match(document, /Independent Philippine budget evidence project/);
  assert.match(document, /Explore the source record/);
  assert.match(document, /GAA appropriations/);
  assert.match(document, /DPWH delivery records/);
  assert.match(document, /Candidate links/);
  assert.match(document, /Human review required/);
  assert.match(document, /Illustrative view · not a project record/);
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
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/projects\/corazon-2024-phase-1\/<\/loc>/);
  assert.doesNotMatch(sitemapText, /corazon-2026-completion/);
  assert.match(await llms.text(), /Evidence and publication rules/);
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
    DB: { prepare: () => ({ bind: () => ({ first: async () => row }) }) },
  };
  const response = await worker.fetch(
    new Request('https://busisi.org/projects/reviewed-project/'),
    environment,
  );
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Reviewed public project/);
  assert.match(document, /Reviewed link/);
  assert.match(document, /Authority to spend, not proof of disbursement/);
  assert.match(document, /Official evidence 1/);
});

test('serves immutable assets and safe method boundaries', async () => {
  const css = await fetchPath('/assets/site-visual-v4.css');
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
  assert.match(cssText, /--text-xs:\.8125rem/);
  assert.match(cssText, /body\{[^}]*font-size:var\(--text-md\)[^}]*line-height:1\.6/);
  assert.match(cssText, /body:before\{display:none/);
  assert.match(cssText, /@media\(prefers-contrast:more\)/);
  assert.match(await css.clone().text(), /@keyframes orbit-pulse/);
  assert.match(await css.text(), /prefers-reduced-motion:reduce/);
  assert.match(icon.headers.get('content-type'), /^image\/svg\+xml/);
  assert.equal(missingAsset.status, 404);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal(post.status, 405);
});

test('passes generated media and self-hosted fonts through the static asset binding', async () => {
  const env = {
    ASSETS: {
      fetch: async (request) => new Response(new URL(request.url).pathname, {
        headers: { 'content-type': 'image/webp' },
      }),
    },
  };
  const asset = await worker.fetch(
    new Request('https://busisi.org/assets/busisi-masthead.webp'),
    env,
  );

  assert.equal(asset.status, 200);
  assert.equal(await asset.text(), '/assets/busisi-masthead.webp');
});
