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

export const procurementDeskBody = ({ summary, sources, coverage }) => {
  const metadata = summary.metadata || {};
  return `<section class="data-intro audit-intro"><div><p class="kicker">Contract trail</p><h1>Procurement evidence desk.</h1><p class="lede">Follow exact contract IDs through official procurement plans, bid notices, and monitoring reports without treating a posting as proof of payment or completed work.</p></div><aside class="snapshot-card"><span>Reviewed pilot</span><strong>${html(metadata.projects_with_evidence || '0')} of ${html(metadata.checked_projects || '0')} reviewed dossiers</strong><p>${html(metadata.record_count || '0')} exact evidence records<br>${html(metadata.archived_sources || '0')} source copy archived</p></aside></section>
  <section class="evidence-boundary"><strong>Evidence gap, not a clean bill</strong><p>A missing procurement artifact does not show that no procurement occurred. An APP is a plan, a bid notice is a posting, and an agency PMR is not proof of payment, inspection quality, or COA clearance.</p></section>
  <section class="evidence-section"><p class="kicker">Official evidence</p><h2>Sources behind the pilot records</h2><div class="audit-report-grid">${sources.map(sourceCard).join('')}</div></section>
  <section class="evidence-section"><p class="kicker">Six-dossier pilot</p><h2>Exact matches and explicit gaps</h2><div class="audit-catalog-list">${coverage.map((item) => `<article><div><span>${html(coverageLabel(item.status))}</span><h3>FY ${item.fiscal_year} · ${html(item.contract_id)}</h3><p>${html(item.review_note)}</p></div><a href="/projects/${html(item.case_id)}/">Open dossier</a></article>`).join('')}</div></section>`;
};
