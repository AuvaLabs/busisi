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
  assert.match(document, /<meta property="og:image" content="https:\/\/busisi\.org\/assets\/busisi-social-v2\.png">/);
  assert.match(document, /<meta property="og:image:width" content="1200">/);
  assert.match(document, /<meta property="og:image:height" content="630">/);
  assert.match(document, /<meta name="twitter:card" content="summary_large_image">/);
  assert.match(document, /href="\/assets\/site-visual-v20\.css"/);
  assert.match(document, /"@type":"WebSite"/);
  assert.match(document, /Philippine public project evidence/);
  assert.match(document, /independent, nonpartisan evidence desk for Philippine public projects/);
  assert.match(document, /budget, procurement, contractor, delivery, audit, and payment records/);
  assert.doesNotMatch(document, /corazon-2026|25HI0028|api\/v1\/projects/i);
  assert.match(document, /Built and maintained by <a href="https:\/\/auvalabs\.com\//);
  assert.match(document, /href="mailto:dev@auvalabs\.com"/);
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

  assert.match(document, /Follow the evidence behind public projects/);
  assert.match(document, /href="\/contractors\/"/);
  assert.match(document, /href="\/places\/"/);
  assert.match(document, /href="\/signals\/"/);
  assert.match(document, /href="\/sources\/"/);
  assert.match(document, /href="\/watch\/"/);
  assert.match(document, /class="home-ledger"/);
  assert.match(document, /aria-label="Current FY2027 budget evidence"/);
  assert.match(document, /Project rows compared<\/dt><dd>20,431/);
  assert.match(document, /DPWH delivery records/);
  assert.match(document, /56,887/);
  assert.match(document, /Budget authority/);
  assert.match(document, /Payment and outcome/);
  assert.match(document, /src="\/assets\/busisi-evidence-banner-v2\.webp"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#delivery"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#contractors"/);
  assert.match(document, /href="\/assets\/busisi-icons-v1\.svg#investigate"/);
  assert.doesNotMatch(document, /busisi-masthead\.webp|Illustrative view/);
  assert.doesNotMatch(document, /class="utility-strip"/);
  assert.equal((document.match(/data-nav-group=/g) ?? []).length, 7);
});

