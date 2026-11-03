import { SITE } from './prelaunch-config.js';
import { dataCss } from './prelaunch-data-styles.js';
import { changeCss } from './prelaunch-change-styles.js';
import { agencyCss } from './prelaunch-agency-styles.js';
import { integrityCss } from './prelaunch-integrity-styles.js';
import { reviewCss } from './prelaunch-review-styles.js';
import { siteCss as baseSiteCss } from './prelaunch-styles.js';
import { typeCss } from './prelaunch-type-styles.js';
import {
  evidenceOrbit,
  gateVisual,
  illustrativeSequence,
  methodDiagram,
  signalAnatomy,
} from './prelaunch-visuals.js';

const navigation = (canonicalPath) => {
  const methodology = canonicalPath === '/methodology/';
  const links = `<a href="/explore/"${canonicalPath === '/explore/' ? ' aria-current="page"' : ''}>Explore</a><a href="/agencies/"${canonicalPath === '/agencies/' ? ' aria-current="page"' : ''}>Agencies</a><a href="/changes/"${canonicalPath === '/changes/' ? ' aria-current="page"' : ''}>Projects</a><a href="/signals/"${canonicalPath === '/signals/' ? ' aria-current="page"' : ''}>Review</a><a href="/integrity/"${canonicalPath === '/integrity/' ? ' aria-current="page"' : ''}>Integrity</a>`;
  return `<div class="header-inner">
    <a class="wordmark" href="/" aria-label="Busisi home"><img class="brand-mark" src="/assets/busisi-mark-v2.svg" width="44" height="44" alt=""><span>Busisi</span></a>
    <nav class="primary-nav" aria-label="Primary navigation">${links}<a class="method-link" href="/methodology/"${methodology ? ' aria-current="page"' : ''}>Methodology</a></nav>
  </div>`;
};

const utilityStrip = `<div class="utility-strip"><div class="utility-inner">
  <span>Independent Philippine budget evidence project</span>
  <a href="/changes/"><i aria-hidden="true"></i>FY2027 NEP to House change ledger</a>
</div></div>`;

const footer = `<footer class="site-footer"><div class="footer-inner">
  <div class="footer-brand"><strong>Busisi</strong><p>Independent civic data initiative for traceable Philippine public budget records.</p></div>
  <nav class="footer-nav" aria-label="Footer navigation"><a href="/explore/">Explore</a><a href="/agencies/">Agencies</a><a href="/changes/">Projects</a><a href="/signals/">Review</a><a href="/integrity/">Integrity</a><a href="/methodology/">Methodology</a></nav>
  <p class="footer-note">Official source records are public. Inferred links remain labelled by review status.</p>
</div></footer>`;

const escapeJson = (value) => JSON.stringify(value).replaceAll('<', '\\u003c');
const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const peso = (centavos) => new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
}).format(centavos / 100);

export const document = ({ title, description, canonicalPath, body, schema, noindex = false }) => {
  const canonical = `${SITE.origin}${canonicalPath}`;
  const robots = noindex ? 'noindex, nofollow' : 'index, follow, max-image-preview:large';
  return `<!doctype html>
<html lang="en-PH"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title><meta name="description" content="${description}"><meta name="robots" content="${robots}">
  <link rel="canonical" href="${canonical}"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="/assets/busisi-masthead.webp" as="image" type="image/webp" fetchpriority="high"><link rel="stylesheet" href="/assets/site-visual-v7.css">
  <meta property="og:type" content="website"><meta property="og:site_name" content="Busisi"><meta property="og:title" content="${title}"><meta property="og:description" content="${description}"><meta property="og:url" content="${canonical}">
  <meta property="og:image" content="${SITE.origin}/assets/busisi-masthead.webp"><meta property="og:image:width" content="1600"><meta property="og:image:height" content="666">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${title}"><meta name="twitter:description" content="${description}"><meta name="twitter:image" content="${SITE.origin}/assets/busisi-masthead.webp">
  <script type="application/ld+json">${escapeJson(schema)}</script>${canonicalPath === '/explore/' ? '<script type="module" src="/assets/explorer-v1.js"></script>' : ''}${canonicalPath === '/agencies/' ? '<script type="module" src="/assets/agencies-v1.js"></script>' : ''}${canonicalPath === '/changes/' ? '<script type="module" src="/assets/changes-v1.js"></script>' : ''}${canonicalPath === '/signals/' ? '<script type="module" src="/assets/review-v1.js"></script>' : ''}${canonicalPath === '/integrity/' ? '<script type="module" src="/assets/integrity-v1.js"></script>' : ''}
</head><body>
  <a class="skip-link" href="#main-content">Skip to content</a>${utilityStrip}<header class="site-header">${navigation(canonicalPath)}</header>
  <main id="main-content">${body}</main>${footer}
</body></html>`;
};

