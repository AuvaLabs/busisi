const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const money = (centavos) => new Intl.NumberFormat('en-PH', {
  style: 'currency', currency: 'PHP',
}).format(Number(centavos || 0) / 100);

const coordinates = (record) => (
  Number.isInteger(record.latitude_e6) && Number.isInteger(record.longitude_e6)
    ? `${(record.latitude_e6 / 1_000_000).toFixed(6)}, ${(record.longitude_e6 / 1_000_000).toFixed(6)}`
    : 'Not stated in the official list'
);

const yesNo = (value) => value === 1 ? 'Yes in the source list' : 'Not marked yes in the source list';

const linkedRecords = (links) => links.length ? `<ul class="evidence-record-list">${links.map((item) => `
  <li><div><span>FY ${item.fiscal_year} · ${item.source_type === 'budget' ? 'Budget-stage record' : 'DPWH delivery record'}</span><strong>${html(item.title)}</strong><small>${html(item.location || item.office || 'Place not stated')}</small></div><b>${html(money(item.amount_centavos))}</b><a href="${html(item.reader_url)}">Open linked record</a></li>`).join('')}</ul>` : '<p class="evidence-empty">No public budget or delivery record has a confirmed link to this facility.</p>';

export const facilityBody = ({ record, links, summary }) => `<nav class="evidence-breadcrumbs" aria-label="Breadcrumb">
  <a href="/public-services/">Public services</a><span>/</span><span>Official facility</span><span>/</span><span>${html(record.official_id)}</span>
</nav><article class="evidence-dossier"><header class="evidence-header"><div><span class="evidence-badge reviewed">Official facility identity</span><p class="kicker">Official school ID ${html(record.official_id)}</p><h1>${html(record.official_name)}</h1><p class="lede">${html(record.municipality)} · ${html(record.division || record.province)} · ${html(record.region)}</p></div></header>
<dl class="evidence-facts"><div><dt>Linked public records</dt><dd>${summary.record_count}</dd><small>Records, not a count of school buildings</small></div><div><dt>Budget-stage records</dt><dd>${summary.budget_records}</dd><small>${html(money(summary.budget_amount_centavos))}, kept separate</small></div><div><dt>Delivery records</dt><dd>${summary.delivery_records}</dd><small>${html(money(summary.delivery_amount_centavos))}, kept separate</small></div></dl>
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Registry identity</p><h2>What DepEd published</h2><dl class="evidence-details"><div><dt>School ID</dt><dd>${html(record.official_id)}</dd></div><div><dt>School name</dt><dd>${html(record.official_name)}</dd></div><div><dt>Division</dt><dd>${html(record.division || 'Not stated')}</dd></div><div><dt>City or municipality</dt><dd>${html(record.municipality)}</dd></div><div><dt>Region</dt><dd>${html(record.region)}</dd></div><div><dt>Coordinates</dt><dd>${html(coordinates(record))}</dd></div><div><dt>Source row</dt><dd>${html(record.source_row || 'Not stated')}</dd></div></dl></section>
<section class="evidence-panel"><p class="kicker">Indicative site information</p><h2>Planning fields in the source list</h2><dl class="evidence-details"><div><dt>Demolition required</dt><dd>${yesNo(record.demolition_required)}</dd></div><div><dt>Geotechnical report</dt><dd>${yesNo(record.geotechnical_report)}</dd></div><div><dt>Previous site plan</dt><dd>${yesNo(record.site_development_plan)}</dd></div><div><dt>Ownership documents</dt><dd>${yesNo(record.ownership_documents)}</dd></div></dl><p class="evidence-limit">A blank source cell is shown as not marked yes. It is not converted into a definite no.</p></section></div>
<section class="evidence-section"><p class="kicker">Linked public records</p><h2>${summary.record_count} linked public record${summary.record_count === 1 ? '' : 's'}</h2><p>Appropriations and contract budgets describe different stages. Busisi keeps their amounts separate.</p>${linkedRecords(links)}</section>
<section class="evidence-section"><p class="kicker">Where this information came from</p><h2>${html(record.dataset_name)}</h2><dl class="provenance-grid"><div><dt>Publisher</dt><dd>${html(record.publisher)}</dd></div><div><dt>Downloaded</dt><dd>${html(record.acquired_at)}</dd></div><div><dt>Saved-file check code</dt><dd><code>${html(record.artifact_sha256)}</code></dd></div><div><dt>Source status</dt><dd>${html(record.source_status)}</dd></div></dl><p>${html(record.scope_note)}</p><a class="evidence-action" href="${html(record.source_url)}" target="_blank" rel="noopener noreferrer">Open official DepEd source file</a></section>
<aside class="evidence-boundary"><strong>What this does not prove</strong><p>An official school identity and linked public records do not prove a new building was constructed, that work started or finished, that payment occurred, or that the facility information remains current. The indicative list is not a complete national registry.</p></aside></article>`;
