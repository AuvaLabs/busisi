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
const expectedChanges = Object.freeze({
  record_count: 20_431,
  quarantine_count: 426,
  fiscal_year: 2027,
  source_commit: 'a0caa778442cdae5583f5a006ea7401dab00e5ac',
});
const expectedBudgetCycle = Object.freeze({
  fiscal_year: '2027',
  document_count: '5',
  verified_document_count: '2',
  discovered_document_count: '3',
  catalog_sha256: '7fb461156cba8bd04b48315b298fb2b908506b6a2bb6e3df656d179ad59608ff',
});
const expectedCoa = Object.freeze({
  report_count: '4',
  archived_reports: '0',
  checked_projects: '6',
  project_matches: '0',
  catalog_sha256: '4c6cbc56a5226dff8499f097bf8c800c1b952ed51198cce4842b724b2498d4ba',
});
const expectedProcurement = Object.freeze({
  source_count: '3',
  archived_sources: '1',
  record_count: '4',
  exact_records: '4',
  checked_projects: '6',
  projects_with_evidence: '3',
  catalog_sha256: '4f9d9d76fe00fa4f31bf274a5834964978c6f4a137bf8b7aeed3e8983e0b8d91',
});
const expectedReviewCounts = Object.freeze({
  decreased: 265,
  house_only: 6_954,
  increased: 243,
  nep_only: 1_784,
  scope_review: 37,
  unchanged: 11_148,
});
const expectedIntegrity = Object.freeze({
  source_records: 56_887,
  delivery_details: 56_887,
  integrity_signals: 16_814,
  contractors: 4_297,
  concentrations: 737,
  pcab_records: 18_868,
  pcab_retrieved_on: '2026-11-03',
  pcab_source_sha256: '016bc9e3427b55e7744558f7726eb773f02f496f88279987c473546d6edb97d2',
  source_artifact_sha256: '5b411cf3f112fabd1913c70681791e5e2b78b43a8393f489f48bd882f154e123',
  district_count: 254,
  district_offices: 199,
  district_source_commit: 'a0caa778442cdae5583f5a006ea7401dab00e5ac',
  district_source_built_at: '2026-10-26T08:46:14.383Z',
  district_source_retrieved_on: '2026-11-03',
  district_snapshot_sha256: 'dc78c26838c81da134e2ae7523a45f0bd7792d2a01e06f6694fc351a25650e46',
});
const expectedDistrictCoverage = Object.freeze({
  shared_office: 14_027,
  single_district: 35_166,
  unassigned: 7_694,
});
const expectedIntegritySignals = Object.freeze({
  completed_progress_conflict: 7,
  completed_without_satellite_image: 2_029,
  coordinate_location_conflict: 5,
  date_order_conflict: 1,
  missing_coordinate: 7_771,
  nonpositive_active_budget: 23,
  reused_coordinate: 1_230,
  same_site_repeat_family: 4,
  status_progress_conflict: 5_744,
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

const verifyHtmlRecord = async (path, expected) => {
  const response = await request(path);
  expectStatus(response, 200, path);
  expectContentType(response, 'text/html', path);
  const body = await response.text();
  expectIncludes(body, expected, path);
  expectIncludes(body, 'Evidence boundary', `${path} evidence boundary`);
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
  const methodologyText = await methodology.text();
  expectIncludes(methodologyText, '100 reviewed linkage cases', 'methodology gate');
  expectIncludes(methodologyText, 'Congressional district context', 'methodology district boundary');

  const publicValue = await request('/sulit/');
  expectStatus(publicValue, 200, '/sulit/');
  const publicValueText = await publicValue.text();
  expectIncludes(publicValueText, '₱7.2 trillion. Sulit ba para sa Pilipino?', 'public value heading');
  expectIncludes(publicValueText, '/assets/public-value-v1.js', 'public value client');
  expectIncludes(publicValueText, 'Motive cannot be inferred', 'public value limitation');

  const explore = await request('/explore/');
  expectStatus(explore, 200, '/explore/');
  const exploreText = await explore.text();
  expectIncludes(exploreText, 'Explore official budget records', 'explorer heading');
  expectIncludes(exploreText, 'Unreviewed candidates are not public findings', 'explorer warning');

  const signals = await request('/signals/');
  expectStatus(signals, 200, '/signals/');
  const signalsText = await signals.text();
  expectIncludes(signalsText, 'Start with the records that moved', 'review desk heading');
  expectIncludes(signalsText, '/assets/review-v1.js', 'review desk client');
  expectIncludes(signalsText, 'Full insertion analysis', 'signals evidence gaps');
  expectIncludes(signalsText, 'Physical existence verification', 'signals evidence gaps');

  const integrity = await request('/integrity/');
  expectStatus(integrity, 200, '/integrity/');
  const integrityText = await integrity.text();
  expectIncludes(integrityText, 'Inspect contradictions in delivery records', 'integrity heading');
  expectIncludes(integrityText, '/assets/integrity-v1.js', 'integrity client');
  expectIncludes(integrityText, 'Contractors with the most projects', 'contractor ranking');
  expectIncludes(integrityText, 'What this desk flags', 'integrity limitation');

  const changes = await request('/changes/');
  expectStatus(changes, 200, '/changes/');
  const changesText = await changes.text();
  expectIncludes(changesText, 'Trace what changed between the NEP and House bill', 'changes heading');
  expectIncludes(changesText, 'How to read a change', 'changes warning');

  const budgetTrail = await request('/budget-trail/');
  expectStatus(budgetTrail, 200, '/budget-trail/');
  const budgetTrailText = await budgetTrail.text();
  expectIncludes(budgetTrailText, 'Follow the FY2027 budget through each published stage', 'budget trail heading');
  expectIncludes(budgetTrailText, '/assets/budget-cycle-v1.js', 'budget trail client');
  expectIncludes(budgetTrailText, 'Publisher is not stage', 'budget trail evidence boundary');

  const audit = await request('/audit/');
  expectStatus(audit, 200, '/audit/');
  const auditText = await audit.text();
  expectIncludes(auditText, 'COA audit evidence desk', 'audit desk heading');
  expectIncludes(auditText, 'Absence is not clearance', 'audit desk evidence boundary');
  expectIncludes(auditText, '6 dossiers checked', 'audit desk coverage');

  const procurement = await request('/procurement/');
  expectStatus(procurement, 200, '/procurement/');
  const procurementText = await procurement.text();
  expectIncludes(procurementText, 'Procurement evidence desk', 'procurement desk heading');
  expectIncludes(procurementText, '3 of 6 reviewed dossiers', 'procurement desk coverage');
  expectIncludes(procurementText, 'Evidence gap, not a clean bill', 'procurement boundary');
  expectIncludes(procurementText, 'Contract evidence acquisition ledger', 'acquisition ledger');
  expectIncludes(procurementText, '3 acquisition checks queued', 'acquisition retry queue');
  expectIncludes(procurementText, 'Contract outcome cross-checks', 'contract outcome heading');
  expectIncludes(procurementText, 'Questions, not findings', 'contract outcome boundary');

  const robots = await request('/robots.txt');
  expectStatus(robots, 200, '/robots.txt');
  expectIncludes(await robots.text(), `Sitemap: ${origin}/sitemap.xml`, 'robots sitemap');

  const sitemap = await request('/sitemap.xml');
  expectStatus(sitemap, 200, '/sitemap.xml');
  const sitemapText = await sitemap.text();
  for (const path of ['/sulit/', '/explore/', '/changes/', '/budget-trail/', '/audit/', '/procurement/', '/signals/', '/integrity/', '/methodology/', '/projects/corazon-2024-phase-1/']) {
    expectIncludes(sitemapText, `<loc>${origin}${path}</loc>`, `sitemap ${path}`);
  }
  if (sitemapText.includes('corazon-2026-completion')) fail('sitemap: quarantined dossier is indexed');

  const llms = await request('/llms.txt');
  expectStatus(llms, 200, '/llms.txt');
  expectIncludes(await llms.text(), 'Evidence and publication rules', 'llms evidence policy');

  const indexNow = await request(`/${indexNowKey}.txt`);
  expectStatus(indexNow, 200, 'IndexNow key');
  expectIncludes(await indexNow.text(), indexNowKey, 'IndexNow key');

  return ['/', '/sulit/', '/explore/', '/changes/', '/budget-trail/', '/audit/', '/procurement/', '/signals/', '/integrity/', '/methodology/', '/robots.txt', '/sitemap.xml', '/llms.txt', 'IndexNow key'];
};

const verifyDesign = async () => {
  const home = await request('/');
  expectStatus(home, 200, '/');
  const html = await home.text();
  for (const value of [
    '/assets/site-visual-v10.css',
    '/assets/busisi-mark-v2.svg',
    '/assets/busisi-social-v1.png',
    '/assets/busisi-evidence-banner-v1.webp',
    '/assets/busisi-icons-v1.svg#appropriations',
    'class="home-ledger"',
    'Current FY2027 budget evidence',
  ]) expectIncludes(html, value, 'home design');
  if (/busisi-mark\.webp|busisi-masthead\.webp|auva\s*labs?/i.test(html)) {
    fail('home design: retired branding or illustration is public');
  }

  const css = await request('/assets/site-visual-v10.css');
  expectStatus(css, 200, 'design CSS');
  expectContentType(css, 'text/css', 'design CSS');
  const cssText = await css.text();
  for (const value of [
    'Source Sans 3', '--paper:#fff', '--ink:#111', '--accent:#111', '.home-ledger',
    '.explorer-shell', '.review-shell', '.integrity-shell', '.contractor-shell',
    '.lifecycle-grid', '.lifecycle-item',
  ]) {
    expectIncludes(cssText, value, 'design CSS');
  }
  if (/Merriweather|Georgia|Times New Roman/i.test(cssText)) fail('design CSS: decorative serif font remains');

  const mark = await request('/assets/busisi-mark-v2.svg');
  expectStatus(mark, 200, 'brand mark');
  expectContentType(mark, 'image/svg+xml', 'brand mark');
  const markText = await mark.text();
  if (markText.length > 4_096 || /<script/i.test(markText)) fail('brand mark: unsafe or oversized SVG');

  const socialCard = await request('/assets/busisi-social-v1.png');
  expectStatus(socialCard, 200, 'social card');
  expectContentType(socialCard, 'image/png', 'social card');
  const socialCardBytes = Buffer.from(await socialCard.arrayBuffer());
  if (socialCardBytes.length > 250_000) fail('social card: exceeds the 250 KB performance budget');
  expectBytes(socialCardBytes.subarray(1, 4), 'PNG', 'social card');

  const banner = await request('/assets/busisi-evidence-banner-v1.webp');
  expectStatus(banner, 200, 'editorial banner');
  expectContentType(banner, 'image/webp', 'editorial banner');
  const bannerBytes = Buffer.from(await banner.arrayBuffer());
  if (bannerBytes.length > 200_000) fail('editorial banner: exceeds the 200 KB performance budget');
  expectBytes(bannerBytes.subarray(0, 4), 'RIFF', 'editorial banner');
  expectBytes(bannerBytes.subarray(8, 12), 'WEBP', 'editorial banner');

  const icons = await request('/assets/busisi-icons-v1.svg');
  expectStatus(icons, 200, 'icon system');
  expectContentType(icons, 'image/svg+xml', 'icon system');
  const iconText = await icons.text();
  if (iconText.length > 12_000 || /<script/i.test(iconText)) fail('icon system: unsafe or oversized SVG');

  const sourceSansBytes = await verifyFont('/assets/source-sans-3-latin.woff2');

  return {
    mark_bytes: Buffer.byteLength(markText),
    social_card_bytes: socialCardBytes.length,
    banner_bytes: bannerBytes.length,
    icon_bytes: Buffer.byteLength(iconText),
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
  await verifyHtmlRecord(budget.data[0].reader_source_url, 'Official GAA appropriation record');

  const delivery = await readJson('/api/v1/delivery?q=24CM0078&limit=1');
  if (delivery.meta.total < 1 || delivery.data.length !== 1) fail('delivery query: no matching records');
  expectIncludes(delivery.data[0].source_url, 'api.dpwh.bettergov.ph', 'delivery source URL');
  await verifyHtmlRecord(delivery.data[0].reader_source_url, 'Official DPWH delivery record');
  if (delivery.data[0].district_context?.classification === 'unassigned'
    || !delivery.data[0].district_context?.districts.length) {
    fail('delivery query: district context missing');
  }

  const candidates = await readJson('/api/v1/candidates?limit=1');
  if (candidates.meta.total !== expectedCounts.candidate_links) fail('candidate query: count mismatch');
  if (candidates.meta.review_scope !== 'unreviewed_candidates') fail('candidate query: review scope missing');
  await verifyHtmlRecord(candidates.data[0].review_url, 'Unreviewed candidate comparison');

  const changeStats = (await readJson('/api/v1/change-stats')).data;
  for (const [key, value] of Object.entries(expectedChanges)) {
    if (changeStats[key] !== value) {
      fail(`change stats: ${key} expected ${value}, received ${changeStats[key]}`);
    }
  }
  const changes = await readJson('/api/v1/changes?change=house_only&limit=1');
  if (changes.meta.total < 1 || changes.data.length !== 1) fail('change query: no House-only records');
  if (changes.meta.review_scope !== 'provisional_stage_comparisons') {
    fail('change query: review scope missing');
  }
  expectIncludes(changes.data[0].source_url, 'budget.bettergov.ph', 'change source URL');
  if (!changes.data[0].house_pdf_url) fail('change query: House evidence link missing');
  await verifyHtmlRecord(
    `/records/change/${encodeURIComponent(changes.data[0].record_id)}/`,
    'Provisional stage comparison',
  );

  const budgetCycle = (await readJson('/api/v1/budget-cycle')).data;
  for (const [key, expected] of Object.entries(expectedBudgetCycle)) {
    if (budgetCycle.metadata[key] !== expected) {
      fail(`budget cycle: ${key} expected ${expected}, received ${budgetCycle.metadata[key]}`);
    }
  }
  const unavailableStages = budgetCycle.stages
    .filter(({ status }) => status === 'unavailable')
    .map(({ stage }) => stage);
  for (const stage of ['senate_committee', 'senate_amendment', 'bicam', 'gaa']) {
    if (!unavailableStages.includes(stage)) fail(`budget cycle: ${stage} should be unavailable`);
  }
  const cycleDocuments = await readJson('/api/v1/budget-cycle/documents');
  if (cycleDocuments.meta.total !== 5
    || cycleDocuments.meta.review_scope !== 'source_separated_budget_cycle_catalogue') {
    fail('budget cycle documents: count or review scope mismatch');
  }

  const coaSummary = (await readJson('/api/v1/coa-summary')).data;
  for (const [key, expected] of Object.entries(expectedCoa)) {
    if (coaSummary.metadata[key] !== expected) {
      fail(`COA summary: ${key} expected ${expected}, received ${coaSummary.metadata[key]}`);
    }
  }
  if (coaSummary.statuses.not_covered !== 6 || coaSummary.catalogs.length !== 4) {
    fail('COA summary: coverage status or catalogue count mismatch');
  }
  const coaReports = await readJson('/api/v1/coa-reports');
  if (coaReports.meta.total !== 4
    || coaReports.meta.review_scope !== 'official_coa_report_catalogue'
    || !coaReports.data.every((report) => report.acquisition_status === 'discovered')) {
    fail('COA reports: count, scope or acquisition boundary mismatch');
  }
  await verifyHtmlRecord(
    '/audit/reports/coa-oda-consolidated-2024/',
    'Source copy not archived',
  );
  const procurementSummary = (await readJson('/api/v1/procurement-summary')).data;
  for (const [key, expected] of Object.entries(expectedProcurement)) {
    if (procurementSummary.metadata[key] !== expected) {
      fail(`procurement summary: ${key} expected ${expected}, received ${procurementSummary.metadata[key]}`);
    }
  }
  if (procurementSummary.statuses.exact_evidence !== 3
    || procurementSummary.statuses.not_located !== 2
    || procurementSummary.statuses.quarantined !== 1) {
    fail('procurement summary: coverage status counts mismatch');
  }
  const procurementRecords = await readJson('/api/v1/procurement-records');
  if (procurementRecords.meta.total !== 4
    || procurementRecords.meta.review_scope !== 'exact_official_procurement_evidence'
    || procurementRecords.data.filter(({ acquisition_status }) => (
      acquisition_status === 'verified_archived'
    )).length !== 1) {
    fail('procurement records: count, scope or acquisition boundary mismatch');
  }
  const contractOutcomes = await readJson('/api/v1/contract-outcomes');
  if (contractOutcomes.meta.total !== 3
    || contractOutcomes.meta.review_scope !== 'deterministic_cross_source_contract_outcomes'
    || !contractOutcomes.data.every(({
      awardee_evidence: awardee, awardee_check: awardeeCheck, payment_evidence: payment,
    }) => (
      awardee.state === 'secondary'
      && awardeeCheck.state === 'consistent_secondary'
      && payment.state === 'gap'
    ))) {
    fail('contract outcomes: count, scope or secondary-evidence boundary mismatch');
  }
  const amountMismatch = contractOutcomes.data.find(({ contract_id: id }) => id === '24HI0131');
  if (amountMismatch?.amount_check.difference_centavos !== 22979
    || !amountMismatch.questions.some(({ code }) => code === 'completion_status_conflict')) {
    fail('contract outcomes: 24HI0131 amount or completion cross-check mismatch');
  }
  const contractEvidence = await readJson('/api/v1/contract-evidence');
  if (contractEvidence.meta.total !== 27
    || contractEvidence.meta.contracts !== 3
    || contractEvidence.meta.retry_items !== 3
    || contractEvidence.meta.review_scope !== 'contract_lifecycle_document_acquisition'
    || contractEvidence.meta.statuses.verified_archived !== 1
    || contractEvidence.meta.statuses.blocked !== 3
    || contractEvidence.meta.statuses.secondary !== 3
    || contractEvidence.meta.statuses.not_located !== 20) {
    fail('contract evidence: count, scope or status controls mismatch');
  }
  const phaseOneNtp = contractEvidence.data.find(({ contract_id: id, stage }) => (
    id === '24HI0148' && stage === 'notice_to_proceed'
  ));
  if (phaseOneNtp?.status !== 'not_located'
    || phaseOneNtp.reported_date !== '2024-09-05'
    || phaseOneNtp.date_kind !== 'actual') {
    fail('contract evidence: reported event and missing-document boundary mismatch');
  }
  if (cycleDocuments.data.filter(({ acquisition_status }) => (
    acquisition_status === 'verified_archived'
  )).length !== 2) {
    fail('budget cycle documents: verified copy count mismatch');
  }

  const publicValueSummary = (await readJson('/api/v1/public-value-summary')).data;
  for (const [key, expected] of Object.entries({
    reading: 'mixed', indicator_count: 19, improving_count: 3, pressure_count: 6,
    context_count: 10, revenue_coverage_bps: 7544,
    expenditure_per_capita_centavos: 6244753,
  })) {
    if (publicValueSummary[key] !== expected) {
      fail(`public value summary: ${key} expected ${expected}, received ${publicValueSummary[key]}`);
    }
  }
  const publicValueIndicators = await readJson('/api/v1/public-value-indicators');
  if (publicValueIndicators.data.length !== 19
    || publicValueIndicators.meta.review_scope !== 'official_dbm_fiscal_program') {
    fail('public value indicators: count or evidence scope mismatch');
  }
  if (!publicValueIndicators.data.every((row) => row.source_url?.startsWith('https://www.dbm.gov.ph/')
    && row.artifact_sha256?.length === 64)) {
    fail('public value indicators: official source evidence missing');
  }

  const reviewSummary = (await readJson('/api/v1/review-summary')).data;
  if (reviewSummary.quarantine_count !== expectedChanges.quarantine_count) {
    fail('review summary: quarantine count mismatch');
  }
  for (const [changeType, expected] of Object.entries(expectedReviewCounts)) {
    const item = reviewSummary.changes.find((row) => row.change_type === changeType);
    if (!item || item.record_count !== expected) {
      fail(`review summary: ${changeType} expected ${expected}`);
    }
  }
  const repeated = await readJson('/api/v1/review-rankings?signal=repeat_family&limit=1');
  if (repeated.meta.total !== 953 || repeated.data.length !== 1) {
    fail('review rankings: repeated-family count mismatch');
  }
  if (!repeated.data[0].prior_years.length || !repeated.data[0].source_url) {
    fail('review rankings: repeated-family evidence missing');
  }
  const concentration = await readJson(
    '/api/v1/review-concentrations?signal=house_only&dimension=region&limit=1',
  );
  if (concentration.data[0]?.label !== 'Region IV-A') {
    fail('review concentrations: leading region mismatch');
  }

  const reviewCsv = await request('/api/v1/review.csv?signal=increased&dataset=hfep');
  expectStatus(reviewCsv, 200, 'review CSV');
  expectContentType(reviewCsv, 'text/csv', 'review CSV');
  expectIncludes(await reviewCsv.text(), 'comparison_record', 'review CSV');

  const integritySummary = (await readJson('/api/v1/integrity-summary')).data;
  for (const [key, value] of Object.entries(expectedIntegrity)) {
    if (integritySummary[key] !== value) {
      fail(`integrity summary: ${key} expected ${value}, received ${integritySummary[key]}`);
    }
  }
  const districtCoverage = Object.fromEntries(
    integritySummary.district_coverage.map((item) => [item.classification, item.count]),
  );
  for (const [classification, expected] of Object.entries(expectedDistrictCoverage)) {
    if (districtCoverage[classification] !== expected) {
      fail(`integrity summary: district ${classification} expected ${expected}`);
    }
  }
  const integritySignalMap = Object.fromEntries(
    integritySummary.signals.map((item) => [item.code, item.count]),
  );
  for (const [code, value] of Object.entries(expectedIntegritySignals)) {
    if (integritySignalMap[code] !== value) {
      fail(`integrity summary: ${code} expected ${value}, received ${integritySignalMap[code]}`);
    }
  }
  const coordinateReview = await readJson(
    '/api/v1/integrity-signals?signal=coordinate_location_conflict&limit=1',
  );
  if (coordinateReview.meta.total !== expectedIntegritySignals.coordinate_location_conflict) {
    fail('integrity query: coordinate-location conflict count mismatch');
  }
  if (!coordinateReview.data[0]?.source_url || !coordinateReview.data[0]?.limitations) {
    fail('integrity query: source evidence or limitation missing');
  }
  await verifyHtmlRecord(
    `/records/integrity/${encodeURIComponent(coordinateReview.data[0].signal_id)}/`,
    'Review signal, not a finding',
  );
  const districtReview = await readJson(
    '/api/v1/integrity-signals?q=Metro%20Manila%201st%20DEO&limit=1',
  );
  const districtContext = districtReview.data[0]?.district_context;
  if (districtContext?.classification !== 'shared_office' || districtContext.districts.length !== 7) {
    fail('integrity query: shared district-office context missing');
  }
  if (!districtContext.districts.every((seat) => seat.representative_profile_url
    ?.startsWith('https://www.congress.gov.ph/house-members/view/'))) {
    fail('integrity query: official representative profiles missing');
  }
  const contractorsByCount = await readJson('/api/v1/contractors?sort=count_desc&limit=1');
  const contractorsByBudget = await readJson('/api/v1/contractors?sort=budget_desc&limit=1');
  for (const [label, payload] of [
    ['count', contractorsByCount],
    ['budget', contractorsByBudget],
  ]) {
    if (payload.meta.total !== expectedIntegrity.contractors || payload.data.length !== 1) {
      fail(`contractor query: ${label} ranking count mismatch`);
    }
    if (!payload.data[0].contractor_name || !payload.data[0].pcab_url
      || !payload.data[0].pcab_status) {
      fail(`contractor query: ${label} ranking evidence missing`);
    }
  }
  await verifyHtmlRecord(
    `/contractors/${encodeURIComponent(contractorsByCount.data[0].contractor_key)}/`,
    'Archived contractor activity',
  );
  const concentrations = await readJson(
    '/api/v1/contractor-concentrations?dimension=region&year=0',
  );
  if (!concentrations.data.length
    || concentrations.meta.denominator !== 'contractor_party_associations') {
    fail('contractor concentration: denominator or records missing');
  }
  const integrityCsv = await request('/api/v1/integrity.csv?signal=date_order_conflict');
  expectStatus(integrityCsv, 200, 'integrity CSV');
  expectContentType(integrityCsv, 'text/csv', 'integrity CSV');
  expectIncludes(await integrityCsv.text(), 'source_artifact_sha256', 'integrity CSV');

  const reviewed = await readJson('/api/v1/projects?status=reviewed&limit=1');
  if (reviewed.meta.total !== 5 || reviewed.data.length !== 1) fail('reviewed query: count mismatch');

  return {
    ...expectedCounts,
    stage_changes: changeStats.record_count,
    integrity_signals: integritySummary.integrity_signals,
    contractors: integritySummary.contractors,
    district_offices: integritySummary.district_offices,
    public_value_indicators: publicValueSummary.indicator_count,
    budget_cycle_documents: cycleDocuments.meta.total,
    reviewed_public: reviewed.meta.total,
  };
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
  expectIncludes(reviewedText, 'Reviewed project evidence dossier', 'reviewed dossier');
  expectIncludes(reviewedText, 'Related reviewed phases', 'reviewed dossier');
  for (const value of [
    'Recorded implementation details', 'Completed', '100.0%', 'LA PRUEBA CONSTRUCTION',
    '2024-09-05', '2024-12-18', '10.7218472, 124.0110944',
    'Identifiers and archived source fingerprints', 'Reader evidence links',
    'Procurement timeline', 'Notice of award', 'Page 6', '₱5,324.90',
    'Contract outcome pack', 'Payment evidence',
    'Contract evidence checklist', 'Reported date, document missing', 'HTTP 403',
    'Awardee reported by the PhilGEPS mirror', 'LA PRUEBA CONSTRUCTION',
    'complete source file and official award page not archived',
  ]) expectIncludes(reviewedText, value, 'reviewed dossier detail');
  if (/api\.dpwh\.bettergov\.ph|budget\.bettergov\.ph\/api/.test(reviewedText)) {
    fail('reviewed dossier: raw API reader link is public');
  }
  if (reviewedText.includes('noindex, nofollow')) fail('reviewed dossier: unexpectedly noindex');

  const quarantined = await request('/projects/corazon-2026-completion/');
  expectStatus(quarantined, 200, 'quarantined dossier');
  const quarantinedText = await quarantined.text();
  expectIncludes(quarantinedText, 'Quarantined project candidate', 'quarantined dossier');
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