const principles = `
  <div class="principles">
    <article class="principle"><span class="principle-icon" aria-hidden="true">⌁</span><h3>Source before claim</h3><p>Every record retains its official origin, retrieval context, and archived fingerprint.</p></article>
    <article class="principle"><span class="principle-icon" aria-hidden="true">≡</span><h3>Uncertainty stays visible</h3><p>Candidate links remain candidates. Confidence and conflicting evidence are never hidden.</p></article>
    <article class="principle"><span class="principle-icon" aria-hidden="true">✓</span><h3>Review before release</h3><p>Weak matches and failed controls stay quarantined instead of becoming public assertions.</p></article>
  </div>`;

export const homeBody = `
  <section class="hero">
    <img class="hero-art" src="/assets/busisi-masthead.webp" width="1600" height="666" alt="Illustration of public records linked to roads, schools, health services, and water infrastructure across the Philippines" fetchpriority="high" decoding="async">
    <p class="hero-art-note">Illustrative view · not a project record</p>
    <div class="hero-copy">
      <div class="eyebrow"><span></span> Official source records now available</div>
      <h1>Follow public money through the record.</h1>
      <p class="lede">Search Philippine appropriations and DPWH delivery records, inspect candidate links, and see exactly which conclusions remain unverified.</p>
      <div class="actions"><a class="primary" href="/changes/">Inspect FY2027 changes</a><a class="secondary" href="/explore/">Explore source records</a></div>
    </div>
  </section>

  <section class="register-preview" aria-labelledby="register-preview-heading">
    <div class="preview-heading"><p class="kicker">Explore the source record</p><h2 id="register-preview-heading">Four ways to inspect public money.</h2><p>Official records are published as source records. Cross-source relationships stay labelled as candidates until they pass human review.</p></div>
    <div class="preview-panels">
      <a href="/explore/?view=budgets"><span aria-hidden="true">01</span><div><h3>GAA appropriations</h3><p>Search 68,608 positive budget records across fiscal years 2024 to 2026.</p></div><small>Official source records</small></a>
      <a href="/explore/?view=delivery"><span aria-hidden="true">02</span><div><h3>DPWH delivery records</h3><p>Inspect 56,887 contracts with recorded budgets, locations, and funding sources.</p></div><small>Official source records</small></a>
      <a href="/explore/?view=candidates"><span aria-hidden="true">03</span><div><h3>Candidate links</h3><p>Review 385 explainable machine matches without treating them as confirmed identity.</p></div><small>Human review required</small></a>
      <a href="/changes/"><span aria-hidden="true">04</span><div><h3>FY2027 stage changes</h3><p>Compare 20,431 project rows between the NEP and the House bill with document-page evidence.</p></div><small>Provisional comparisons</small></a>
    </div>
  </section>

  <nav class="page-map" aria-label="Project sections"><a href="/#mission"><span>01</span>Mission<b>→</b></a><a href="/#system"><span>02</span>Evidence system<b>→</b></a><a href="/#gate"><span>03</span>Release gate<b>→</b></a></nav>

  <section class="narrative-section" id="mission" aria-labelledby="mission-heading">
    <div class="section-heading"><p class="section-number">01 / Mission</p><div><h2 id="mission-heading">A record trail, not a verdict.</h2><p class="section-intro">Public budget information is spread across documents, years, agencies, and inconsistent names. Busisi makes the path between those records inspectable without turning a pattern into an accusation.</p></div></div>
    <div class="mission-visuals">${evidenceOrbit}${principles}</div>
  </section>

  <section class="narrative-section" id="system" aria-labelledby="system-heading">
    <div class="section-heading"><p class="section-number">02 / System</p><div><h2 id="system-heading">One project can leave many records.</h2><p class="section-intro">The system follows evidence across stages while keeping the original language and source beside every normalized field.</p></div></div>
    <div class="system-panel">${illustrativeSequence}</div>
  </section>

  <section class="signal-band" aria-labelledby="signal-heading">
    <div class="signal-layout"><div><p class="section-number">Review signals</p><h2 id="signal-heading">Not a ranking. Not an accusation.</h2><p>A signal is a documented reason to inspect a record more closely. Its calculation, inputs, confidence, and limitations must travel with it.</p></div>${signalAnatomy}</div>
  </section>

  <section class="narrative-section" id="gate" aria-labelledby="gate-heading">
    <div class="gate-layout"><div class="gate-copy"><p class="kicker">03 / Release gate</p><h2 id="gate-heading">Evidence before inference.</h2><p>Official source records can be inspected now. The gate controls when Busisi may present an inferred relationship as a reviewed project link.</p><a class="text-link" href="/methodology/#release-standard">Read the release standard&nbsp; →</a></div>${gateVisual}</div>
  </section>`;

