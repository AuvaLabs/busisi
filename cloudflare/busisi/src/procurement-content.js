const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const safeLink = (value) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.toString() : '';
  } catch {
    return '';
  }
};

const money = (centavos) => centavos === null || centavos === undefined
  ? 'Not available'
  : new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' })
    .format(Number(centavos) / 100);

const sourceStatus = (source) => source.acquisition_status === 'verified_archived'
  ? 'Source archived and verified'
  : source.acquisition_status === 'blocked'
    ? 'Official source discovered, archive blocked'
    : source.acquisition_status.replaceAll('_', ' ');

const sourceCard = (source) => {
  const url = safeLink(source.source_url);
  return `<article class="audit-report-card"><header><span>${html(source.document_type.replaceAll('_', ' '))}</span><b>FY ${source.fiscal_year}</b></header><h2>${html(source.title)}</h2><p>${html(source.publisher)}</p><dl><div><dt>Acquisition</dt><dd>${html(sourceStatus(source))}</dd></div><div><dt>Fingerprint</dt><dd>${source.artifact_sha256 ? `<code>${html(source.artifact_sha256)}</code>` : 'Not archived'}</dd></div></dl><p>${html(source.evidence_note)}</p>${url ? `<a href="${html(url)}" target="_blank" rel="noopener noreferrer">Open official source</a>` : ''}</article>`;
};

const coverageLabel = (status) => ({
  exact_evidence: 'Exact procurement evidence',
  partial_evidence: 'Partial procurement evidence',
  not_located: 'No exact artifact located',
  current_year_not_yet_located: 'Current-year evidence not yet located',
  quarantined: 'Quarantined',
}[status] || status.replaceAll('_', ' '));

const outcomeCard = (outcome) => {
  const questionCount = outcome.questions.length;
  const amount = outcome.amount_check;
  const mirror = outcome.award_mirror;
  return `<article class="outcome-card"><header><span>FY ${outcome.fiscal_year}</span><b>${html(outcome.contract_id)}</b></header><h3>${html(outcome.title)}</h3><dl>${mirror ? `<div><dt>Mirror-reported awardee</dt><dd>${html(mirror.awardee_name)}</dd></div>` : ''}<div><dt>Delivery record contractor</dt><dd>${html(outcome.contractor_name || 'Not stated')}</dd></div>${mirror ? `<div><dt>Name cross-check</dt><dd>${html(outcome.awardee_check.label)}</dd></div>` : ''}<div><dt>Amount cross-check</dt><dd>${html(amount.label)}</dd></div>${amount.difference_centavos === null ? '' : `<div><dt>Recorded difference</dt><dd>${html(money(amount.difference_centavos))}</dd></div>`}<div><dt>Awardee evidence</dt><dd>${html(outcome.awardee_evidence.label)}</dd></div><div><dt>Inspection evidence</dt><dd>${html(outcome.inspection_evidence.label)}</dd></div><div><dt>Payment evidence</dt><dd>${html(outcome.payment_evidence.label)}</dd></div></dl><p><strong>${questionCount} review question${questionCount === 1 ? '' : 's'}.</strong> These are cross-source consistency checks, not findings of wrongdoing.</p>${outcome.case_id ? `<a href="/projects/${html(outcome.case_id)}/#contract-outcome">Open outcome evidence</a>` : ''}</article>`;
};

export const procurementDeskBody = ({ summary, sources, coverage, outcomes = [] }) => {
  const metadata = summary.metadata || {};
  return `<section class="data-intro audit-intro"><div><p class="kicker">Contract trail</p><h1>Procurement evidence desk.</h1><p class="lede">Follow exact contract IDs through official procurement plans, bid notices, and monitoring reports without treating a posting as proof of payment or completed work.</p></div><aside class="snapshot-card"><span>Reviewed pilot</span><strong>${html(metadata.projects_with_evidence || '0')} of ${html(metadata.checked_projects || '0')} reviewed dossiers</strong><p>${html(metadata.record_count || '0')} exact evidence records<br>${html(metadata.archived_sources || '0')} source copy archived</p></aside></section>
  <section class="evidence-boundary"><strong>Evidence gap, not a clean bill</strong><p>A missing procurement artifact does not show that no procurement occurred. An APP is a plan, a bid notice is a posting, and an agency PMR is not proof of payment, inspection quality, or COA clearance.</p></section>
  <section class="evidence-section"><p class="kicker">Cross-source review</p><h2>Contract outcome cross-checks</h2><p>Compare procurement amounts and events with the DPWH delivery snapshot. Mirror-reported awardees are versioned secondary evidence and are not presented as verified official award artifacts.</p><div class="outcome-grid">${outcomes.map(outcomeCard).join('')}</div><aside class="evidence-boundary"><strong>Questions, not findings</strong><p>A discrepancy or missing artifact is a lead for documentary review. It does not establish fraud, corruption, non-delivery, or improper payment.</p></aside></section>
  <section class="evidence-section"><p class="kicker">Official evidence</p><h2>Sources behind the pilot records</h2><div class="audit-report-grid">${sources.map(sourceCard).join('')}</div></section>
  <section class="evidence-section"><p class="kicker">Six-dossier pilot</p><h2>Exact matches and explicit gaps</h2><div class="audit-catalog-list">${coverage.map((item) => `<article><div><span>${html(coverageLabel(item.status))}</span><h3>FY ${item.fiscal_year} · ${html(item.contract_id)}</h3><p>${html(item.review_note)}</p></div><a href="/projects/${html(item.case_id)}/">Open dossier</a></article>`).join('')}</div></section>`;
};
