import { Resolver } from 'node:dns/promises';

import { INDEX_NOW_KEY, SITE } from '../src/prelaunch-config.js';

const origin = process.env.BUSISI_ORIGIN ?? SITE.origin;
const expectedHost = new URL(origin).hostname;
const indexNowKey = INDEX_NOW_KEY;
const expectedCounts = Object.freeze({
  budget_records: 68_608,
  delivery_records: 56_887,
  candidate_links: 385,
  reviewed_dossiers: 6,
});
const expectedArtifacts = Object.freeze({
  budget_artifact_sha256: '6ed63d8db36e10280782ff2c9e5e1c32fe99ffbe2ff0accfe319a025203a48c4',
  delivery_artifact_sha256: '5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123',
});
const resolver = new Resolver();
resolver.setServers((process.env.BUSISI_DNS_SERVERS ?? '1.1.1.1,8.8.8.8').split(','));

const fail = (message) => {
  throw new Error(message);
};

const request = async (path, options = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    return await fetch(`${origin}${path}`, {
      redirect: 'manual',
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
};

const expectStatus = (response, status, path) => {
  if (response.status !== status) {
    fail(`${path}: expected ${status}, received ${response.status}`);
  }
};

const expectIncludes = (value, expected, label) => {
  if (!value.includes(expected)) fail(`${label}: missing ${expected}`);
};

const expectContentType = (response, expected, label) => {
  expectIncludes(response.headers.get('content-type') ?? '', expected, `${label} content type`);
};

const expectBytes = (value, expected, label) => {
  if (!value.equals(Buffer.from(expected))) fail(`${label}: invalid file signature`);
};

const readJson = async (path) => {
  const response = await request(path);
  expectStatus(response, 200, path);
  expectContentType(response, 'application/json', path);
  return response.json();
};

const verifyFont = async (path) => {
  const response = await request(path);
  expectStatus(response, 200, path);
  expectContentType(response, 'font/woff2', path);
  const bytes = Buffer.from(await response.arrayBuffer());
  expectBytes(bytes.subarray(0, 4), 'wOF2', path);
  return bytes.length;
};

const verifyDns = async () => {
  const hosts = [expectedHost, `www.${expectedHost}`];
  const results = await Promise.all(hosts.map(async (host) => ({
    host,
    records: (await Promise.allSettled([
      resolver.resolve4(host),
      resolver.resolve6(host),
    ])).flatMap((result) => result.status === 'fulfilled' ? result.value : []),
  })));
  for (const result of results) {
    if (result.records.length === 0) fail(`${result.host}: no public DNS records`);
  }
  return results.map(({ host, records }) => ({ host, record_count: records.length }));
};

const verifyPages = async () => {
  const home = await request('/');
  expectStatus(home, 200, '/');
  const homeText = await home.text();
  expectIncludes(homeText, `<link rel="canonical" href="${origin}/">`, 'home canonical');
  expectIncludes(homeText, '"@type":"WebSite"', 'home structured data');
  expectIncludes(homeText, 'index, follow, max-image-preview:large', 'home robots');
  const csp = home.headers.get('content-security-policy') ?? '';
  expectIncludes(csp, "default-src 'self'", 'home CSP');
  expectIncludes(csp, "connect-src 'self'", 'home CSP');
  expectIncludes(csp, "script-src 'self' https://static.cloudflareinsights.com", 'home CSP');
  expectIncludes(home.headers.get('strict-transport-security') ?? '', 'max-age=', 'home HSTS');

  const methodology = await request('/methodology/');
  expectStatus(methodology, 200, '/methodology/');
  expectIncludes(await methodology.text(), '100 reviewed linkage cases', 'methodology gate');

  const explore = await request('/explore/');
  expectStatus(explore, 200, '/explore/');
  const exploreText = await explore.text();
  expectIncludes(exploreText, 'Explore official budget records', 'explorer heading');
  expectIncludes(exploreText, 'Unreviewed candidates are not public findings', 'explorer warning');

  const signals = await request('/signals/');
  expectStatus(signals, 200, '/signals/');
  const signalsText = await signals.text();
  expectIncludes(signalsText, 'Insertion analysis', 'signals evidence gaps');
  expectIncludes(signalsText, 'Physical existence verification', 'signals evidence gaps');

  const robots = await request('/robots.txt');
  expectStatus(robots, 200, '/robots.txt');
  expectIncludes(await robots.text(), `Sitemap: ${origin}/sitemap.xml`, 'robots sitemap');

  const sitemap = await request('/sitemap.xml');
  expectStatus(sitemap, 200, '/sitemap.xml');
  const sitemapText = await sitemap.text();
  for (const path of ['/explore/', '/signals/', '/methodology/', '/projects/corazon-2024-phase-1/']) {
    expectIncludes(sitemapText, `<loc>${origin}${path}</loc>`, `sitemap ${path}`);
  }
  if (sitemapText.includes('corazon-2026-completion')) fail('sitemap: quarantined dossier is indexed');

  const llms = await request('/llms.txt');
  expectStatus(llms, 200, '/llms.txt');
  expectIncludes(await llms.text(), 'Evidence and publication rules', 'llms evidence policy');

  const indexNow = await request(`/${indexNowKey}.txt`);
  expectStatus(indexNow, 200, 'IndexNow key');
  expectIncludes(await indexNow.text(), indexNowKey, 'IndexNow key');

  return ['/', '/explore/', '/signals/', '/methodology/', '/robots.txt', '/sitemap.xml', '/llms.txt', 'IndexNow key'];
};

const verifyDesign = async () => {
  const home = await request('/');
  expectStatus(home, 200, '/');
  const html = await home.text();
  for (const value of [
    '/assets/site-visual-v5.css',
    '/assets/busisi-mark-v2.svg',
    '/assets/busisi-masthead.webp',
    'Illustrative view · not a project record',
  ]) expectIncludes(html, value, 'home design');
  if (/busisi-mark\.webp|auva\s*labs?/i.test(html)) fail('home design: retired branding is public');

  const css = await request('/assets/site-visual-v5.css');
  expectStatus(css, 200, 'design CSS');
  expectContentType(css, 'text/css', 'design CSS');
  const cssText = await css.text();
  for (const value of ['Source Sans 3', '--paper:#fff', '--text-xs:.8125rem', '.hero-art-note', '.explorer-shell']) {
    expectIncludes(cssText, value, 'design CSS');
  }
  if (/Merriweather|Georgia|Times New Roman/i.test(cssText)) fail('design CSS: decorative serif font remains');

  const mark = await request('/assets/busisi-mark-v2.svg');
  expectStatus(mark, 200, 'brand mark');
  expectContentType(mark, 'image/svg+xml', 'brand mark');
  const markText = await mark.text();
  if (markText.length > 4_096 || /<script/i.test(markText)) fail('brand mark: unsafe or oversized SVG');

  const masthead = await request('/assets/busisi-masthead.webp');
  expectStatus(masthead, 200, 'masthead');
  expectContentType(masthead, 'image/webp', 'masthead');
  const mastheadBytes = Buffer.from(await masthead.arrayBuffer());
  if (mastheadBytes.length > 100_000) fail('masthead: exceeds the 100 KB performance budget');
  expectBytes(mastheadBytes.subarray(0, 4), 'RIFF', 'masthead');
  expectBytes(mastheadBytes.subarray(8, 12), 'WEBP', 'masthead');

  const sourceSansBytes = await verifyFont('/assets/source-sans-3-latin.woff2');

  return {
    mark_bytes: Buffer.byteLength(markText),
    masthead_bytes: mastheadBytes.length,
    font_bytes: sourceSansBytes,
  };
};

const verifyData = async () => {
  const stats = (await readJson('/api/v1/stats')).data;
  for (const [key, value] of Object.entries(expectedCounts)) {
    if (stats[key] !== value) fail(`stats: ${key} expected ${value}, received ${stats[key]}`);
  }
  for (const [key, value] of Object.entries(expectedArtifacts)) {
    if (stats[key] !== value) fail(`stats: ${key} does not match the release artifact`);
  }

  const budget = await readJson('/api/v1/budgets?q=pumping&year=2025&limit=1');
  if (budget.meta.total < 1 || budget.data.length !== 1) fail('budget query: no matching records');
  expectIncludes(budget.data[0].source_url, 'budget.bettergov.ph', 'budget source URL');

  const delivery = await readJson('/api/v1/delivery?q=Manila&limit=1');
  if (delivery.meta.total < 1 || delivery.data.length !== 1) fail('delivery query: no matching records');
  expectIncludes(delivery.data[0].source_url, 'api.dpwh.bettergov.ph', 'delivery source URL');

  const candidates = await readJson('/api/v1/candidates?limit=1');
  if (candidates.meta.total !== expectedCounts.candidate_links) fail('candidate query: count mismatch');
  if (candidates.meta.review_scope !== 'unreviewed_candidates') fail('candidate query: review scope missing');

  const reviewed = await readJson('/api/v1/projects?status=reviewed&limit=1');
  if (reviewed.meta.total !== 5 || reviewed.data.length !== 1) fail('reviewed query: count mismatch');

  return { ...expectedCounts, reviewed_public: reviewed.meta.total };
};

const verifyBoundaries = async () => {
  const missing = ['/projects/example', '/not-a-page'];
  for (const path of missing) {
    const response = await request(path);
    expectStatus(response, 404, path);
    expectIncludes(await response.text(), 'noindex, nofollow', `${path} robots`);
  }

  const watchlist = await request('/watchlist/');
  expectStatus(watchlist, 302, '/watchlist/');
  if (watchlist.headers.get('location') !== `${origin}/explore/?view=reviewed`) {
    fail('/watchlist/: unexpected redirect destination');
  }

  const reviewed = await request('/projects/corazon-2024-phase-1/');
  expectStatus(reviewed, 200, 'reviewed dossier');
  const reviewedText = await reviewed.text();
  expectIncludes(reviewedText, 'Reviewed link', 'reviewed dossier');
  if (reviewedText.includes('noindex, nofollow')) fail('reviewed dossier: unexpectedly noindex');

  const quarantined = await request('/projects/corazon-2026-completion/');
  expectStatus(quarantined, 200, 'quarantined dossier');
  const quarantinedText = await quarantined.text();
  expectIncludes(quarantinedText, 'Quarantined candidate', 'quarantined dossier');
  expectIncludes(quarantinedText, 'noindex, nofollow', 'quarantined dossier robots');

  const post = await request('/', { method: 'POST' });
  expectStatus(post, 405, 'POST /');

  const redirect = await fetch(`https://www.${expectedHost}/methodology/`, { redirect: 'manual' });
  expectStatus(redirect, 301, 'www redirect');
  if (redirect.headers.get('location') !== `${origin}/methodology/`) {
    fail('www redirect: unexpected destination');
  }
  return { missing, quarantined: '/projects/corazon-2026-completion/' };
};

const main = async () => {
  const dns = await verifyDns();
  const pages = await verifyPages();
  const design = await verifyDesign();
  const data = await verifyData();
  const boundaries = await verifyBoundaries();
  console.log(JSON.stringify({ passed: true, origin, dns, pages, design, data, boundaries }, null, 2));
};

main().catch((error) => {
  console.error(JSON.stringify({ passed: false, origin, error: error.message }, null, 2));
  process.exitCode = 1;
});