export const exploreBody = `
  <section class="data-intro"><div><p class="kicker">Public data explorer</p><h1>Explore official budget records.</h1><p class="lede">Search the archived GAA and DPWH snapshots separately, then inspect candidate relationships without confusing a similarity match with a reviewed finding.</p></div><aside class="snapshot-card"><span>Snapshot boundary</span><strong>FY 2024–2026</strong><p>GAA modified 29 Jan 2026<br>DPWH modified 22 Jan 2026</p><a href="/methodology/#source-policy">Read the source policy</a></aside></section>
  <section class="dataset-stats" aria-label="Dataset totals"><article><span>68,608</span><p>positive GAA records</p></article><article><span>56,887</span><p>DPWH delivery records</p></article><article><span>385</span><p>candidate links</p></article><article><span>6</span><p>human-reviewed dossiers</p></article></section>
  <section class="explorer-shell" data-explorer>
    <div class="explorer-tabs" role="tablist" aria-label="Choose a public record collection"><button type="button" role="tab" data-explorer-view="budgets">GAA appropriations</button><button type="button" role="tab" data-explorer-view="delivery">DPWH delivery records</button><button type="button" role="tab" data-explorer-view="candidates">Candidate links</button><button type="button" role="tab" data-explorer-view="reviewed">Reviewed dossiers</button></div>
    <div class="explorer-notice" data-explorer-notice><strong>Source records are not findings.</strong><span data-explorer-description>Amounts reproduce the archived official snapshot and should be read with its date and limitations.</span></div>
    <form class="explorer-controls" data-explorer-form role="search"><label>Search records<input type="search" name="q" maxlength="200" placeholder="Project, place, contract, or description"></label><label>Fiscal year<select name="year"><option value="">All years</option><option>2026</option><option>2025</option><option>2024</option><option>2023</option><option>2022</option></select></label><label>Sort<select name="sort" data-explorer-sort></select></label><button type="submit">Apply</button><button type="button" class="secondary-control" data-explorer-reset>Reset</button></form>
    <div class="result-summary" aria-live="polite"><p><strong data-explorer-count>0</strong> of <span data-explorer-total>0</span> records shown</p><p data-explorer-status>Loading the public snapshot…</p></div>
    <div class="record-list" data-explorer-results></div>
    <div class="explorer-actions"><button type="button" data-explorer-more hidden>Load more</button></div>
    <noscript><p class="explorer-error">JavaScript is required for interactive filtering. The source APIs remain available as JSON.</p></noscript>
  </section>
  <section class="candidate-warning"><h2>Unreviewed candidates are not public findings.</h2><p>Candidate links are generated from year, description, amount, funding, and location signals. They may connect separate phases or unrelated records. Only records marked reviewed have passed the current human evidence check.</p></section>`;

export const signalsBody = `
  <section class="data-intro review-intro"><div><p class="kicker">Deterministic review desk</p><h1>Start with the records that moved.</h1><p class="lede">Rank FY2027 project changes, inspect geographic concentrations, trace repeated project-family candidates, and export the evidence for independent review.</p></div><aside class="snapshot-card"><span>Evidence boundary</span><strong>Questions, not verdicts</strong><p>Every result comes from a disclosed rule. No model assigns risk or intent.</p><a href="/methodology/">Read the method</a></aside></section>
  <section class="review-warning"><strong>Not a corruption score.</strong><p>Rankings identify records that meet a deterministic review rule. Similar wording, a large increase, or a House-only row does not establish duplication, authorship, illegality, or wrongdoing.</p></section>
  <section class="review-summary" data-review-summary aria-label="FY2027 change summary"><p>Loading reconciled totals…</p></section>
  <section class="review-shell" data-review-desk>
    <form class="review-controls" data-review-form><label>Review rule<select name="signal"><option value="house_only">Largest House-only rows</option><option value="increased">Largest increases</option><option value="decreased">Largest decreases</option><option value="nep_only">Largest NEP-only rows</option><option value="repeat_family">Prior-year family candidates</option><option value="similar_family">Similar FY2027 family candidates</option></select></label><label>Program<select name="dataset"><option value="all">All four</option><option value="dpwh">DPWH</option><option value="fmr">Farm-to-market roads</option><option value="hfep">Health facilities</option><option value="nia">Irrigation</option></select></label><label>Group by<select name="dimension"><option value="region">Region</option><option value="office">Office</option><option value="program">Program</option><option value="dataset">Dataset</option></select></label><button type="submit">Apply rule</button></form>
    <div class="review-toolbar" aria-live="polite"><p><strong data-review-total>0</strong> candidates meet this rule. <span data-review-status>Loading review candidates…</span></p><a data-review-export href="/api/v1/review.csv">Download evidence CSV</a></div>
    <div class="review-grid"><section class="review-ranking-panel"><div class="review-panel-heading"><p class="kicker">Priority queue</p><h2>Records to inspect first</h2></div><div data-review-rankings></div></section><section><div class="review-panel-heading"><p class="kicker">Concentration</p><h2>Where movement is grouped</h2></div><div class="review-concentrations" data-review-concentrations></div></section></div>
    <noscript><p class="explorer-error">JavaScript is required for interactive rankings. The read-only JSON and CSV APIs remain available.</p></noscript>
  </section>
  <section class="review-method"><div><p class="kicker">Rule boundaries</p><h2>What these queues can and cannot establish.</h2></div><div><p>The repeated-family rule uses the same conservative normalized project-family identity as the historical appropriation explorer. Similar-family candidates share that label inside the same FY2027 dataset.</p><ul><li>Large movement is ordered by exact integer-centavo arithmetic.</li><li>Concentration is an aggregate observation, not evidence against an office or region.</li><li>Family matches may join separate phases and always require documentary review.</li><li>Physical existence, procurement conduct and political authorship require additional evidence.</li></ul></div></section>
  <section class="coverage-matrix" aria-labelledby="coverage-heading"><div><p class="kicker">Evidence gaps</p><h2 id="coverage-heading">Unavailable means unavailable.</h2><p>Busisi does not generate a label when the evidence required for that label has not been acquired.</p></div><div class="coverage-list"><article><span>Partial</span><h3>Full insertion analysis</h3><p>The FY2027 ledger covers four project-level programs from NEP to House. Senate, bicameral and enacted GAA stages remain unavailable.</p></article><article><span>Not available</span><h3>Physical existence verification</h3><p>Requires implementation evidence such as geotagged progress, inspections, audit findings, or field verification. Budget data alone cannot establish physical existence.</p></article><article><span>Partial</span><h3>Procurement consistency</h3><p>ABC, award, status, and physical-progress checks require current DPWH detail and PhilGEPS records beyond the archived bulk snapshot.</p></article></div></section>`;

