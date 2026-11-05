const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const number = (value) => new Intl.NumberFormat('en-PH').format(Number(value || 0));

const stateLabels = Object.freeze({
  structured_exact: 'Structured exact ID',
  title_exact: 'Exact ID in title',
  multiple_exact_rows: 'Multiple exact rows',
  conflict_review: 'Conflicting identifiers',
  no_exact_row: 'No exact mirror row',
  invalid_identifier: 'Invalid contract ID',
});

const stateRows = (states) => Object.entries(stateLabels).map(([key, label]) => (
  `<tr><th scope="row">${html(label)}</th><td>${number(states[key])}</td></tr>`
)).join('');

const yearRows = (years) => years.map((year) => {
  const usable = year.state_counts.structured_exact + year.state_counts.title_exact
    + year.state_counts.multiple_exact_rows;
  return `<tr><th scope="row">FY ${html(year.value)}</th><td>${number(year.total_contracts)}</td><td>${number(usable)}</td><td>${number(year.state_counts.no_exact_row)}</td><td>${number(year.state_counts.conflict_review)}</td></tr>`;
}).join('');

export const fullUniverseCoverage = (coverage) => {
  const { summary, states, queue, source, years } = coverage;
  const usable = (states.structured_exact || 0) + (states.title_exact || 0)
    + (states.multiple_exact_rows || 0);
  return `<section class="evidence-section acquisition-coverage" aria-labelledby="acquisition-coverage-heading"><div class="section-heading-inline"><div><p class="kicker">All current delivery records</p><h2 id="acquisition-coverage-heading">How many contracts have matching secondary records?</h2><p>This check compares every FY 2024 to FY 2026 DPWH delivery contract with one dated copy of a PhilGEPS mirror. The mirror helps Busisi find documents to check, but it is not treated as official proof.</p></div><aside><strong>${number(summary.examined_contracts)} of ${number(summary.contract_count)} contracts examined</strong><span>Every contract ID was checked</span></aside></div>
  <div class="acquisition-stat-grid"><article><span>Contracts with usable exact rows</span><strong>${number(usable)}</strong><p>The same exact contract ID appears in the secondary source.</p></article><article><span>Exact rows kept</span><strong>${number(summary.accepted_match_rows)}</strong><p>Rows remain separate when one contract has multiple exact records.</p></article><article><span>Conflicting source rows held back</span><strong>${number(summary.quarantined_source_rows)}</strong><p>These rows are not used as confirmed links.</p></article><article><span>Document checks</span><strong>${number(summary.lifecycle_task_count)}</strong><p>Nine expected document stages are listed for every contract.</p></article></div>
  <div class="acquisition-tables"><div><h3>How the records matched</h3><table><thead><tr><th>Match type</th><th>Contracts</th></tr></thead><tbody>${stateRows(states)}</tbody></table></div><div><h3>Records checked by year</h3><table><thead><tr><th>Year</th><th>Examined</th><th>Exact secondary</th><th>No exact row</th><th>Conflict</th></tr></thead><tbody>${yearRows(years)}</tbody></table></div></div>
  <div class="acquisition-queue"><div><span>Waiting for document checks</span><strong>${number(queue.pending)}</strong></div><div><span>Exact secondary rows</span><strong>${number(queue.secondary_exact)}</strong></div><div><span>Downloads to try again</span><strong>${number(queue.retry)}</strong></div><div><span>Held back because records conflict</span><strong>${number(queue.quarantined)}</strong></div></div>
  <aside class="evidence-boundary"><strong>This comparison is not official proof</strong><p>The saved ${number(source.award_source_rows)}-row copy is a secondary source. Its saved-file check code is <code>${html(source.award_sha256)}</code>. A waiting or unmatched check does not mean a document does not exist. Official notices, signed contracts, inspection records, payment records, and COA reports must be found and checked separately.</p></aside></section>`;
};
