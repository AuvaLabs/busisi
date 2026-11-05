import { contractEvidenceLedger } from './contract-evidence-content.js';
import { fullUniverseCoverage } from './acquisition-coverage-content.js';

const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const plainPublicText = (value) => String(value ?? '')
  .replace(/\bacquired\b/gi, 'available')
  .replace(/\bacquisition\b/gi, 'document search')
  .replace(/\bartifact\b/gi, 'document')
  .replace(/\bquarantined\b/gi, 'held back for checking')
  .replace(/\breconciled\b/gi, 'checked')
  .replace(/\bsnapshot\b/gi, 'dated copy');

const publicHtml = (value) => html(plainPublicText(value));

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
  ? 'Source copy saved and checked'
  : source.acquisition_status === 'blocked'
    ? 'Official source found, but the copy could not be saved'
    : source.acquisition_status.replaceAll('_', ' ');

const sourceCard = (source) => {
  const url = safeLink(source.source_url);
  return `<article class="audit-report-card"><header><span>${html(source.document_type.replaceAll('_', ' '))}</span><b>FY ${source.fiscal_year}</b></header><h2>${html(source.title)}</h2><p>${html(source.publisher)}</p><dl><div><dt>Source copy</dt><dd>${html(sourceStatus(source))}</dd></div><div><dt>Saved-file check code</dt><dd>${source.artifact_sha256 ? `<code>${html(source.artifact_sha256)}</code>` : 'No saved copy'}</dd></div></dl><p>${publicHtml(source.evidence_note)}</p>${url ? `<a href="${html(url)}" target="_blank" rel="noopener noreferrer">Open official source</a>` : ''}</article>`;
};

const coverageLabel = (status) => ({
  exact_evidence: 'Exact procurement evidence',
  partial_evidence: 'Partial procurement evidence',
  not_located: 'No exact document located',
  current_year_not_yet_located: 'Current-year evidence not yet located',
  quarantined: 'Held back for checking',
}[status] || status.replaceAll('_', ' '));

const outcomeCard = (outcome) => {
  const questionCount = outcome.questions.length;
  const amount = outcome.amount_check;
  const mirror = outcome.award_mirror;
  const title = outcome.case_id
    ? `<a class="record-title-link" href="/projects/${encodeURIComponent(outcome.case_id)}/#contract-outcome">${html(outcome.title)}</a>`
    : html(outcome.title);
  return `<article class="outcome-card"><header><span>FY ${outcome.fiscal_year}</span><b>${html(outcome.contract_id)}</b></header><h3>${title}</h3><dl>${mirror ? `<div><dt>Mirror-reported awardee</dt><dd>${html(mirror.awardee_name)}</dd></div>` : ''}<div><dt>Delivery record contractor</dt><dd>${html(outcome.contractor_name || 'Not stated')}</dd></div>${mirror ? `<div><dt>Do the names agree?</dt><dd>${publicHtml(outcome.awardee_check.label)}</dd></div>` : ''}<div><dt>Do the amounts agree?</dt><dd>${publicHtml(amount.label)}</dd></div>${amount.difference_centavos === null ? '' : `<div><dt>Recorded difference</dt><dd>${html(money(amount.difference_centavos))}</dd></div>`}<div><dt>Awardee document</dt><dd>${publicHtml(outcome.awardee_evidence.label)}</dd></div><div><dt>Inspection document</dt><dd>${publicHtml(outcome.inspection_evidence.label)}</dd></div><div><dt>Payment document</dt><dd>${publicHtml(outcome.payment_evidence.label)}</dd></div></dl><p><strong>${questionCount} question${questionCount === 1 ? '' : 's'} to check.</strong> These comparisons do not prove wrongdoing.</p>${outcome.case_id ? `<a href="/projects/${encodeURIComponent(outcome.case_id)}/#contract-outcome">Open the supporting records</a>` : ''}</article>`;
};

export const procurementDeskBody = ({
  summary, sources, coverage, outcomes = [], evidenceSummary, evidenceItems = [],
  acquisitionCoverage,
}) => {
  const metadata = summary.metadata || {};
  return `<section class="data-intro audit-intro"><div><p class="kicker">Contract documents</p><h1>What contract documents can Busisi find?</h1><p class="lede">Follow a contract number through procurement plans, bid notices, and monitoring reports. See which documents Busisi found and which are still missing.</p></div><aside class="snapshot-card"><span>Small checked sample</span><strong>${html(metadata.projects_with_evidence || '0')} of ${html(metadata.checked_projects || '0')} project files have evidence</strong><p>${html(metadata.record_count || '0')} exact records<br>${html(metadata.archived_sources || '0')} source copy saved</p></aside></section>
  <section class="evidence-boundary"><strong>A missing document does not mean procurement did not happen</strong><p>A procurement plan shows an intention. A bid notice shows a posting. A monitoring report does not prove payment, work quality, or COA clearance.</p></section>
  ${acquisitionCoverage ? fullUniverseCoverage(acquisitionCoverage) : ''}
  ${contractEvidenceLedger(evidenceSummary, evidenceItems)}
  <section class="evidence-section"><p class="kicker">Compare the records</p><h2>Do the contract records agree?</h2><p>Busisi compares procurement amounts and dates with the DPWH project record. A name found in a secondary copy is not treated as an official award notice.</p><div class="outcome-grid">${outcomes.map(outcomeCard).join('')}</div><aside class="evidence-boundary"><strong>Questions to check, not findings</strong><p>A difference or missing document does not prove fraud, corruption, missing work, or improper payment.</p></aside></section>
  <section class="evidence-section"><p class="kicker">Official evidence</p><h2>Sources behind the pilot records</h2><div class="audit-report-grid">${sources.map(sourceCard).join('')}</div></section>
  <section class="evidence-section"><p class="kicker">Six checked examples</p><h2>Exact matches and clearly marked gaps</h2><div class="audit-catalog-list">${coverage.map((item) => `<article><div><span>${html(coverageLabel(item.status))}</span><h3><a class="record-title-link" href="/projects/${encodeURIComponent(item.case_id)}/">FY ${item.fiscal_year} · ${html(item.contract_id)}</a></h3><p>${publicHtml(item.review_note)}</p></div><a href="/projects/${encodeURIComponent(item.case_id)}/">Open project evidence</a></article>`).join('')}</div></section>`;
};