export const integrityBody = `
  <section class="data-intro integrity-intro"><div><p class="kicker">Project integrity desk</p><h1>Inspect contradictions in delivery records.</h1><p class="lede">Filter deterministic review signals from the archived DPWH project snapshot, inspect the source evidence, and compare contractor activity without turning a data inconsistency into an accusation.</p></div><aside class="snapshot-card"><span>Snapshot boundary</span><strong>FY 2024 to 2026</strong><p>56,887 DPWH records<br>Source modified 22 Jan 2026</p><a href="/methodology/#source-policy">Read the source policy</a></aside></section>
  <section class="integrity-warning"><strong>Not a corruption score.</strong><p>Each signal describes a specific source contradiction, missing field, or identity question. It does not establish fraud, a ghost project, poor workmanship, collusion, or unlawful conduct.</p></section>
  <section class="integrity-summary" data-integrity-summary aria-label="Delivery-integrity snapshot"><p>Loading verified snapshot totals...</p></section>
  <section class="integrity-shell" data-integrity-desk>
    <form class="integrity-controls" data-integrity-form role="search"><label>Search records<input type="search" name="q" maxlength="200" placeholder="Contract, project, contractor, or place"></label><label>Review signal<select name="signal"><option value="all">All signals</option><option value="status_progress_conflict">Ongoing at 100% progress</option><option value="completed_progress_conflict">Completed below 100%</option><option value="past_completion_not_complete">Completion date passed without completed status</option><option value="date_order_conflict">Date order conflict</option><option value="nonpositive_active_budget">Nonpositive active budget</option><option value="missing_coordinate">Coordinate not available</option><option value="coordinate_outside_philippines">Coordinate outside broad bounds</option><option value="completed_without_satellite_image">Completed without satellite image</option><option value="reused_coordinate">Coordinate reused across projects</option><option value="same_site_repeat_family">Same site and project family across fiscal years</option><option value="coordinate_location_conflict">Coordinate and location conflict</option></select></label><label>Evidence class<select name="classification"><option value="all">All classes</option><option value="source_conflict">Source conflict</option><option value="amount_review">Amount review</option><option value="identity_review">Identity review</option><option value="coverage_gap">Coverage gap</option></select></label><label>Fiscal year<select name="year"><option value="">All years</option><option>2026</option><option>2025</option><option>2024</option></select></label><label>Sort<select name="sort"><option value="budget_desc">Largest project budget</option><option value="year_desc">Newest fiscal year</option><option value="contract_asc">Contract number</option></select></label><button type="submit">Apply</button></form>
    <div class="integrity-toolbar" aria-live="polite"><p><strong data-integrity-count>0</strong> of <span data-integrity-total>0</span> signals shown. <span data-integrity-status>Loading source-review signals...</span></p><a data-integrity-export href="/api/v1/integrity.csv">Download evidence CSV</a></div>
    <div class="integrity-list" data-integrity-results></div>
    <div class="integrity-actions"><button type="button" data-integrity-more hidden>Load more signals</button></div>
    <noscript><p class="explorer-error">JavaScript is required for interactive filtering. The read-only JSON and CSV APIs remain available.</p></noscript>
  </section>
  <section class="contractor-section" aria-labelledby="contractor-heading"><div class="contractor-heading"><div><p class="kicker">Archived DPWH activity</p><h2 id="contractor-heading">Contractors with the most projects.</h2></div><p>Explicit slash-delimited joint ventures are split into their recorded parties. Associated project budget is repeated for every listed party because the source does not state each party's award share. Current PCAB-table status is a present-day verification, not status on the award date.</p></div>
    <div class="contractor-shell" data-contractor-desk><form class="contractor-controls" data-contractor-form role="search"><label>Find contractor<input type="search" name="q" maxlength="200" placeholder="Contractor name or PCAB ID"></label><label>Ranking<select name="sort"><option value="count_desc">Rank by project count</option><option value="budget_desc">Rank by associated project budget</option><option value="name_asc">Contractor name A to Z</option></select></label><button type="submit">Apply ranking</button></form><div class="contractor-toolbar" aria-live="polite"><p><strong data-contractor-count>0</strong> of <span data-contractor-total>0</span> contractor identities shown</p><p data-contractor-status>Loading contractor activity...</p></div><div class="contractor-list" data-contractor-results></div><div class="contractor-actions"><button type="button" data-contractor-more hidden>Load more contractors</button></div></div>
  </section>
  <section class="concentration-section" data-concentration-desk aria-labelledby="concentration-heading"><div class="contractor-heading"><div><p class="kicker">Transparent concentration</p><h2 id="concentration-heading">Where one contractor appears often.</h2></div><p>This view ranks groups with at least 20 projects. Its denominator is contractor-party associations, so every explicitly listed joint-venture party is counted once. It is a screening measure, not evidence of bid coordination or wrongdoing.</p></div><form class="concentration-controls" data-concentration-form><label>Group by<select name="dimension"><option value="region">Region label</option><option value="province">Province or district-office label</option><option value="category">Project category</option></select></label><label>Fiscal year<select name="year"><option value="0">All years</option><option value="2026">2026</option><option value="2025">2025</option><option value="2024">2024</option></select></label><button type="submit">Compare groups</button></form><p class="concentration-status" data-concentration-status aria-live="polite">Loading concentration analysis...</p><div class="concentration-list" data-concentration-results></div></section>
  <section class="integrity-method"><div><p class="kicker">Reading the evidence</p><h2>Every tag has a narrow meaning.</h2><p>The system publishes the exact rule, source fields, and limitation beside each result.</p></div><div><ul><li>Status and progress conflicts reproduce fields that disagree inside the same archived record.</li><li>Coordinate reuse and conflicting location labels identify exact source-coordinate patterns, not verified geographic boundaries.</li><li>Congressional district context uses the exact listed DPWH office. Shared offices retain every possible district and representative; no geographic guess is made.</li><li>District context does not establish political authorship, sponsorship, control, responsibility, or insertion.</li><li>Same-site project-family recurrence can describe legitimate phases or continuing works.</li><li>Missing coordinates or imagery are coverage gaps and do not show that a physical project is missing.</li><li>PCAB checks use the current regular-license table and do not establish historical license status.</li><li>PhilGEPS contract-level linkage remains unpublished until a complete reproducible award artifact is acquired.</li></ul></div></section>`;

