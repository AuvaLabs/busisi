import { Resolver } from 'node:dns/promises';

import { INDEX_NOW_KEY, SITE } from '../src/prelaunch-config.js';

const publicOrigin = SITE.origin;
const requestOrigin = process.env.BUSISI_ORIGIN ?? publicOrigin;
const monitorToken = process.env.BUSISI_MONITOR_TOKEN ?? '';
const expectedHost = new URL(publicOrigin).hostname;
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
const expectedReleases = Object.freeze({
  fiscal_year: 2026,
  as_of_date: '2026-09-30',
  record_count: 96,
  department_count: 36,
  attached_agency_count: 47,
  special_purpose_fund_count: 13,
  current_gaa_adjusted_centavos: 439_104_496_900_000,
  current_gaa_releases_centavos: 407_222_774_000_000,
  current_gaa_balance_centavos: 31_881_722_900_000,
  total_program_centavos: 679_316_200_000_000,
  total_releases_centavos: 653_295_146_600_000,
  total_balance_centavos: 26_021_053_400_000,
  source_sha256: '05a902418e0a78339b82d71def04447eab44897b752d001343121bcbe6226aae',
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
const expectedAcquisitionCoverage = Object.freeze({
  contract_count: 56_887,
  examined_contracts: 56_887,
  accepted_match_rows: 62_129,
  quarantined_source_rows: 83,
  lifecycle_task_count: 511_983,
  award_source_rows: 5_481_161,
  award_sha256: '9bfa9e7cbf5041dc3b51a4c2742e60a43d1615f119955581d4b155bf3a6d4a8b',
});
const expectedImageCoverage = Object.freeze({
  universe_contracts: 56_890,
  source_sha256: expectedArtifacts.delivery_artifact_sha256,
  minimum_verified_images: 5,
  minimum_quarantined_images: 13,
});
const coverageReleaseMaxAgeMs = 8 * 60 * 60 * 1000;
const sourceMonitorMaxAgeMs = 8 * 60 * 60 * 1000;
const expectedContractStates = Object.freeze({
  conflict_review: 161,
  multiple_exact_rows: 2_077,
  no_exact_row: 9_655,
  structured_exact: 38_110,
  title_exact: 6_884,
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
  contractor_associations: 53_201,
  concentrations: 737,
  pcab_records: 18_853,
  pcab_retrieved_on: '2026-11-03',
  pcab_source_sha256: 'e3ed711707a5c2e52efe907148d59b39a028b78fa0458d840250dad977362fa1',
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
const expectedPublicServices = Object.freeze({
  total: 6_050,
  budget: 937,
  delivery: 5_113,
  school: 4_722,
  hospital: 671,
  health_center: 657,
  new_build: 3_611,
  rehabilitation: 798,
  expansion: 31,
  equipment: 1,
  continuation: 703,
  unspecified: 906,
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
    return await fetch(`${requestOrigin}${path}`, {
      redirect: 'manual',
      ...options,
      headers: {
        Accept: '*/*',
        'User-Agent': 'BusisiProductionMonitor/1.0 (+https://busisi.org/methodology/)',
        ...(monitorToken ? { 'X-Busisi-Monitor-Token': monitorToken } : {}),
        ...options.headers,
      },
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
  expectIncludes(homeText, `<link rel="canonical" href="${publicOrigin}/">`, 'home canonical');
  expectIncludes(homeText, '"@type":"WebSite"', 'home structured data');
  expectIncludes(homeText, 'index, follow, max-image-preview:large', 'home robots');
  expectIncludes(
    homeText,
    'Busisi is a nonpartisan public-interest data platform for Filipinos',
    'home positioning',
  );
  expectIncludes(homeText, 'https://auvalabs.com/', 'Auva Labs project credit');
  expectIncludes(homeText, 'mailto:dev@auvalabs.com', 'project contact');
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
  expectIncludes(methodologyText, 'Discovery can be automatic', 'methodology automation boundary');
  expectIncludes(methodologyText, 'Nonpartisan by policy', 'methodology independence');
  expectIncludes(
    methodologyText,
    'no affiliation with any politician, political party, candidate',
    'methodology political boundary',
  );
  expectIncludes(
    methodologyText,
    'BetterGov does not operate, sponsor, or endorse Busisi',
    'methodology data-source boundary',
  );

  const coverage = await request('/coverage/');
  expectStatus(coverage, 200, '/coverage/');
  const coverageText = await coverage.text();
  expectIncludes(coverageText, 'See how many project images Busisi has checked', 'coverage heading');
  expectIncludes(coverageText, 'No AI model decides whether an image is published', 'coverage boundary');
  expectIncludes(coverageText, 'Did the sources change?', 'coverage source monitor');

  const publicValue = await request('/sulit/');
  expectStatus(publicValue, 200, '/sulit/');
  const publicValueText = await publicValue.text();
  expectIncludes(publicValueText, '₱7.2 trillion. Sulit ba para sa Pilipino?', 'public value heading');
  expectIncludes(publicValueText, '/assets/public-value-v1.js?v=2', 'public value client');
  expectIncludes(publicValueText, 'Motive cannot be inferred', 'public value limitation');

  const explore = await request('/explore/');
  expectStatus(explore, 200, '/explore/');
  const exploreText = await explore.text();
  expectIncludes(exploreText, 'Explore official budget records', 'explorer heading');
  expectIncludes(exploreText, '/assets/explorer-v1.js?v=2', 'explorer client');
  expectIncludes(exploreText, 'Unreviewed candidates are not public findings', 'explorer warning');

  const contracts = await request('/contracts/');
  expectStatus(contracts, 200, '/contracts/');
  const contractsText = await contracts.text();
  expectIncludes(contractsText, 'Contract intelligence explorer', 'contract explorer heading');
  expectIncludes(contractsText, '/assets/contracts-v1.js?v=3', 'contract explorer client');
  expectIncludes(contractsText, 'Province or district office', 'contract province filter');
  expectIncludes(contractsText, 'Source patterns are review leads, not findings', 'contract explorer boundary');

  const signals = await request('/signals/');
  expectStatus(signals, 200, '/signals/');
  const signalsText = await signals.text();
  expectIncludes(signalsText, 'Find budget changes that need a closer look', 'review desk heading');
  expectIncludes(signalsText, '/assets/review-v1.js?v=3', 'review desk client');
  expectIncludes(signalsText, 'Full insertion analysis', 'signals evidence gaps');
  expectIncludes(signalsText, 'Physical existence verification', 'signals evidence gaps');

  const integrity = await request('/integrity/');
  expectStatus(integrity, 200, '/integrity/');
  const integrityText = await integrity.text();
  expectIncludes(integrityText, 'Find project records that need a closer look', 'integrity heading');
  expectIncludes(integrityText, '/assets/integrity-v1.js?v=3', 'integrity client');
  expectIncludes(integrityText, 'Contractors with the most projects', 'contractor ranking');
  expectIncludes(integrityText, 'A flag is a question to check, not an accusation', 'integrity limitation');

  const changes = await request('/changes/');
  expectStatus(changes, 200, '/changes/');
  const changesText = await changes.text();
  expectIncludes(changesText, 'Trace what changed between the NEP and House bill', 'changes heading');
  expectIncludes(changesText, '/assets/changes-v1.js?v=2', 'changes client');
  expectIncludes(changesText, 'How to read a change', 'changes warning');

  const releases = await request('/releases/');
  expectStatus(releases, 200, '/releases/');
  const releasesText = await releases.text();
  expectIncludes(releasesText, 'See what DBM had released by September', 'releases heading');
  expectIncludes(releasesText, '/assets/releases-v1.js', 'releases client');
  expectIncludes(releasesText, 'Allotment release is not payment', 'releases boundary');
  expectIncludes(releasesText, expectedReleases.source_sha256, 'releases fingerprint');

  const budgetTrail = await request('/budget-trail/');
  expectStatus(budgetTrail, 200, '/budget-trail/');
  const budgetTrailText = await budgetTrail.text();
  expectIncludes(budgetTrailText, 'Follow the FY2027 budget through each published stage', 'budget trail heading');
  expectIncludes(budgetTrailText, '/assets/budget-cycle-v1.js', 'budget trail client');
  expectIncludes(budgetTrailText, 'Publisher is not stage', 'budget trail evidence boundary');

  const audit = await request('/audit/');
  expectStatus(audit, 200, '/audit/');
  const auditText = await audit.text();
  expectIncludes(auditText, 'What do COA reports say about the projects Busisi checked?', 'audit desk heading');
  expectIncludes(auditText, 'Not finding a report is not the same as COA clearance', 'audit desk evidence boundary');
  expectIncludes(auditText, '6 project files checked', 'audit desk coverage');
  expectIncludes(auditText, 'class="record-title-link"', 'audit report drill-down');

  const procurement = await request('/procurement/');
  expectStatus(procurement, 200, '/procurement/');
  const procurementText = await procurement.text();
  expectIncludes(procurementText, 'What contract documents can Busisi find?', 'procurement desk heading');
  expectIncludes(procurementText, '3 of 6 project files have evidence', 'procurement desk coverage');
  expectIncludes(procurementText, 'A missing document does not mean procurement did not happen', 'procurement boundary');
  expectIncludes(procurementText, 'Full-universe acquisition coverage', 'acquisition coverage');
  expectIncludes(procurementText, '56,887 of 56,887 contracts examined', 'acquisition coverage');
  expectIncludes(procurementText, 'Coverage is not official proof', 'acquisition boundary');
  expectIncludes(procurementText, 'Contract evidence acquisition ledger', 'acquisition ledger');
  expectIncludes(procurementText, '3 acquisition checks queued', 'acquisition retry queue');
  expectIncludes(procurementText, 'Do the contract records agree?', 'contract outcome heading');
  expectIncludes(procurementText, 'Questions to check, not findings', 'contract outcome boundary');
  expectIncludes(procurementText, 'class="record-title-link"', 'procurement dossier drill-down');

  const questions = await request('/questions/');
  expectStatus(questions, 200, '/questions/');
  const questionsText = await questions.text();
  expectIncludes(questionsText, 'What can Busisi answer today?', 'questions heading');
  expectIncludes(questionsText, 'Can partly answer', 'questions partial state');
  expectIncludes(questionsText, 'What this answer cannot prove', 'questions evidence boundary');
  expectIncludes(questionsText, 'Who inserted, sponsored, or politically motivated a line item', 'questions authorship boundary');
  if (/href="\/api\/v1\//.test(questionsText)) fail('questions: reader action exposes raw API');

  const publicServices = await request('/public-services/');
  expectStatus(publicServices, 200, '/public-services/');
  const publicServicesText = await publicServices.text();
  expectIncludes(publicServicesText, 'Schools and health facilities in the public record', 'public services heading');
  expectIncludes(publicServicesText, '/assets/public-services-v1.js', 'public services client');
  expectIncludes(publicServicesText, 'These are records, not separate buildings', 'public services counting boundary');
  expectIncludes(publicServicesText, 'Things that need checking', 'public services flag boundary');

  const robots = await request('/robots.txt');
  expectStatus(robots, 200, '/robots.txt');
  const robotsText = await robots.text();
  expectIncludes(robotsText, `Sitemap: ${publicOrigin}/sitemap.xml`, 'robots sitemap');
  expectIncludes(robotsText, 'Allow: /api/v1/questions', 'robots question API');
  expectIncludes(robotsText, 'Allow: /api/v1/public-services', 'robots public services API');

  const sitemap = await request('/sitemap.xml');
  expectStatus(sitemap, 200, '/sitemap.xml');
  const sitemapText = await sitemap.text();
  for (const path of ['/sulit/', '/releases/', '/contracts/', '/explore/', '/changes/', '/budget-trail/', '/audit/', '/procurement/', '/signals/', '/integrity/', '/coverage/', '/questions/', '/public-services/', '/methodology/', '/projects/corazon-2024-phase-1/']) {
    expectIncludes(sitemapText, `<loc>${publicOrigin}${path}</loc>`, `sitemap ${path}`);
  }
  if (sitemapText.includes('corazon-2026-completion')) fail('sitemap: quarantined dossier is indexed');

  const llms = await request('/llms.txt');
  expectStatus(llms, 200, '/llms.txt');
  const llmsText = await llms.text();
  expectIncludes(llmsText, 'Evidence and publication rules', 'llms evidence policy');
  expectIncludes(llmsText, 'nonpartisan and politically unaffiliated', 'llms independence policy');
  expectIncludes(llmsText, 'Built and maintained by Auva Labs', 'llms ownership');
  expectIncludes(llmsText, 'Evidence question catalogue', 'llms question catalogue');
  expectIncludes(llmsText, '/api/v1/questions', 'llms question API');
  expectIncludes(llmsText, 'Public services inventory', 'llms public services desk');
  expectIncludes(llmsText, '/api/v1/public-services', 'llms public services API');

  const indexNow = await request(`/${indexNowKey}.txt`);
  expectStatus(indexNow, 200, 'IndexNow key');
  expectIncludes(await indexNow.text(), indexNowKey, 'IndexNow key');

  return ['/', '/sulit/', '/releases/', '/contracts/', '/explore/', '/changes/', '/budget-trail/', '/audit/', '/procurement/', '/signals/', '/integrity/', '/coverage/', '/questions/', '/public-services/', '/methodology/', '/robots.txt', '/sitemap.xml', '/llms.txt', 'IndexNow key'];
};

const verifyDesign = async () => {
  const home = await request('/');
  expectStatus(home, 200, '/');
  const html = await home.text();
  for (const value of [
    '/assets/site-visual-v19.css',
    '/assets/busisi-mark-v3.svg',
    '/assets/busisi-social-v2.png',
    '/assets/busisi-evidence-banner-v2.webp',
    '/assets/busisi-icons-v1.svg#appropriations',
    'class="home-ledger"',
    'Current FY2027 budget evidence',
    'Questions Busisi can answer from current evidence',
  ]) expectIncludes(html, value, 'home design');
  if (/busisi-mark\.webp|busisi-masthead\.webp/i.test(html)) {
    fail('home design: retired branding or illustration is public');
  }

  const css = await request('/assets/site-visual-v19.css');
  expectStatus(css, 200, 'design CSS');
  expectContentType(css, 'text/css', 'design CSS');
  const cssText = await css.text();
  for (const value of [
    'Source Sans 3', '--paper:#fff', '--ink:#15191d', '--accent:#17415f',
    '--review:#8a4600', '--signal-red:#982b25', '--verified:#1f6547', '.home-ledger',
    '.explorer-shell', '.review-shell', '.integrity-shell', '.contractor-shell',
    '.lifecycle-grid', '.lifecycle-item', '.contract-explorer', '.contract-card',
    '.release-shell', '.release-card', '.questions-hero', '.question-grid',
    '.services-hero', '.services-desk', '.services-card',
  ]) {
    expectIncludes(cssText, value, 'design CSS');
  }
  if (/Merriweather|Georgia|Times New Roman/i.test(cssText)) fail('design CSS: decorative serif font remains');
  if (/\.project-image-card img\{[^}]*(?:filter|mix-blend-mode|opacity):/i.test(cssText)) {
    fail('design CSS: documentary project images are visually altered');
  }
  expectIncludes(cssText, '.editorial-banner img{display:block;width:100%;height:100%;object-fit:cover;object-position:center;filter:none}', 'design CSS');
  expectIncludes(cssText, '.release-editorial-banner img{filter:none}', 'design CSS');

  const mark = await request('/assets/busisi-mark-v3.svg');
  expectStatus(mark, 200, 'brand mark');
  expectContentType(mark, 'image/svg+xml', 'brand mark');
  const markText = await mark.text();
  if (markText.length > 4_096 || /<script/i.test(markText)) fail('brand mark: unsafe or oversized SVG');

  const socialCard = await request('/assets/busisi-social-v2.png');
  expectStatus(socialCard, 200, 'social card');
  expectContentType(socialCard, 'image/png', 'social card');
  const socialCardBytes = Buffer.from(await socialCard.arrayBuffer());
  if (socialCardBytes.length > 250_000) fail('social card: exceeds the 250 KB performance budget');
  expectBytes(socialCardBytes.subarray(1, 4), 'PNG', 'social card');

  const banner = await request('/assets/busisi-evidence-banner-v2.webp');
  expectStatus(banner, 200, 'editorial banner');
  expectContentType(banner, 'image/webp', 'editorial banner');
  const bannerBytes = Buffer.from(await banner.arrayBuffer());
  if (bannerBytes.length > 200_000) fail('editorial banner: exceeds the 200 KB performance budget');
  expectBytes(bannerBytes.subarray(0, 4), 'RIFF', 'editorial banner');
  expectBytes(bannerBytes.subarray(8, 12), 'WEBP', 'editorial banner');

  const budgetBanner = await request('/assets/busisi-budget-evidence-banner-v2.webp');
  expectStatus(budgetBanner, 200, 'budget evidence banner');
  expectContentType(budgetBanner, 'image/webp', 'budget evidence banner');
  const budgetBannerBytes = Buffer.from(await budgetBanner.arrayBuffer());
  if (budgetBannerBytes.length > 250_000) fail('budget evidence banner: exceeds the 250 KB performance budget');
  expectBytes(budgetBannerBytes.subarray(0, 4), 'RIFF', 'budget evidence banner');
  expectBytes(budgetBannerBytes.subarray(8, 12), 'WEBP', 'budget evidence banner');

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
    budget_banner_bytes: budgetBannerBytes.length,
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

  const imageCoverage = (await readJson('/api/v1/coverage-status')).data;
  const coverageReleasedAt = Date.parse(imageCoverage?.released_at ?? '');
  if (!imageCoverage
    || !Number.isFinite(coverageReleasedAt)
    || Date.now() - coverageReleasedAt > coverageReleaseMaxAgeMs) {
    fail('project-image coverage: release is missing or stale');
  }
  if (imageCoverage.universe_contracts !== expectedImageCoverage.universe_contracts
    || imageCoverage.source_sha256 !== expectedImageCoverage.source_sha256
    || imageCoverage.release_id?.length !== 64
    || imageCoverage.verified_images < expectedImageCoverage.minimum_verified_images
    || imageCoverage.quarantined_images < expectedImageCoverage.minimum_quarantined_images
    || imageCoverage.completed_contracts !== (
      imageCoverage.verified_exact_contracts
      + imageCoverage.no_image_contracts
      + imageCoverage.conflict_contracts
    )
    || imageCoverage.universe_contracts !== (
      imageCoverage.completed_contracts
      + imageCoverage.retry_contracts
      + imageCoverage.blocked_contracts
      + imageCoverage.pending_contracts
    )) {
    fail('project-image coverage: release identity or control totals do not reconcile');
  }

  const sourceMonitor = (await readJson('/api/v1/source-monitor-status')).data;
  const sourceCheckedAt = Date.parse(sourceMonitor?.checked_at ?? '');
  if (!sourceMonitor
    || sourceMonitor.status !== 'unchanged'
    || !Number.isFinite(sourceCheckedAt)
    || Date.now() - sourceCheckedAt > sourceMonitorMaxAgeMs
    || !/^[a-f0-9]{64}$/.test(sourceMonitor.observations_sha256 ?? '')
    || !Array.isArray(sourceMonitor.differences)
    || sourceMonitor.differences.length !== 0
    || !sourceMonitor.limitations?.some(({ source }) => (
      source === 'Commission on Audit report catalogues'
    ))) {
    fail('source monitor: current passing evidence is missing, stale, or reports drift');
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

  const releaseSummary = (await readJson('/api/v1/allotment-release-summary')).data;
  for (const [key, expected] of Object.entries(expectedReleases)) {
    if (releaseSummary[key] !== expected) {
      fail(`allotment releases: ${key} expected ${expected}, received ${releaseSummary[key]}`);
    }
  }
  const releaseRows = await readJson('/api/v1/allotment-releases?q=DPWH&level=departments');
  if (releaseRows.meta.total !== 1
    || releaseRows.meta.review_scope !== 'official_dbm_allotment_releases'
    || releaseRows.data[0]?.record_id !== 'release:dpwh'
    || releaseRows.data[0]?.release_centavos !== 52_784_559_400_000
    || releaseRows.data[0]?.adjusted_program_centavos !== 53_011_519_500_000
    || releaseRows.data[0]?.balance_centavos !== 226_960_100_000
    || releaseRows.data[0]?.source_reader_url !== '/releases/#source') {
    fail('allotment releases: DPWH row or evidence boundary does not reconcile');
  }

  const publicServices = (await readJson('/api/v1/public-services-summary')).data;
  const publicServiceControls = {
    total: publicServices.records?.total,
    budget: publicServices.records?.budget,
    delivery: publicServices.records?.delivery,
    school: publicServices.facilities?.school,
    hospital: publicServices.facilities?.hospital,
    health_center: publicServices.facilities?.health_center,
    ...publicServices.work_types,
  };
  for (const [key, expected] of Object.entries(expectedPublicServices)) {
    if (publicServiceControls[key] !== expected) {
      fail(`public services: ${key} expected ${expected}, received ${publicServiceControls[key]}`);
    }
  }
  if (publicServices.classification_version !== 'public-services-v1'
    || publicServices.records.flagged < 0
    || publicServices.records.flagged > publicServices.records.total
    || publicServices.facilities.school + publicServices.facilities.hospital
      + publicServices.facilities.health_center !== publicServices.records.total
    || Object.values(publicServices.work_types).reduce((sum, value) => sum + value, 0)
      !== publicServices.records.total) {
    fail('public services: classification identity or control totals do not reconcile');
  }
  const schoolServices = await readJson('/api/v1/public-services?facility=school&limit=1');
  if (schoolServices.meta.total !== expectedPublicServices.school
    || schoolServices.meta.review_scope !== 'title_classified_public_service_records'
    || schoolServices.data.length !== 1
    || schoolServices.data[0].facility_type !== 'school'
    || schoolServices.data[0].reader_url?.startsWith('/api/')) {
    fail('public services: school filter or reader-safe evidence link does not reconcile');
  }
  const serviceIdentityConflicts = await readJson(
    '/api/v1/public-services?flag=identity_conflict&limit=1',
  );
  if (serviceIdentityConflicts.meta.total < 1
    || !serviceIdentityConflicts.data[0]?.flags.some(({ classification }) => (
      classification === 'identity_conflict'
    ))) {
    fail('public services: identity-conflict filter does not return qualifying evidence');
  }

  const questionCatalogue = await readJson('/api/v1/questions');
  if (questionCatalogue.meta.review_scope !== 'evidence_question_catalogue'
    || questionCatalogue.meta.total !== 21
    || questionCatalogue.meta.states?.answerable !== 10
    || questionCatalogue.meta.states?.partially_answerable !== 5
    || questionCatalogue.meta.states?.not_supported !== 6
    || new Set(questionCatalogue.data.map(({ id }) => id)).size !== 21) {
    fail('question catalogue: identity or state controls do not reconcile');
  }
  const questionsById = Object.fromEntries(questionCatalogue.data.map((item) => [item.id, item]));
  if (questionsById['fy2027-project-stage-changes']?.scope_count !== changeStats.record_count
    || questionsById['dbm-allotment-releases']?.scope_count !== releaseSummary.record_count
    || questionsById['project-image-coverage']?.scope_count !== imageCoverage.universe_contracts
    || questionsById['school-hospital-counts']?.scope_count !== publicServices.records.total
    || questionsById['school-hospital-counts']?.answer_url !== '/public-services/'
    || questionsById['actual-project-payment']?.answer_url !== null
    || questionCatalogue.data.some(({ answer_url: answerUrl }) => answerUrl?.startsWith('/api/'))) {
    fail('question catalogue: live counts or reader-safe answer links do not reconcile');
  }

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
  const acquisitionCoverage = await readJson('/api/v1/acquisition-coverage');
  if (acquisitionCoverage.meta.review_scope !== 'full_contract_universe_acquisition') {
    fail('acquisition coverage: review scope mismatch');
  }
  for (const [key, expected] of Object.entries(expectedAcquisitionCoverage)) {
    const actual = key.startsWith('award_')
      ? acquisitionCoverage.data.source[key]
      : acquisitionCoverage.data.summary[key];
    if (actual !== expected) {
      fail(`acquisition coverage: ${key} expected ${expected}, received ${actual}`);
    }
  }
  if (acquisitionCoverage.data.states.structured_exact !== 38_110
    || acquisitionCoverage.data.states.title_exact !== 6_884
    || acquisitionCoverage.data.states.multiple_exact_rows !== 2_077
    || acquisitionCoverage.data.states.conflict_review !== 161
    || acquisitionCoverage.data.states.no_exact_row !== 9_655
    || acquisitionCoverage.data.queue.pending !== 464_727
    || acquisitionCoverage.data.queue.secondary_exact !== 47_071
    || acquisitionCoverage.data.queue.quarantined !== 161) {
    fail('acquisition coverage: state or queue controls mismatch');
  }

  const contractSummary = (await readJson('/api/v1/contract-intelligence-summary')).data;
  if (contractSummary.total_contracts !== expectedCounts.delivery_records) {
    fail(`contract intelligence: expected ${expectedCounts.delivery_records} contracts`);
  }
  for (const [state, expected] of Object.entries(expectedContractStates)) {
    if (contractSummary.states[state] !== expected) {
      fail(`contract intelligence: ${state} expected ${expected}, received ${contractSummary.states[state]}`);
    }
  }
  if (contractSummary.facets.categories.length !== 76
    || contractSummary.facets.regions.length !== 18
    || contractSummary.facets.provinces.length !== 100
    || contractSummary.facets.statuses.length !== 5) {
    fail('contract intelligence: filter facet controls do not reconcile');
  }
  const exactContracts = await readJson('/api/v1/contracts?q=24CM0078&state=structured_exact&limit=1');
  if (exactContracts.meta.total !== 1
    || exactContracts.meta.review_scope !== 'contract_intelligence_evidence'
    || exactContracts.data[0]?.contract_id !== '24CM0078'
    || exactContracts.data[0]?.match_state !== 'structured_exact'
    || exactContracts.data[0]?.reader_url !== '/contracts/24CM0078/') {
    fail('contract intelligence: exact contract filter does not reconcile');
  }
  const conflictContracts = await readJson('/api/v1/contracts?q=24CJ0309&state=conflict_review&limit=1');
  if (conflictContracts.meta.total !== 1
    || conflictContracts.data[0]?.contract_id !== '24CJ0309'
    || conflictContracts.data[0]?.quarantined_match_rows !== 3) {
    fail('contract intelligence: conflict contract filter does not reconcile');
  }
  const provinceContracts = await readJson(
    '/api/v1/contracts?province=Ilocos%20Norte%201st%20DEO&limit=1',
  );
  if (provinceContracts.meta.total !== 1148
    || provinceContracts.data[0]?.province !== 'Ilocos Norte 1st DEO') {
    fail('contract intelligence: exact province filter does not reconcile');
  }
  const contractCsv = await request('/api/v1/contracts.csv?q=24CJ0309&state=conflict_review');
  expectStatus(contractCsv, 200, 'contract intelligence CSV');
  expectContentType(contractCsv, 'text/csv', 'contract intelligence CSV');
  if (contractCsv.headers.get('x-export-row-limit') !== '10000') {
    fail('contract intelligence CSV: export limit is not explicit');
  }
  const contractCsvText = await contractCsv.text();
  expectIncludes(contractCsvText, '"contract_id","match_state"', 'contract intelligence CSV');
  expectIncludes(contractCsvText, '24CJ0309', 'contract intelligence CSV');
  expectIncludes(contractCsvText, 'conflict_review', 'contract intelligence CSV');

  const exactContract = await readJson('/api/v1/contracts/24CM0078');
  if (exactContract.meta.review_scope !== 'contract_acquisition_evidence'
    || exactContract.data.acquisition.match_state !== 'structured_exact'
    || exactContract.data.award_matches.length !== 1
    || exactContract.data.metadata.award_sha256 !== expectedAcquisitionCoverage.award_sha256) {
    fail('contract detail: exact acquisition evidence does not reconcile');
  }
  await verifyHtmlRecord('/contracts/24CM0078/', 'Contract acquisition evidence');

  const projectImagesPage = await request('/projects/corazon-2024-phase-1/');
  expectStatus(projectImagesPage, 200, 'reviewed project images page');
  const projectImagesText = await projectImagesPage.text();
  expectIncludes(projectImagesText, '2 archived source images', 'reviewed project image count');
  expectIncludes(projectImagesText, 'source-reported, timezone unstated', 'project image time boundary');
  const projectImage = await request('/media/project-images/2e8edcf80e5eadfc64804bcbb2dbfafc27f922906c3657525781fc6cfdaf9144');
  expectStatus(projectImage, 200, 'verified project image');
  expectContentType(projectImage, 'image/jpeg', 'verified project image');
  expectIncludes(projectImage.headers.get('cache-control') ?? '', 'immutable', 'verified project image cache');
  const projectImageBytes = Buffer.from(await projectImage.arrayBuffer());
  expectBytes(projectImageBytes.subarray(0, 2), [0xff, 0xd8], 'verified project image');

  const quarantinedImage = await request('/media/project-images/1d3456daf2211a56c905c6b73d925ace0176792122adbf1f5eeb4aa513f03fd9');
  expectStatus(quarantinedImage, 404, 'quarantined project image');

  const conflictContract = await readJson('/api/v1/contracts/24CJ0309');
  if (conflictContract.data.acquisition.match_state !== 'conflict_review'
    || conflictContract.data.quarantine.length !== 3
    || !conflictContract.data.quarantine.every((item) => item.candidates.length === 2)) {
    fail('contract detail: quarantined conflict evidence does not reconcile');
  }
  const conflictPage = await request('/contracts/24CJ0309/');
  expectStatus(conflictPage, 200, '/contracts/24CJ0309/');
  const conflictText = await conflictPage.text();
  expectIncludes(conflictText, 'Conflicting exact identifiers', 'contract conflict page');
  expectIncludes(conflictText, 'not a finding of wrongdoing', 'contract conflict boundary');
  const formerDelivery = await request('/records/delivery/24CM0078/');
  expectStatus(formerDelivery, 301, 'former delivery route');
  if (formerDelivery.headers.get('location') !== `${publicOrigin}/contracts/24CM0078/`) {
    fail('former delivery route: unexpected redirect destination');
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
  const groupedReview = await readJson(
    '/api/v1/review-rankings?signal=house_only&dimension=region&group=Region%20IV-A&limit=2',
  );
  if (groupedReview.meta.total !== 782
    || groupedReview.data.length !== 2
    || !groupedReview.data.every((record) => record.region === 'Region IV-A')) {
    fail('review rankings: concentration drill-down does not preserve the selected group');
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
    'Something to check, not a finding',
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
  const egbProjects = await readJson(
    '/api/v1/contractors/pcab%3A13722/projects?relationship=joint&limit=100',
  );
  const egbJointProject = egbProjects.data.find(({ contract_id: contractId }) => (
    contractId === '25D00208'
  ));
  if (egbProjects.meta.total !== 96
    || egbProjects.meta.budget_boundary !== 'full_project_budget_not_party_share'
    || egbJointProject?.party_position !== 2
    || egbJointProject?.party_count !== 2
    || egbJointProject?.contractor_parties?.[0]?.contractor_key !== 'pcab:42440'
    || egbJointProject?.contractor_parties?.[1]?.contractor_key !== 'pcab:13722') {
    fail('contractor projects: joint-party identity or budget boundary does not reconcile');
  }
  const egbPage = await request('/contractors/pcab%3A13722/');
  expectStatus(egbPage, 200, 'EGB contractor activity');
  const egbPageText = await egbPage.text();
  expectIncludes(
    egbPageText,
    '<dt>Project associations</dt><dd>245</dd>',
    'EGB contractor activity',
  );
  expectIncludes(egbPageText, '96 joint-project associations', 'EGB contractor activity');
  expectIncludes(egbPageText, '/assets/contractor-v1.js?v=1', 'contractor project client');
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
    allotment_release_records: releaseSummary.record_count,
    integrity_signals: integritySummary.integrity_signals,
    contractors: integritySummary.contractors,
    district_offices: integritySummary.district_offices,
    public_value_indicators: publicValueSummary.indicator_count,
    budget_cycle_documents: cycleDocuments.meta.total,
    project_image_coverage: imageCoverage.completed_contracts,
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
  if (watchlist.headers.get('location') !== `${publicOrigin}/explore/?view=reviewed`) {
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
    'Complete mirror snapshot archived; original official award page not archived',
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

  if (requestOrigin === publicOrigin) {
    const redirect = await fetch(`https://www.${expectedHost}/methodology/`, { redirect: 'manual' });
    expectStatus(redirect, 301, 'www redirect');
    if (redirect.headers.get('location') !== `${publicOrigin}/methodology/`) {
      fail('www redirect: unexpected destination');
    }
  }
  return { missing, quarantined: '/projects/corazon-2026-completion/' };
};

const main = async () => {
  const dns = await verifyDns();
  const pages = await verifyPages();
  const design = await verifyDesign();
  const data = await verifyData();
  const boundaries = await verifyBoundaries();
  console.log(JSON.stringify({
    passed: true,
    origin: publicOrigin,
    request_origin: requestOrigin,
    dns,
    pages,
    design,
    data,
    boundaries,
  }, null, 2));
};

main().catch((error) => {
  console.error(JSON.stringify({
    passed: false,
    origin: publicOrigin,
    request_origin: requestOrigin,
    error: error.message,
  }, null, 2));
  process.exitCode = 1;
});
