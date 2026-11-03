import { SITE } from './prelaunch-config.js';
import { dataCss } from './prelaunch-data-styles.js';
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
  const links = `<a href="/explore/"${canonicalPath === '/explore/' ? ' aria-current="page"' : ''}>Explore</a><a href="/signals/"${canonicalPath === '/signals/' ? ' aria-current="page"' : ''}>Signals</a><a href="/#mission">Mission</a>`;
  return `<div class="header-inner">
    <a class="wordmark" href="/" aria-label="Busisi home"><img class="brand-mark" src="/assets/busisi-mark-v2.svg" width="44" height="44" alt=""><span>Busisi</span></a>
    <nav class="primary-nav" aria-label="Primary navigation">${links}<a class="method-link" href="/methodology/"${methodology ? ' aria-current="page"' : ''}>Methodology</a></nav>
  </div>`;
};

const utilityStrip = `<div class="utility-strip"><div class="utility-inner">
  <span>Independent Philippine budget evidence project</span>
  <a href="/explore/"><i aria-hidden="true"></i>Public source snapshot: FY 2024–2026</a>
</div></div>`;

const footer = `<footer class="site-footer"><div class="footer-inner">
  <div class="footer-brand"><strong>Busisi</strong><p>Independent civic data initiative for traceable Philippine public budget records.</p></div>
  <nav class="footer-nav" aria-label="Footer navigation"><a href="/explore/">Explore</a><a href="/signals/">Signals</a><a href="/methodology/">Methodology</a></nav>
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
  <link rel="canonical" href="${canonical}"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="/assets/busisi-masthead.webp" as="image" type="image/webp" fetchpriority="high"><link rel="stylesheet" href="/assets/site-visual-v4.css">
  <meta property="og:type" content="website"><meta property="og:site_name" content="Busisi"><meta property="og:title" content="${title}"><meta property="og:description" content="${description}"><meta property="og:url" content="${canonical}">
  <meta property="og:image" content="${SITE.origin}/assets/busisi-masthead.webp"><meta property="og:image:width" content="1600"><meta property="og:image:height" content="666">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${title}"><meta name="twitter:description" content="${description}"><meta name="twitter:image" content="${SITE.origin}/assets/busisi-masthead.webp">
  <script type="application/ld+json">${escapeJson(schema)}</script>${canonicalPath === '/explore/' ? '<script src="/assets/explorer-v1.js" defer></script>' : ''}
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
      <div class="actions"><a class="primary" href="/explore/">Explore the records</a><a class="secondary" href="/signals/">Review the signals</a></div>
    </div>
  </section>

  <section class="register-preview" aria-labelledby="register-preview-heading">
    <div class="preview-heading"><p class="kicker">Explore the source record</p><h2 id="register-preview-heading">Three ways to inspect public money.</h2><p>Official records are published as source records. Cross-source relationships stay labelled as candidates until they pass human review.</p></div>
    <div class="preview-panels">
      <a href="/explore/?view=budgets"><span aria-hidden="true">01</span><div><h3>GAA appropriations</h3><p>Search 68,608 positive budget records across fiscal years 2024 to 2026.</p></div><small>Official source records</small></a>
      <a href="/explore/?view=delivery"><span aria-hidden="true">02</span><div><h3>DPWH delivery records</h3><p>Inspect 56,887 contracts with recorded budgets, locations, and funding sources.</p></div><small>Official source records</small></a>
      <a href="/explore/?view=candidates"><span aria-hidden="true">03</span><div><h3>Candidate links</h3><p>Review 385 explainable machine matches without treating them as confirmed identity.</p></div><small>Human review required</small></a>
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
  <section class="data-intro signal-intro"><div><p class="kicker">Evidence-led review</p><h1>Review signals, not accusations.</h1><p class="lede">Every signal states what triggered it, what evidence it used, and what it cannot establish.</p></div><aside class="snapshot-card"><span>Current coverage</span><strong>2 supported signal families</strong><p>Other analyses remain visibly unavailable instead of being approximated.</p></aside></section>
  <section class="signal-catalog" aria-label="Available review signals"><article class="available"><span>Available</span><h2>Repeated funding</h2><p>Finds related project families with positive appropriations in at least two fiscal years.</p><dl><div><dt>Can show</dt><dd>Years, amounts, family identity, source records</dd></div><div><dt>Cannot show</dt><dd>Whether phases describe the same physical asset</dd></div></dl><a href="/explore/?view=reviewed">Inspect reviewed evidence</a></article><article class="available"><span>Available</span><h2>Zero downstream budget</h2><p>Finds a positive appropriation candidate linked to a DPWH record reporting a zero project budget.</p><dl><div><dt>Can show</dt><dd>The two source amounts and match evidence</dd></div><div><dt>Cannot show</dt><dd>Missing money or a nonexistent project</dd></div></dl><a href="/projects/corazon-2026-completion/">Inspect the quarantined example</a></article></section>
  <section class="coverage-matrix" aria-labelledby="coverage-heading"><div><p class="kicker">Evidence gaps</p><h2 id="coverage-heading">Unavailable means unavailable.</h2><p>Busisi does not generate a label when the evidence required for that label has not been acquired.</p></div><div class="coverage-list"><article><span>Not available</span><h3>Insertion analysis</h3><p>Unavailable until budget-stage records are acquired for NEP, House, Senate, bicameral, and enacted GAA comparisons.</p></article><article><span>Not available</span><h3>Physical existence verification</h3><p>Requires implementation evidence such as geotagged progress, inspections, audit findings, or field verification. Budget data alone cannot establish physical existence.</p></article><article><span>Partial</span><h3>Procurement consistency</h3><p>ABC, award, status, and physical-progress checks require current DPWH detail and PhilGEPS records beyond the archived bulk snapshot.</p></article></div></section>`;

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
  <nav class="local-nav" aria-label="Methodology sections"><span>Jump to</span><a href="#pipeline">Pipeline</a><a href="#source-policy">Source policy</a><a href="#release-standard">Release standard</a><a href="#corrections">Corrections</a></nav>

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
  </section>

  <section class="narrative-section" id="release-standard" aria-labelledby="release-heading">
    <div class="section-heading"><p class="section-number">03 / Release standard</p><div><h2 id="release-heading">The register opens only after measured review.</h2></div></div>
    <div class="standards-grid"><article class="standard-panel"><h3>Required before release</h3><p>At least <strong>100 reviewed linkage cases</strong>, at least 95% measured precision, at least 95% reviewer agreement, and no unresolved critical reconciliation failure.</p></article><article class="standard-panel"><h3>How to read a signal</h3><p>A signal identifies a record pattern for examination. It is <strong>not evidence of wrongdoing</strong>, waste, or unlawful conduct.</p><p>Every published signal must show its rule, inputs, confidence, source references, and known limitations.</p></article></div>
  </section>

  <section class="narrative-section" id="corrections" aria-labelledby="corrections-heading">
    <div class="section-heading"><p class="section-number">04 / Corrections</p><div><h2 id="corrections-heading">Corrections keep their history.</h2><p class="section-intro">A correction preserves the prior version, records what changed, and identifies the evidence behind the decision. A record that loses support returns to quarantine.</p></div></div>
  </section>`;

export const siteCss = `${baseSiteCss}\n${dataCss}\n${typeCss}`;

export const favicon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g stroke="#102f2a" stroke-width="2.5" stroke-linejoin="round"><path fill="#a7ddc3" d="m8 39 24 14 24-14v9L32 62 8 48Z"/><path fill="#fbf8ef" d="m8 28 24 14 24-14v9L32 51 8 37Z"/><path fill="#fbf8ef" d="M8 17 32 3l24 14-24 14Z"/></g><path fill="none" stroke="#b83b27" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" d="M18 44V34l14-8v-9l9-5"/><circle cx="18" cy="44" r="3.5" fill="#fbf8ef" stroke="#b83b27" stroke-width="3"/><circle cx="32" cy="26" r="3.5" fill="#fbf8ef" stroke="#b83b27" stroke-width="3"/><circle cx="51" cy="12" r="10" fill="#102f2a"/><path fill="none" stroke="#f3efe4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" d="m46.5 12 3 3 6-7"/></svg>`;