export const changesBody = `
  <section class="data-intro change-intro"><div><p class="kicker">FY2027 budget change ledger</p><h1>Trace what changed between the NEP and House bill.</h1><p class="lede">Inspect project-level additions, removals and amount changes across DPWH infrastructure, farm-to-market roads, health facilities and irrigation.</p></div><aside class="snapshot-card"><span>Evidence boundary</span><strong>NEP → House</strong><p>Four project-level programs<br>House second or third reading</p><a href="/methodology/#source-policy">Read the source policy</a></aside></section>
  <section class="change-disclaimer"><strong>Not a corruption finding.</strong> A new-line candidate means a House project row was not matched to a NEP row in this comparison. It may be new, renamed, split, merged or outside the matching evidence.</section>
  <section class="change-summary" aria-label="Change-ledger totals"><article><strong>20,431</strong><span>reconciled comparison rows</span></article><article><strong>4</strong><span>project-level programs</span></article><article><strong>426</strong><span>quarantined or scope-review rows</span></article><article><strong>8</strong><span>hashed source documents</span></article></section>
  <section class="change-shell" data-change-ledger>
    <form class="change-controls" data-change-form role="search"><label>Search projects<input type="search" name="q" maxlength="200" placeholder="Project, program, office"></label><label>Program<select name="dataset"><option value="all">All four</option><option value="dpwh">DPWH</option><option value="fmr">Farm-to-market roads</option><option value="hfep">Health facilities</option><option value="nia">Irrigation</option></select></label><label>Change<select name="change"><option value="all">All changes</option><option value="house_only">In the House bill only</option><option value="nep_only">In the NEP only</option><option value="increased">Amount increased</option><option value="decreased">Amount decreased</option><option value="unchanged">Unchanged</option><option value="scope_review">Scope review</option></select></label><label>Review status<select name="review"><option value="all">All statuses</option><option value="candidate">Candidate</option><option value="quarantine">Quarantine</option></select></label><label>Sort<select name="sort"><option value="absolute_desc">Largest movement</option><option value="house_desc">Largest House amount</option><option value="increase_desc">Largest increase</option><option value="decrease_desc">Largest decrease</option><option value="title_asc">Project A to Z</option></select></label><button type="submit">Apply</button><button type="button" class="secondary-control" data-change-reset>Reset</button></form>
    <div class="change-result-summary" aria-live="polite"><p><strong data-change-count>0</strong> of <span data-change-total>0</span> rows shown</p><p data-change-status>Loading reconciled comparisons…</p></div>
    <div class="change-list" data-change-results></div><div class="change-actions"><button type="button" data-change-more hidden>Load more</button></div>
    <noscript><p class="explorer-error">JavaScript is required for interactive filtering. The read-only JSON API remains available.</p></noscript>
  </section>
  <section class="change-scope"><div><p class="kicker">What this ledger covers</p><h2>Four programs, not the entire national budget.</h2></div><div><p>Rows are provisional comparisons derived from published NEP and House documents and independently reconciled to their program controls.</p><ul><li>DPWH national infrastructure</li><li>Department of Agriculture farm-to-market roads</li><li>DOH Health Facilities Enhancement Program</li><li>National Irrigation Administration projects</li></ul></div></section>`;

