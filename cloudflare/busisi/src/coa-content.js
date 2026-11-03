const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const statusLabel = (status) => ({
  discovered: 'Source record discovered',
  verified_archived: 'Source copy archived and verified',
  unavailable: 'Source unavailable',
}[status] || status.replaceAll('_', ' '));

const reportCard = (report) => `<article class="audit-report-card">
  <div><span>${html(report.report_type.replaceAll('_', ' '))} · FY ${report.fiscal_year}</span><h3>${html(report.title)}</h3><p>${html(report.scope_note)}</p></div>
  <dl><div><dt>Audited entity</dt><dd>${html(report.audited_entity)}</dd></div><div><dt>Acquisition</dt><dd>${html(statusLabel(report.acquisition_status))}</dd></div></dl>
  <a href="/audit/reports/${encodeURIComponent(report.report_id)}/">Read the evidence record</a>
</article>`;

export const coaDeskBody = ({ summary, reports }) => {
  const { metadata, statuses, catalogs } = summary;
  return `<section class="data-intro audit-intro"><div><p class="kicker">Independent audit trail</p><h1>COA audit evidence desk.</h1><p class="lede">See which official audit reports were checked, where a project-level observation was actually matched, and where the public trail still stops.</p></div><aside class="snapshot-card"><span>Catalogue review</span><strong>${html(metadata.checked_projects || '0')} dossiers checked</strong><p>${html(metadata.project_matches || '0')} project observation matches<br>${html(metadata.archived_reports || '0')} source copies archived</p></aside></section>
  <section class="evidence-boundary"><strong>Absence is not clearance</strong><p>No located observation does not mean COA cleared a project. An audit opinion is not a score, and an observation is not automatically a disallowance or proof of wrongdoing.</p></section>
  <section class="dataset-stats" aria-label="COA evidence totals"><article><span>${html(metadata.report_count || '0')}</span><p>official report records indexed</p></article><article><span>${html(metadata.checked_projects || '0')}</span><p>Busisi dossiers checked</p></article><article><span>${html(metadata.project_matches || '0')}</span><p>project observation matches</p></article><article><span>${html(statuses.not_covered || 0)}</span><p>without located project-level evidence</p></article></section>
  <section class="evidence-section"><p class="kicker">Indexed official reports</p><h2>Reports available for evidence review</h2><div class="audit-report-grid">${reports.map(reportCard).join('')}</div></section>
  <section class="evidence-section"><p class="kicker">Coverage log</p><h2>Official catalogues checked</h2><div class="audit-catalog-list">${catalogs.map((catalog) => `<article><div><span>${html(catalog.checked_status.replaceAll('_', ' '))}</span><h3>${html(catalog.title)}</h3><p>${html(catalog.evidence_note)}</p></div><a href="${html(catalog.source_url)}" target="_blank" rel="noopener noreferrer">Open official catalogue</a></article>`).join('')}</div></section>
  <aside class="evidence-boundary"><strong>Publication rule</strong><p>Busisi publishes a project-level COA link only after an exact identifier match or a reviewed high-confidence combination of title, location, amount, year, and implementing office. Ambiguous matches remain quarantined.</p></aside>`;
};

export const coaReportBody = (report) => `<nav class="evidence-breadcrumbs" aria-label="Breadcrumb"><a href="/audit/">COA audit evidence</a><span>/</span><span>${html(report.report_id)}</span></nav>
<article class="evidence-dossier"><header class="evidence-header"><div><span class="evidence-badge reviewed">${html(statusLabel(report.acquisition_status))}</span><p class="kicker">${html(report.report_type.replaceAll('_', ' '))} · FY ${report.fiscal_year}</p><h1>${html(report.title)}</h1><p class="lede">${html(report.audited_entity)}</p></div></header>
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Report scope</p><h2>What this report covers</h2><p>${html(report.scope_note)}</p><dl class="evidence-details"><div><dt>Publication date</dt><dd>${html(report.publication_date || 'Not stated')}</dd></div><div><dt>Report identifier</dt><dd>${html(report.report_id)}</dd></div></dl></section><section class="evidence-panel"><p class="kicker">Acquisition status</p><h2>${report.acquisition_status === 'verified_archived' ? 'Source copy archived' : 'Source copy not archived'}</h2><p>${html(report.evidence_note)}</p>${report.artifact_sha256 ? `<dl class="evidence-details"><div><dt>SHA-256</dt><dd><code>${html(report.artifact_sha256)}</code></dd></div><div><dt>Pages</dt><dd>${report.page_count}</dd></div></dl>` : ''}</section></div>
<section class="evidence-panel"><p class="kicker">Official source</p><h2>Open the publisher record</h2><a class="evidence-action" href="${html(report.landing_url)}" target="_blank" rel="noopener noreferrer">Open COA report catalogue</a><a class="evidence-action" href="${html(report.source_url)}" target="_blank" rel="noopener noreferrer">Open official report record</a></section>
<aside class="evidence-boundary"><strong>Evidence boundary</strong><p>Being listed here does not connect this report to a particular Busisi project. Project links require a separately reviewed match with cited pages.</p></aside></article>`;