test('publishes a research library and the multipurpose-building investigation', async () => {
  const library = await fetchPath('/research/');
  const libraryDocument = await library.text();
  assert.equal(library.status, 200);
  assert.match(libraryDocument, /Research and investigations/);
  assert.match(libraryDocument, /href="\/research\/multipurpose-buildings\//);
  assert.match(libraryDocument, /href="\/research\/fy2027-nep-house-changes\//);
  assert.match(libraryDocument, /href="\/research\/fy2027-change-concentration\//);
  assert.match(libraryDocument, /href="\/research\/releases\//);
  assert.match(libraryDocument, /Data cutoff/);

  const article = await fetchPath('/research/multipurpose-buildings/');
  const articleDocument = await article.text();
  assert.equal(article.status, 200);
  assert.match(articleDocument, /5,842/);
  assert.match(articleDocument, /7,024/);
  assert.match(articleDocument, /₱88\.79 billion/);
  assert.match(articleDocument, /₱129\.78 billion/);
  assert.match(articleDocument, /Is every project necessary\?/);
  assert.match(articleDocument, /cannot determine necessity from the current snapshot/i);
  assert.match(articleDocument, /25,499 to 32,503/);
  assert.match(articleDocument, /not a cancellation recommendation/i);
  assert.match(articleDocument, /Need and public function/);
  assert.match(articleDocument, /Location and hazards/);
  assert.match(articleDocument, /Design and accessibility/);
  assert.match(articleDocument, /Cost and delivery/);
  assert.match(articleDocument, /What we investigated/);
  assert.match(articleDocument, /What this does not establish/);
  assert.match(articleDocument, /Where the records came from/);
  assert.match(articleDocument, /Department of Public Works and Highways/);
  assert.match(articleDocument, /Accessed through<\/dt><dd>BetterGov/);
  assert.match(articleDocument, /Open the archived source dataset/);
  assert.doesNotMatch(articleDocument, /href="https:\/\/(?:www\.)?(?:perplexity|exa)\.ai/i);
  assert.match(articleDocument, /Download the research package/);
  assert.match(articleDocument, /Download the finished story/);
  assert.match(articleDocument, /Open the consumption index/);
  assert.match(articleDocument, /43 projects now have a public evidence checklist/);
  assert.match(articleDocument, /href="\/research\/multipurpose-buildings\/evidence\//);
  assert.match(articleDocument, /data\/research\/multipurpose-buildings\/v5\/story\.json/);
  assert.match(articleDocument, /"@type":"AnalysisNewsArticle"/);
});

test('publishes a bounded multipurpose-building public value evidence queue', async () => {
  const response = await fetchPath('/research/multipurpose-buildings/evidence/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Public value evidence layer/);
  assert.match(document, /43.*multipurpose-building records/);
  assert.match(document, /Coordinate-history leads<\/span><strong>31/);
  assert.match(document, /Largest-budget records<\/span><strong>12/);
  assert.match(document, /Fully assessed<\/span><strong>0/);
  assert.match(document, /946.*evidence checks/);
  assert.match(document, /Exact secondary award rows<\/span><strong>38/);
  assert.match(document, /Archived source media<\/span><strong>1/);
  assert.match(document, /Official checks complete<\/span><strong>0/);
  assert.match(document, /not an archived official award notice/i);
  assert.match(document, /Project and facility identity/);
  assert.match(document, /Need and intended public use/);
  assert.match(document, /Location and site suitability/);
  assert.match(document, /Design, capacity, and accessibility/);
  assert.match(document, /Cost, delivery, and actual use/);
  assert.match(document, /25AI0166/);
  assert.match(document, /href="\/contracts\/25AI0166\//);
  assert.match(document, /Selection is not suspicion/);
  assert.match(document, /not a representative sample, risk score, accusation/i);
  assert.match(document, /data\/research\/multipurpose-buildings\/v5\/project-examples\.json/);
  assert.match(document, /"@type":"Dataset"/);
});

test('publishes the FY2027 NEP-to-House investigation with evidence limits', async () => {
  const article = await fetchPath('/research/fy2027-nep-house-changes/');
  const document = await article.text();
  assert.equal(article.status, 200);
  assert.match(document, /20,431/);
  assert.match(document, /6,954/);
  assert.match(document, /426/);
  assert.match(document, /not proof of an insertion/i);
  assert.match(document, /four project-level lists/i);
  assert.match(document, /fy2027-nep-house-changes\/v1\/manifest\.json/);
  assert.match(document, /"@type":"AnalysisNewsArticle"/);
});

test('publishes the FY2027 change-concentration investigation without political inference', async () => {
  const article = await fetchPath('/research/fy2027-change-concentration/');
  const document = await article.text();
  assert.equal(article.status, 200);
  assert.match(document, /20,431/);
  assert.match(document, /9,283/);
  assert.match(document, /6,954/);
  assert.match(document, /426/);
  assert.match(document, /Region IV-A/);
  assert.match(document, /Convergence and Special Support Program/);
  assert.match(document, /not evidence of wrongdoing/i);
  assert.match(document, /fy2027-change-concentration\/v1\/manifest\.json/);
  assert.match(document, /"@type":"AnalysisNewsArticle"/);
});

test('publishes an explicit corrections and immutable release history', async () => {
  const response = await fetchPath('/research/releases/');
  const document = await response.text();
  assert.equal(response.status, 200);
  assert.match(document, /Corrections and release history/);
  assert.match(document, /7 published packages/);
  assert.match(document, /No corrections have been filed/);
  assert.match(document, /Editorial expansion/);
  assert.match(document, /underlying calculations/);
  assert.match(document, /targeted 946-task acquisition ledger/);
  assert.match(document, /multipurpose-buildings\/v1\/manifest\.json/);
});

test('research routes appear in discovery surfaces', async () => {
  const robotsDocument = await (await fetchPath('/robots.txt')).text();
  const sitemapDocument = await (await fetchPath('/sitemap.xml')).text();
  const llmsDocument = await (await fetchPath('/llms.txt')).text();

  assert.match(robotsDocument, /Allow: \/api\/v1\/research/);
  assert.match(sitemapDocument, /\/research\/multipurpose-buildings\//);
  assert.match(sitemapDocument, /\/research\/fy2027-nep-house-changes\//);
  assert.match(sitemapDocument, /\/research\/fy2027-change-concentration\//);
  assert.match(sitemapDocument, /\/research\/releases\//);
  assert.match(llmsDocument, /Research library/);
  assert.match(
    llmsDocument,
    /\/data\/research\/multipurpose-buildings\/v5\/editorial-package\.json/,
  );
  assert.match(sitemapDocument, /\/research\/multipurpose-buildings\/evidence\//);
  assert.match(llmsDocument, /Multipurpose-building public-value evidence queue/);
  assert.match(llmsDocument, /fy2027-nep-house-changes\/v1\/editorial-package\.json/);
  assert.match(llmsDocument, /fy2027-change-concentration\/v1\/editorial-package\.json/);
  assert.match(llmsDocument, /data\/research\/release-history\.json/);
});

test('publishes a machine-readable research release without a database binding', async () => {
  const catalogue = await fetchPath('/api/v1/research');
  const cataloguePayload = await catalogue.json();
  assert.equal(catalogue.status, 200);
  const multipurpose = cataloguePayload.data.find(({ slug }) => slug === 'multipurpose-buildings');
  assert.equal(multipurpose.story_id, 'multipurpose-buildings-2026');
  assert.equal(multipurpose.version, 5);
  assert.equal(
    multipurpose.editorial_package_url,
    'https://busisi.org/data/research/multipurpose-buildings/v5/editorial-package.json',
  );

  const release = await fetchPath('/api/v1/research/multipurpose-buildings');
  const releasePayload = await release.json();
  assert.equal(release.status, 200);
  assert.equal(releasePayload.data.manifest.version, 5);
  assert.equal(releasePayload.data.chart_data.public_value_evidence.candidate_count, 43);
  assert.equal(releasePayload.data.chart_data.public_value_acquisition.task_count, 946);
  assert.equal(releasePayload.data.chart_data.public_value_acquisition.secondary_exact, 38);
  assert.equal(releasePayload.data.project_examples.public_value_candidates.length, 43);
  assert.equal(releasePayload.data.story.editorial_status, 'ready');
  assert.equal(releasePayload.data.editorial_package.status, 'ready_for_consumption');
  assert.equal(releasePayload.data.claims.find(({ id }) => id === 'mpb-ongoing').value, 5842);

  const stageRelease = await fetchPath('/api/v1/research/fy2027-nep-house-changes');
  const stagePayload = await stageRelease.json();
  assert.equal(stageRelease.status, 200);
  assert.equal(stagePayload.data.manifest.package_sha256, '7cd2b9fc154cdae4228232fae5fd2446bb2b88c5bd82f56823d9e1afd77cca1a');
  assert.equal(stagePayload.data.claims.find(({ id }) => id === 'stage-total-records').value, 20431);

  const concentration = await fetchPath('/api/v1/research/fy2027-change-concentration');
  const concentrationPayload = await concentration.json();
  assert.equal(concentration.status, 200);
  assert.equal(concentrationPayload.data.manifest.package_sha256, 'b2a09440ee641fd5f6693401e7f18ed0392b83451e0afd94361a8dc5d6f979ed');
  assert.equal(concentrationPayload.data.claims.find(({ id }) => id === 'concentration-changed-rows').value, 9283);

  const history = await fetchPath('/api/v1/research/history');
  const historyPayload = await history.json();
  assert.equal(history.status, 200);
  assert.equal(historyPayload.data.release_count, 7);
  assert.equal(historyPayload.data.story_count, 3);
  assert.equal(historyPayload.data.correction_count, 0);
});

test('publishes the ecosystem hubs while preserving established evidence pages', async () => {
  const cases = [
    ['/contractors/', /data-contractor-directory/],
    ['/places/', /data-place-directory/],
    ['/sources/', /Original publisher/],
    ['/watch/', /What Busisi is watching/],
  ];

  for (const [path, expected] of cases) {
    const response = await fetchPath(path);
    const document = await response.text();
    assert.equal(response.status, 200, path);
    assert.match(document, expected, path);
  }

  const contractors = await (await fetchPath('/contractors/')).text();
  const places = await (await fetchPath('/places/')).text();
  const sources = await (await fetchPath('/sources/')).text();
  assert.match(contractors, /src="\/assets\/contractors-v1\.js\?v=1"/);
  assert.match(places, /src="\/assets\/places-v1\.js\?v=1"/);
  assert.match(sources, /href="\/budget-trail\/"/);
  assert.match(sources, /href="\/procurement\/"/);
  assert.match(sources, /href="\/audit\/"/);
  assert.match(sources, /Access route/);
  assert.match(sources, /Busisi processing/);
});

test('home scopes its public questions to evidence Busisi currently holds', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /Questions Busisi can answer from current evidence/);
  assert.match(document, /See every supported question and limitation/);
  assert.match(document, /href="\/questions\/"/);
  assert.match(document, /appropriation heads and Congress institutions/);
  assert.match(document, /official DBM allotment releases/);
  assert.match(document, /recorded contractor identities/);
  assert.doesNotMatch(document, /released to each agency/);
  assert.doesNotMatch(document, /Which contracts have exact bid, plan, or monitoring evidence/);
  assert.doesNotMatch(document, /Did COA publish a report or observation that can be linked to this project/);
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
  assert.match(document, /src="\/assets\/explorer-v1\.js\?v=2"/);
  assert.match(document, /Unreviewed candidates are not public findings/);
  assert.doesNotMatch(document, /ghost project/i);
});

test('publishes the deterministic review desk and names unavailable analyses', async () => {
  const response = await fetchPath('/signals/');
  const document = await response.text();
  const client = readFileSync(new URL('../public/assets/review-v1.js', import.meta.url), 'utf8');

  assert.equal(response.status, 200);
  assert.match(document, /Find budget changes that need a closer look/);
  assert.match(document, /A flag is a question to check, not an accusation/);
  assert.match(document, /What we noticed/);
  assert.match(document, /What this does not prove/);
  assert.match(document, /data-review-desk/);
  assert.match(document, /Similar to an earlier-year project/);
  assert.match(document, /Similar to another FY2027 project/);
  assert.match(document, /Download evidence CSV/);
  assert.match(document, /A flag is a question to check, not an accusation/);
  assert.match(document, /src="\/assets\/review-v1\.js\?v=3"/);
  assert.match(document, /Physical existence verification/);
  assert.match(client, /Why check/);
  assert.match(client, /What this does not prove/);
  assert.match(client, /What to check next/);
  assert.match(client, /Held back for checking/);
  assert.doesNotMatch(client, /Calculating deterministic review candidates/);
});

test('publishes the project-integrity desk and contractor leaderboard', async () => {
  const response = await fetchPath('/integrity/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Find project records that need a closer look/);
  assert.match(document, /data-integrity-desk/);
  assert.match(document, /Contractors with the most projects/);
  assert.match(document, /Find project records that need a closer look/);
  assert.match(document, /A flag is a question to check, not an accusation/);
  assert.match(document, /What we noticed/);
  assert.match(document, /What this does not prove/);
  assert.match(document, /Rank by project count/);
  assert.match(document, /Rank by associated project budget/);
  assert.match(document, /data-concentration-desk/);
  assert.match(document, /contractor-party associations/);
  assert.match(document, /Current PCAB-table status/);
  assert.match(document, /Congressional district context/);
  assert.match(document, /does not establish political authorship/);
  assert.match(document, /A flag is a question to check, not an accusation/);
  assert.match(document, /src="\/assets\/integrity-v1\.js\?v=3"/);
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
  assert.match(document, /src="\/assets\/changes-v1\.js\?v=2"/);
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

test('publishes the official FY2026 allotment-release ledger with spending boundaries', async () => {
  const response = await fetchPath('/releases/');
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /See what DBM had released by September/);
  assert.match(document, /30 September 2026/);
  assert.match(document, /data-release-ledger/);
  assert.match(document, /src="\/assets\/releases-v1\.js"/);
  assert.match(document, /Allotment release is not payment/);
  assert.match(document, /not project-level/i);
  assert.match(document, /href="https:\/\/www\.dbm\.gov\.ph\/index\.php\?/);
  assert.match(document, /05a902418e0a78339b82d71def04447eab44897b752d001343121bcbe6226aae/);
  assert.doesNotMatch(document, /release proves? (?:a )?payment/i);
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
  assert.match(document, /src="\/assets\/public-value-v1\.js\?v=2"/);
  assert.doesNotMatch(document, /overall score|AI score/i);
});

test('home uses the restrained-color Busisi identity and direct evidence desks', async () => {
  const response = await fetchPath('/');
  const document = await response.text();

  assert.match(document, /src="\/assets\/busisi-mark-v3\.svg"/);
  assert.doesNotMatch(document, /src="\/assets\/busisi-mark\.webp"/);
  assert.doesNotMatch(document, /busisi-masthead\.webp/);
  assert.match(document, /Philippine public project evidence/);
  assert.match(document, /Start with the public record/);
  assert.match(document, /Project-centered evidence/);
  assert.match(document, /Association, not attribution/);
  assert.match(document, /Source labels, not map claims/);
  assert.match(document, /Review lead, not accusation/);
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
  assert.match(document, /href="#plain-language"/);
  assert.match(document, /id="plain-language"/);
  assert.match(document, /The simple explanation comes first/);
  assert.match(document, /1\. What we noticed/);
  assert.match(document, /3\. What it does not prove/);
  assert.match(document, /4\. What to check next/);
  assert.match(document, /href="#source-policy"/);
  assert.match(document, /href="#corrections"/);
  assert.match(document, /Congressional district context/);
  assert.match(document, /Machine-readable provenance stays in the JSON API/);
  assert.match(document, /not a coordinate or boundary-polygon determination/);
  assert.match(document, /Built and maintained by/);
  assert.match(document, /id="editorial-independence"/);
  assert.match(document, /no affiliation with any politician, political party, candidate/);
  assert.match(document, /same published evidence rules/);
  assert.match(document, /BetterGov does not operate, sponsor, or endorse Busisi/);
  assert.match(document, /Auva Labs is responsible for Busisi's software, data pipeline, methodology, presentation, and publication decisions/);
});

test('publishes machine-readable discovery files', async () => {
  const robots = await fetchPath('/robots.txt');
  const sitemap = await fetchPath('/sitemap.xml');
  const llms = await fetchPath('/llms.txt');
  const sitemapText = await sitemap.text();

  const robotsText = await robots.text();
  assert.match(robotsText, /Sitemap: https:\/\/busisi\.org\/sitemap\.xml/);
  assert.match(robotsText, /Allow: \/api\/v1\/questions/);
  assert.match(robotsText, /Allow: \/api\/v1\/alerts/);
  assert.match(robotsText, /Allow: \/feeds\/updates\.xml/);
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
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/questions\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/public-services\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/contractors\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/places\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/sources\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/watch\/<\/loc>/);
  assert.match(sitemapText, /<loc>https:\/\/busisi\.org\/projects\/corazon-2024-phase-1\/<\/loc>/);
  assert.doesNotMatch(sitemapText, /corazon-2026-completion/);
  const llmsText = await llms.text();
  assert.match(llmsText, /Evidence and publication rules/);
  assert.match(llmsText, /Project integrity desk/);
  assert.match(llmsText, /Appropriation heads/);
  assert.match(llmsText, /Public value desk/);
  assert.match(llmsText, /Evidence question catalogue/);
  assert.match(llmsText, /Public services inventory/);
  assert.match(llmsText, /Contractor directory/);
  assert.match(llmsText, /Place directory/);
  assert.match(llmsText, /Source guide/);
  assert.match(llmsText, /Source watch/);
  assert.match(llmsText, /Evidence update feed/);
  assert.match(llmsText, /\/api\/v1\/alerts/);
  assert.match(llmsText, /\/api\/v1\/public-services/);
  assert.match(llmsText, /\/api\/v1\/questions/);
  assert.match(llmsText, /nonpartisan, and politically unaffiliated/);
  assert.match(llmsText, /Built and maintained by Auva Labs/);
  assert.match(llms.headers.get('content-type'), /^text\/plain/);
});

test('serves the public IndexNow ownership key', async () => {
  const key = '4754cd4a99b473376bef19b5bbf858f0';
  const response = await fetchPath(`/${key}.txt`);

  assert.equal(response.status, 200);
  assert.equal((await response.text()).trim(), key);
});

test('submits the allotment-release desk for search discovery', () => {
  const source = readFileSync(
    new URL('../scripts/submit-indexnow.mjs', import.meta.url), 'utf8',
  );

  assert.match(source, /'\/releases\/'/);
  assert.match(source, /'\/questions\/'/);
  assert.match(source, /'\/public-services\/'/);
  assert.match(source, /'\/contractors\/'/);
  assert.match(source, /'\/places\/'/);
  assert.match(source, /'\/sources\/'/);
  assert.match(source, /'\/watch\/'/);
});

test('public-services client renders API data without injecting HTML', () => {
  const source = readFileSync(
    new URL('../public/assets/public-services-v1.js', import.meta.url), 'utf8',
  );

  assert.match(source, /\/api\/v1\/public-services/);
  assert.match(source, /textContent/);
  assert.match(source, /encodeURIComponent/);
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML|risk score/i);
});

test('ecosystem clients render API data without injecting HTML', () => {
  for (const name of ['contractors-v1.js', 'places-v1.js']) {
    const source = readFileSync(new URL(`../public/assets/${name}`, import.meta.url), 'utf8');
    assert.match(source, /textContent/);
    assert.match(source, /encodeURIComponent|reader_url/);
    assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);
  }
});

test('redirects www and returns a useful 404', async () => {
  const redirect = await fetchPath('/methodology/', 'www.busisi.org');
  const missing = await fetchPath('/not-a-page');

  assert.equal(redirect.status, 301);
  assert.equal(redirect.headers.get('location'), 'https://busisi.org/methodology/');
  assert.equal(missing.status, 404);
  assert.match(await missing.text(), /Page not found/);
});

test('keeps the workers.dev monitor origin private', async () => {
  const monitorUrl = 'https://busisi-publication.example.workers.dev/';
  const environment = { MONITOR_TOKEN: 'monitor-test-token' };
  const missing = await worker.fetch(new Request(monitorUrl), environment);
  const incorrect = await worker.fetch(new Request(monitorUrl, {
    headers: { 'X-Busisi-Monitor-Token': 'incorrect' },
  }), environment);
  const allowed = await worker.fetch(new Request(monitorUrl, {
    headers: { 'X-Busisi-Monitor-Token': 'monitor-test-token' },
  }), environment);

  assert.equal(missing.status, 404);
  assert.equal(incorrect.status, 404);
  assert.equal(allowed.status, 200);
  assert.match(await allowed.text(), /Philippine public project evidence/);
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

test('serves the accessible civic color system and safe method boundaries', async () => {
  const css = await fetchPath('/assets/site-visual-v20.css');
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
  assert.match(cssText, /--ink:#15191d/);
  assert.match(cssText, /--accent:#17415f/);
  assert.match(cssText, /--review:#8a4600/);
  assert.match(cssText, /--signal-red:#982b25/);
  assert.match(cssText, /--verified:#1f6547/);
  assert.match(cssText, /--text-xs:\.8125rem/);
  assert.match(cssText, /body\{[^}]*font-size:var\(--text-md\)[^}]*line-height:1\.6/);
  assert.match(cssText, /body:before\{display:none/);
  assert.match(cssText, /@media\(prefers-contrast:more\)/);
  assert.match(cssText, /\.integrity-shell/);
  assert.match(cssText, /\.contractor-shell/);
  assert.match(cssText, /\.home-ledger/);
  assert.match(cssText, /\.editorial-banner/);
  assert.match(cssText, /\.project-image-gallery/);
  assert.doesNotMatch(cssText, /\.project-image-card img\{[^}]*grayscale/);
  assert.doesNotMatch(cssText, /\.project-image-card img\{[^}]*(filter|mix-blend-mode|opacity):/);
  assert.match(cssText, /\.primary-nav a:hover,[^{]+\{[^}]*color:var\(--accent\)/);
  assert.match(cssText, /\.editorial-banner img\{[^}]*filter:none/);
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

test('keeps semantic text colors at WCAG AA contrast on white', async () => {
  const cssText = await (await fetchPath('/assets/site-visual-v20.css')).text();
  const token = (name) => cssText.match(new RegExp(`--${name}:(#[0-9a-f]{6})`))?.[1];
  const luminance = (hex) => {
    const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
    const linear = channels.map((value) => (
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    ));
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2]);
  };
  const contrastOnWhite = (hex) => 1.05 / (luminance(hex) + 0.05);

  for (const name of ['ink', 'accent', 'review', 'signal-red', 'verified', 'muted']) {
    assert.ok(contrastOnWhite(token(name)) >= 4.5, `${name} must meet WCAG AA on white`);
  }
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
    new Request('https://busisi.org/assets/busisi-social-v2.png'),
    env,
  );

  assert.equal(asset.status, 200);
  assert.equal(asset.headers.get('content-type'), 'image/png');
  assert.equal(await asset.text(), '/assets/busisi-social-v2.png');
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
    new Request('https://busisi.org/assets/busisi-budget-evidence-banner-v2.webp'),
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

test('places the decorative budget evidence banner on the release ledger', async () => {
  const response = await fetchPath('/releases/');
  const document = await response.text();

  assert.match(document, /busisi-budget-evidence-banner-v2\.webp/);
  assert.match(document, /class="release-editorial-banner" aria-hidden="true"/);
  assert.match(document, /width="1600" height="534" alt=""/);
  assert.match(document, /site-visual-v20\.css/);
});

test('reader actions use human-readable evidence instead of raw JSON endpoints', () => {
  const assets = Object.fromEntries(
    ['explorer', 'agencies', 'changes', 'review', 'integrity', 'contracts', 'public-value'].map((name) => [
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
  assert.match(assets.review, /review-record-title/);
  assert.match(assets.review, /Inspect project evidence/);
  assert.match(assets.review, /Clear group filter/);
  assert.match(assets.review, /params\.set\('group', label\)/);
  assert.match(assets.explorer, /record-title-link/);
  assert.match(assets.changes, /record-title-link/);
  assert.match(assets.integrity, /record-title-link/);
  assert.match(assets.integrity, /top_contractor_key/);
  assert.match(assets.integrity, /contractGroupUrl/);
  assert.match(assets.contracts, /province/);
  assert.match(assets['public-value'], /\/agencies\/\?q=/);
  assert.doesNotMatch(assets.integrity, /Open archived source record.*record\.source_url/);
});