export const agenciesBody = `
  <section class="data-intro agency-intro"><div><p class="kicker">FY2027 agency budget ledger</p><h1>See how agency budgets changed in the House bill.</h1><p class="lede">Compare every national appropriation head from the Executive's NEP with page-specific totals in HB 10858. Senate and House are shown separately under Congress.</p></div><aside class="snapshot-card"><span>Reconciled scope</span><strong>39 appropriation heads</strong><p>37 departments and constitutional bodies<br>Special Purpose Funds<br>Automatic Appropriations shown separately</p><a href="/methodology/#agency-ledger">Read the comparison method</a></aside></section>
  <section class="agency-stage-map" aria-label="FY2027 budget stages"><article><span>01 · Baseline</span><strong>FY2026 base</strong><p>Prior-year comparison values in the NEP dataset.</p></article><article><span>02 · Executive</span><strong>FY2027 NEP</strong><p>The President's proposed national budget.</p></article><article><span>03 · Legislature</span><strong>House Bill 10858</strong><p>Third-reading appropriation totals by source page.</p></article><article class="pending"><span>04 · Pending</span><strong>Senate, bicam, GAA</strong><p>Not published as comparable totals yet. Never treated as zero.</p></article></section>
  <section class="agency-disclaimer"><strong>Not spending or a finding of wrongdoing.</strong><p>These are proposed appropriations and recorded movements between documents. A large increase, decrease, or congressional change is a lead for document review, not proof of an insertion, release, payment, loss, or unlawful act.</p></section>
  <section class="agency-summary" aria-label="Ledger summary"><article><strong>₱4.619T</strong><span>NEP bill-scope total</span></article><article><strong>₱4.606T</strong><span>House bill control</span></article><article><strong>−₱12.637B</strong><span>Net bill-scope movement</span></article><article><strong>43 of 44</strong><span>Rows compared; Automatic Appropriations not applicable</span></article></section>
  <section class="agency-shell" data-agency-ledger>
    <form class="agency-controls" data-agency-form><label>Search appropriation heads<input type="search" name="q" maxlength="200" placeholder="DPWH, education, Senate…"></label><label>Level<select name="level"><option value="heads">Appropriation heads</option><option value="congress">Congress institutions</option><option value="all">All rows</option></select></label><label>Movement<select name="direction"><option value="all">All movements</option><option value="increase">House increases</option><option value="decrease">House decreases</option><option value="unchanged">No change</option><option value="unavailable">House stage unavailable</option></select></label><label>Sort<select name="sort"><option value="difference_desc">Largest increase</option><option value="difference_asc">Largest decrease</option><option value="house_desc">Largest House amount</option><option value="nep_desc">Largest NEP amount</option><option value="name_asc">Name A–Z</option></select></label><button type="submit">Apply</button><button class="secondary-control" type="button" data-agency-reset>Reset</button></form>
    <div class="agency-result-summary"><p><strong data-agency-count>0</strong> of <strong data-agency-total>0</strong> rows shown</p><p data-agency-status aria-live="polite">Loading reconciled appropriation totals…</p></div><div class="agency-list" data-agency-results></div><div class="agency-actions"><button type="button" data-agency-more hidden>Load more</button></div>
  </section>
  <section class="agency-method"><div><p class="kicker">How to read this ledger</p><h2>Totals are comparable only inside their declared scope.</h2></div><div><ul><li>The 39 appropriation heads reconcile to the ₱7.200186 trillion NEP, including Automatic Appropriations.</li><li>The 38 House-comparable heads reconcile to the bill's printed ₱4.606066495 trillion new-appropriations control.</li><li>Automatic Appropriations are outside the House bill control and therefore remain not applicable, not zero.</li><li>Congress institution rows are children of the Congress head and must not be added again to the national total.</li></ul></div></section>`;

export const projectDossierBody = (record) => {
  const signals = record.match_signals
    .map((signal) => `<li>${escapeHtml(signal.replaceAll('_', ' '))}</li>`)
    .join('');
  const sources = record.evidence_urls
    .map((url, index) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Official evidence ${index + 1}</a>`)
    .join('');
  const status = record.is_quarantined ? 'Quarantined candidate' : 'Reviewed link';
  return `
  <nav class="dossier-breadcrumbs" aria-label="Breadcrumb"><a href="/explore/?view=reviewed">Reviewed dossiers</a><span>/</span><span>${escapeHtml(record.contract_id)}</span></nav>
  <article class="dossier">
    <header class="dossier-header"><div><span class="record-type ${record.is_quarantined ? 'candidate' : 'reviewed'}">${status}</span><p class="kicker">FY ${record.fiscal_year} · ${escapeHtml(record.contract_id)}</p><h1>${escapeHtml(record.title)}</h1><p>${escapeHtml(record.location)}</p></div><aside><span>Match confidence</span><strong>${escapeHtml(record.confidence)}</strong><small>Evidence score ${record.confidence_score}</small></aside></header>
    ${record.is_quarantined ? '<section class="dossier-warning"><strong>This relationship is not confirmed.</strong><p>The source records remain separate because the current evidence does not meet the reviewed-link standard.</p></section>' : ''}
    <section class="amount-comparison" aria-label="Budget amount comparison"><article><span>GAA appropriation</span><strong>${peso(record.appropriation_centavos)}</strong><small>Authority to spend, not proof of disbursement</small></article><article><span>DPWH project budget</span><strong>${peso(record.contract_budget_centavos)}</strong><small>Recorded in the archived DPWH snapshot</small></article><article><span>Recorded difference</span><strong>${peso(record.variance_centavos)}</strong><small>Comparison only, not a finding of loss</small></article></section>
    <section class="dossier-grid"><div><p class="kicker">Delivery record</p><h2>${escapeHtml(record.delivery_title)}</h2><dl><div><dt>Contract</dt><dd>${escapeHtml(record.contract_id)}</dd></div><div><dt>Implementing office</dt><dd>${escapeHtml(record.implementing_office)}</dd></div><div><dt>Source of funds</dt><dd>${escapeHtml(record.source_of_funds)}</dd></div></dl></div><aside><p class="kicker">Why these records may relate</p><ul>${signals}</ul><p>${escapeHtml(record.match_limitations)}</p></aside></section>
    <section class="dossier-sources"><div><p class="kicker">Evidence trail</p><h2>Inspect the records underneath the link.</h2></div><div>${sources}</div></section>
  </article>`;
};

const pipeline = `
  <div class="pipeline-groups">
    <section class="pipeline-group"><span>01 / Integrity</span><h3>Preserve</h3><ol><li><strong>Acquire</strong><small>Fetch a named official source.</small></li><li><strong>Hash and archive</strong><small>Keep an immutable copy and digest.</small></li></ol></section>
    <section class="pipeline-group"><span>02 / Consistency</span><h3>Normalize</h3><ol><li><strong>Validate schema</strong><small>Reject malformed records.</small></li><li><strong>Normalize units</strong><small>Standardize dates, amounts, and scale.</small></li><li><strong>Reconcile controls</strong><small>Compare with published totals.</small></li></ol></section>
    <section class="pipeline-group"><span>03 / Identity</span><h3>Link</h3><ol><li><strong>Match identity</strong><small>Connect records with explainable evidence.</small></li><li><strong>Classify confidence</strong><small>Keep uncertainty visible.</small></li></ol></section>
    <section class="pipeline-group"><span>04 / Decision</span><h3>Review</h3><ol><li><strong>Calculate anomalies</strong><small>Run deterministic rules.</small></li><li><strong>Quarantine</strong><small>Hold conflicts and weak evidence.</small></li><li><strong>Publish</strong><small>Release only passing records.</small></li></ol></section>
  </div>`;

export const methodologyBody = `
  <section class="page-intro"><div><p class="kicker">Methodology</p><h1>Every public link needs a source trail.</h1></div><div><p class="lede">Collection, normalization, matching, review, and publication are separated so that a plausible relationship cannot quietly become a public claim.</p>${methodDiagram}</div></section>
  <nav class="local-nav" aria-label="Methodology sections"><span>Jump to</span><a href="#pipeline">Pipeline</a><a href="#source-policy">Source policy</a><a href="#agency-ledger">Agency ledger</a><a href="#release-standard">Release standard</a><a href="#corrections">Corrections</a></nav>

  <section class="narrative-section" id="pipeline" aria-labelledby="pipeline-heading">
    <div class="section-heading"><p class="section-number">01 / Pipeline</p><div><h2 id="pipeline-heading">Ten controls. Four evidence stages.</h2><p class="section-intro">A failure at any stage prevents publication. Quarantine is an intended outcome, not an exception.</p></div></div>${pipeline}
  </section>

  <section class="narrative-section" id="source-policy" aria-labelledby="source-heading">
    <div class="section-heading"><p class="section-number">02 / Source policy</p><div><h2 id="source-heading">Confidence follows evidence.</h2><p class="section-intro">Names alone are not enough to establish that two records refer to the same project.</p></div></div>
    <div class="policy-grid">
      <article class="policy-item"><span>EXACT</span><h3>Direct identifier match</h3><p>Stable identifiers and compatible official fields point to the same record.</p></article>
      <article class="policy-item"><span>HIGH CONFIDENCE</span><h3>Multiple facts agree</h3><p>Location, agency, description, amount, and timing agree without material conflict.</p></article>
      <article class="policy-item"><span>CANDIDATE</span><h3>Human review required</h3><p>Some evidence aligns, but ambiguity or missing fields prevent a public link.</p></article>
    </div>
    <div class="standards-grid"><article class="standard-panel"><h3>Congressional district context</h3><p>District and representative names come from a hashed, dated 20th Congress roster snapshot linked to official House member profiles. Project context is assigned only through an exact listed DPWH office mapping. Shared offices show every served district, and unmatched offices remain unavailable.</p></article><article class="standard-panel"><h3>Boundary of the attribution</h3><p>This is not a coordinate or boundary-polygon determination. It does not show who requested, sponsored, controlled, inserted, or is responsible for a project or amount.</p></article></div>
  </section>

  <section class="narrative-section" id="agency-ledger" aria-labelledby="agency-ledger-heading">
    <div class="section-heading"><p class="section-number">03 / Agency ledger</p><div><h2 id="agency-ledger-heading">Compare only totals with the same appropriation scope.</h2><p class="section-intro">The FY2027 ledger joins 39 exact NEP appropriation-head identities to the third-reading House bill. Each House value is extracted from a declared PDF page and the complete set reconciles to the bill's printed control.</p></div></div>
    <div class="standards-grid"><article class="standard-panel"><h3>Source and arithmetic controls</h3><p>Original PDF and API bytes are archived by SHA-256. Money is stored as integer centavos. The NEP heads reconcile to ₱7.200186 trillion; the House-comparable heads reconcile to the printed ₱4.606066495 trillion new-appropriations control.</p></article><article class="standard-panel"><h3>Stage and hierarchy controls</h3><p>Automatic Appropriations are outside the House bill control and remain not applicable. The five Congress institutions are child rows, so they are never added again to the national total. Senate, bicameral, GAA, release, obligation, and payment stages remain unavailable until comparable evidence is acquired.</p></article></div>
  </section>

  <section class="narrative-section" id="release-standard" aria-labelledby="release-heading">
    <div class="section-heading"><p class="section-number">04 / Release standard</p><div><h2 id="release-heading">The register opens only after measured review.</h2></div></div>
    <div class="standards-grid"><article class="standard-panel"><h3>Required before release</h3><p>At least <strong>100 reviewed linkage cases</strong>, at least 95% measured precision, at least 95% reviewer agreement, and no unresolved critical reconciliation failure.</p></article><article class="standard-panel"><h3>How to read a signal</h3><p>A signal identifies a record pattern for examination. It is <strong>not evidence of wrongdoing</strong>, waste, or unlawful conduct.</p><p>Every published signal must show its rule, inputs, confidence, source references, and known limitations.</p></article></div>
  </section>

  <section class="narrative-section" id="corrections" aria-labelledby="corrections-heading">
    <div class="section-heading"><p class="section-number">05 / Corrections</p><div><h2 id="corrections-heading">Corrections keep their history.</h2><p class="section-intro">A correction preserves the prior version, records what changed, and identifies the evidence behind the decision. A record that loses support returns to quarantine.</p></div></div>
  </section>`;

export const siteCss = `${baseSiteCss}\n${dataCss}\n${typeCss}\n${changeCss}\n${agencyCss}\n${reviewCss}\n${integrityCss}`;

export const favicon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g stroke="#102f2a" stroke-width="2.5" stroke-linejoin="round"><path fill="#a7ddc3" d="m8 39 24 14 24-14v9L32 62 8 48Z"/><path fill="#fbf8ef" d="m8 28 24 14 24-14v9L32 51 8 37Z"/><path fill="#fbf8ef" d="M8 17 32 3l24 14-24 14Z"/></g><path fill="none" stroke="#b83b27" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" d="M18 44V34l14-8v-9l9-5"/><circle cx="18" cy="44" r="3.5" fill="#fbf8ef" stroke="#b83b27" stroke-width="3"/><circle cx="32" cy="26" r="3.5" fill="#fbf8ef" stroke="#b83b27" stroke-width="3"/><circle cx="51" cy="12" r="10" fill="#102f2a"/><path fill="none" stroke="#f3efe4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" d="m46.5 12 3 3 6-7"/></svg>`;
