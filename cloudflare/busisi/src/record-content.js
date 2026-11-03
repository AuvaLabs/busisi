import { gaaDocumentsUrl } from './source-presentation.js';
import { contractEvidencePanel } from './contract-evidence-content.js';

const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const money = (centavos) => new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
}).format(Number(centavos || 0) / 100);

const idPath = (kind, id) => kind === 'delivery'
  ? `/contracts/${encodeURIComponent(id)}/`
  : `/records/${kind}/${encodeURIComponent(id)}/`;
const contractorPath = (key) => `/contractors/${encodeURIComponent(key)}/`;

const safeLink = (value) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.toString() : '';
  } catch {
    return '';
  }
};

const breadcrumb = (label, value) => `<nav class="evidence-breadcrumbs" aria-label="Breadcrumb">
  <a href="/explore/">Public records</a><span>/</span><span>${html(label)}</span><span>/</span><span>${html(value)}</span>
</nav>`;

const heading = ({ badge, kicker, title, summary, tone = '' }) => `<header class="evidence-header">
  <div><span class="evidence-badge ${tone}">${html(badge)}</span><p class="kicker">${html(kicker)}</p><h1>${html(title)}</h1><p class="lede">${html(summary)}</p></div>
</header>`;

const facts = (items) => `<dl class="evidence-facts">${items.map(([label, value, note]) => `
  <div><dt>${html(label)}</dt><dd>${html(value)}</dd>${note ? `<small>${html(note)}</small>` : ''}</div>`).join('')}
</dl>`;

const boundary = (message) => `<aside class="evidence-boundary"><strong>Evidence boundary</strong><p>${html(message)}</p></aside>`;

const hash = (value) => value
  ? `<code title="${html(value)}">${html(value.slice(0, 16))}…</code>`
  : '<span>Not available</span>';

const district = (context) => {
  if (!context || context.classification === 'unassigned') {
    return `<section class="evidence-panel"><p class="kicker">Congressional context</p><h2>No exact office attribution available</h2><p>The listed office did not match a published office-to-district mapping.</p></section>`;
  }
  const rows = context.districts.map((item) => `<li><strong>${html(item.label)}</strong><span>${html(item.representative_name || 'Representative unresolved')}</span></li>`).join('');
  return `<section class="evidence-panel"><p class="kicker">Office-linked congressional context</p><h2>${html(context.office_name)}</h2><ul class="evidence-list">${rows}</ul><p class="evidence-limit">${html(context.limitation)}</p></section>`;
};

const availability = () => `<section class="evidence-panel evidence-availability">
  <p class="kicker">What can be traced</p><h2>Evidence by public-money stage</h2>
  <ol><li class="available"><b>01</b><span><strong>Appropriation or project budget</strong><small>Available in this acquired snapshot</small></span></li><li><b>02</b><span><strong>Release, obligation and payment</strong><small>Not available in the acquired records</small></span></li><li><b>03</b><span><strong>Receipt and audit evidence</strong><small>Not available in the acquired records</small></span></li><li><b>04</b><span><strong>Verified output and public outcome</strong><small>Not available in the acquired records</small></span></li></ol>
</section>`;

const empty = (message) => `<p class="evidence-empty">${html(message)}</p>`;

const relatedBudgets = (records) => records.length ? `<ul class="evidence-record-list">${records.map((item) => `
  <li><div><span>FY ${item.fiscal_year}</span><strong>${html(item.description)}</strong></div><b>${html(money(item.amount_centavos))}</b><a href="${idPath('budget', item.record_id)}">Open record</a></li>`).join('')}</ul>` : empty('No related appropriation records were found under the same normalized family identity.');

const relatedDeliveries = (records) => records.length ? `<ul class="evidence-record-list">${records.map((item) => `
  <li><div><span>FY ${item.fiscal_year} · ${html(item.contract_id)}</span><strong>${html(item.description)}</strong><small>${html(item.location)}</small></div><b>${html(money(item.budget_centavos))}</b><a href="${idPath('delivery', item.contract_id)}">Open record</a></li>`).join('')}</ul>` : empty('No related delivery records were found under the same normalized family identity.');

const signals = (records) => records.length ? `<ul class="evidence-signal-list">${records.map((item) => `
  <li><span>${html(item.classification.replaceAll('_', ' '))}</span><strong>${html(item.label)}</strong><p>${html(item.evidence || item.description)}</p>${item.signal_id ? `<a href="${idPath('integrity', item.signal_id)}">Inspect signal</a>` : ''}</li>`).join('')}</ul>` : empty('No published deterministic integrity signal is associated with this record.');

const coordinates = (record) => {
  if (!record?.latitude || !record?.longitude) return 'Not available in the source record';
  return `${record.latitude}, ${record.longitude}`;
};

const projectDetails = (record) => `<dl class="evidence-details evidence-details-wide">
  <div><dt>Category</dt><dd>${html(record?.category || 'Not stated')}</dd></div>
  <div><dt>Source status</dt><dd>${html(record?.status || 'Not stated')}</dd></div>
  <div><dt>Reported progress</dt><dd>${record?.progress ? `${html(record.progress)}%` : 'Not stated'}</dd></div>
  <div><dt>Start date</dt><dd>${html(record?.start_date || 'Not stated')}</dd></div>
  <div><dt>Completion date</dt><dd>${html(record?.completion_date || 'Not stated')}</dd></div>
  <div><dt>Coordinates</dt><dd>${html(coordinates(record))}</dd></div>
  <div><dt>Satellite image field</dt><dd>${record?.has_satellite_image === 1 ? 'Present in source record' : 'Not present in source record'}</dd></div>
  <div><dt>Recorded contractor</dt><dd>${html(record?.contractor_name || 'Not stated')}</dd></div>
</dl>`;

const contractorCards = (items) => items.length ? `<div class="contractor-card-grid">${items.map((item) => {
  const profile = item.profile;
  return `<article><span>${item.pcab_id ? `PCAB ${html(item.pcab_id)}` : 'No PCAB ID stated'}</span><h3>${html(item.contractor_name)}</h3>${profile ? `<p>${profile.project_count} archived project associations · ${html(money(profile.total_budget_centavos))}</p><a href="${contractorPath(profile.contractor_key)}">Open contractor activity</a>` : '<p>No exact contractor aggregate is available.</p>'}</article>`;
}).join('')}</div>` : empty('No contractor identity is stated in the acquired project-detail record.');

const matchStateLabel = (state) => ({
  structured_exact: 'Exact structured identifier',
  title_exact: 'Exact title identifier',
  multiple_exact_rows: 'Multiple exact source rows',
  conflict_review: 'Conflicting exact identifiers',
  no_exact_row: 'No exact secondary row located',
  invalid_identifier: 'Invalid contract identifier',
}[state] || state.replaceAll('_', ' '));

const awardMatchCards = (items) => items.length ? `<div class="contractor-card-grid">${items.map((item) => `
  <article><span>${html(item.match_basis.replaceAll('_', ' '))}</span>
    <h3>${html(item.notice_title || item.award_title || item.contract_id)}</h3>
    <p>${html(item.awardee_name)} · ${html(item.organization_name || 'Organization not stated')}</p>
    <dl class="evidence-details"><div><dt>Contract amount</dt><dd>${html(money(item.contract_amount_centavos))}</dd></div>
    <div><dt>Award date</dt><dd>${html(item.award_date || 'Not stated')}</dd></div>
    <div><dt>Status</dt><dd>${html(item.award_status || 'Not stated')}</dd></div>
    <div><dt>Source row SHA-256</dt><dd>${hash(item.row_sha256)}</dd></div></dl>
  </article>`).join('')}</div>` : empty('No exact row for this contract was accepted from the archived secondary award mirror.');

const quarantineCards = (items) => items.length ? items.map((item) => `
  <article class="evidence-panel"><p class="kicker">Quarantined source row</p>
    <h3>${html(item.notice_title || 'Conflicting archived row')}</h3>
    <dl class="evidence-details"><div><dt>Reference ID</dt><dd>${html(item.reference_id || 'Not stated')}</dd></div>
    <div><dt>Contract number</dt><dd>${html(item.contract_no || 'Not stated')}</dd></div>
    <div><dt>Award title</dt><dd>${html(item.award_title || 'Not stated')}</dd></div>
    <div><dt>Row SHA-256</dt><dd>${hash(item.row_sha256)}</dd></div></dl>
    <p><strong>Candidate contracts:</strong></p><div class="contractor-card-grid">${item.candidates.map((candidate) => `
      <article><span>FY ${html(candidate.fiscal_year || 'unknown')}</span><h3>${html(candidate.contract_id)}</h3>
      <p>${html(candidate.description || 'Delivery record unavailable')}</p>
      <a href="${idPath('delivery', candidate.contract_id)}">Inspect candidate contract</a></article>`).join('')}</div>
  </article>`).join('') : '';

const acquisitionEvidence = (payload) => {
  if (!payload?.acquisition) return '';
  const { acquisition, award_matches: matches, quarantine, metadata } = payload;
  return `<section class="evidence-section" id="acquisition-evidence">
    <p class="kicker">Contract acquisition evidence</p><h2>${html(matchStateLabel(acquisition.match_state))}</h2>
    ${facts([
    ['Accepted secondary rows', acquisition.accepted_match_rows],
    ['Quarantined secondary rows', acquisition.quarantined_match_rows],
    ['Last reconciled', metadata.checked_on || 'Not stated'],
  ])}
    ${boundary('Each row in this archived mirror is secondary discovery evidence, not an official notice of award. A match does not prove payment, implementation, completion, or wrongdoing.')}
    ${awardMatchCards(matches)}${quarantineCards(quarantine)}
    <dl class="evidence-details"><div><dt>Archived mirror SHA-256</dt><dd>${hash(metadata.award_sha256)}</dd></div>
    <div><dt>Archived mirror revision</dt><dd>${hash(metadata.award_revision)}</dd></div>
    <div><dt>DPWH universe SHA-256</dt><dd>${hash(metadata.delivery_sha256)}</dd></div></dl>
    ${quarantine.length ? boundary('Conflicting identifiers remain quarantined. Quarantine requests documentary review and is not a finding of wrongdoing.') : ''}
  </section>`;
};

const projectAvailability = (delivery, procurementEvidence, auditEvidence) => {
  const procurementAvailable = Boolean(procurementEvidence?.records?.length);
  const awardAvailable = procurementEvidence?.records?.some((item) => (
    item.procurement_status.toLowerCase().includes('awarded')
      || item.events.some((event) => event.stage === 'notice_of_award' && event.date_kind === 'actual')
  ));
  const inspectionAvailable = procurementEvidence?.records?.some((item) => (
    item.events.some((event) => event.stage === 'inspection_acceptance' && event.date_kind === 'actual')
  ));
  const auditAvailable = Boolean(auditEvidence) && !['not_covered', 'agency_report_available', 'program_audit_available'].includes(auditEvidence.status);
  return `<section class="evidence-panel evidence-availability">
  <p class="kicker">Traceability</p><h2>Evidence by public-money stage</h2><ol>
    <li class="available"><b>01</b><span><strong>Appropriation</strong><small>Reviewed GAA source row available</small></span></li>
    <li class="${procurementAvailable ? 'available' : ''}"><b>02</b><span><strong>Procurement</strong><small>${procurementAvailable ? 'Exact contract evidence available' : 'No exact artifact located'}</small></span></li>
    <li class="${awardAvailable ? 'available' : ''}"><b>03</b><span><strong>Award</strong><small>${awardAvailable ? 'Award status or actual award date reported' : 'Not established by acquired evidence'}</small></span></li>
    <li class="${delivery ? 'available' : ''}"><b>04</b><span><strong>Implementation</strong><small>DPWH delivery record ${delivery ? 'available' : 'not acquired'}</small></span></li>
    <li class="${inspectionAvailable ? 'available' : ''}"><b>05</b><span><strong>Inspection and acceptance</strong><small>${inspectionAvailable ? 'Actual event date reported' : 'Not available in acquired procurement evidence'}</small></span></li>
    <li><b>06</b><span><strong>Release, obligation and payment</strong><small>Not available in the acquired records</small></span></li>
    <li class="${auditAvailable ? 'available' : ''}"><b>07</b><span><strong>COA project observation</strong><small>${auditAvailable ? 'Reviewed project match available' : 'No reviewed project-level match located'}</small></span></li>
  </ol></section>`;
};

const projectProvenance = (record, delivery, provenance) => `<section class="evidence-section" id="provenance"><p class="kicker">Provenance</p><h2>Identifiers and archived source fingerprints</h2><dl class="provenance-grid">
  <div><dt>Reviewed case</dt><dd>${html(record.case_id)}</dd></div><div><dt>Project family</dt><dd>${html(record.family_id)}</dd></div>
  <div><dt>Contract ID</dt><dd>${html(record.contract_id)}</dd></div><div><dt>Delivery snapshot as of</dt><dd>${html(provenance.source_as_of || 'Not stated')}</dd></div>
  <div><dt>Budget artifact SHA-256</dt><dd>${hash(provenance.budget_artifact_sha256 || '')}</dd></div><div><dt>Delivery artifact SHA-256</dt><dd>${hash(delivery?.detail_artifact_sha256 || provenance.delivery_artifact_sha256 || provenance.source_artifact_sha256 || '')}</dd></div>
  <div><dt>PCAB snapshot date</dt><dd>${html(provenance.pcab_retrieved_on || 'Not stated')}</dd></div><div><dt>District roster snapshot date</dt><dd>${html(provenance.district_source_retrieved_on || 'Not stated')}</dd></div>
</dl></section>`;

export const budgetRecordBody = ({ record, related, candidates, projects }) => `${breadcrumb('GAA appropriation', record.record_id)}
<article class="evidence-dossier">${heading({
  badge: 'Official GAA appropriation record', kicker: `FY ${record.fiscal_year} · ${record.budget_line_id}`,
  title: record.description, summary: record.family_label,
})}
${facts([['Appropriation', money(record.amount_centavos), 'Authority to spend, not proof of release or payment'], ['Fiscal year', record.fiscal_year], ['Snapshot fingerprint', record.artifact_sha256.slice(0, 16), 'Full digest shown below']])}
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Source identity</p><h2>Archived appropriation row</h2><dl class="evidence-details"><div><dt>Record ID</dt><dd>${html(record.record_id)}</dd></div><div><dt>Budget line ID</dt><dd>${html(record.budget_line_id)}</dd></div><div><dt>Normalized family</dt><dd>${html(record.project_family_id)}</dd></div><div><dt>Artifact SHA-256</dt><dd>${hash(record.artifact_sha256)}</dd></div></dl><a class="evidence-action" href="${html(gaaDocumentsUrl(record.fiscal_year))}" target="_blank" rel="noopener noreferrer">Open FY ${record.fiscal_year} GAA document index</a></section>${availability()}</div>
<section class="evidence-section"><p class="kicker">Related appropriation history</p><h2>Rows sharing this normalized family</h2>${relatedBudgets(related)}</section>
<section class="evidence-section"><p class="kicker">Cross-source review</p><h2>${candidates.length} candidate link${candidates.length === 1 ? '' : 's'}</h2>${candidates.length ? candidates.map((item) => `<a class="candidate-callout" href="${idPath('candidate', item.candidate_id)}"><strong>${html(item.delivery_description)}</strong><span>Unreviewed · evidence score ${item.score}</span></a>`).join('') : empty('No candidate delivery link is associated with this budget line and fiscal year.')}${projects.map((item) => `<a class="reviewed-callout" href="/projects/${html(item.slug)}/"><strong>${html(item.title)}</strong><span>${html(item.status_label)}</span></a>`).join('')}</section>
${boundary('This page reproduces an appropriation record and normalized relationships. It does not establish procurement, release, payment, construction, completion, benefit, or wrongdoing.')}</article>`;

export const deliveryRecordBody = ({ record, related, budgets, candidates, projects, signals: items, contractors, ...acquisition }) => `${breadcrumb('DPWH contract', record.contract_id)}
<article class="evidence-dossier">${heading({ badge: 'Official DPWH delivery record', kicker: `FY ${record.fiscal_year} · Contract ${record.contract_id}`, title: record.description, summary: record.location })}
${facts([['Recorded project budget', money(record.budget_centavos), 'Snapshot value, not proof of payment'], ['Status / progress', `${record.status || 'Not stated'} / ${record.progress ? `${record.progress}%` : 'Not stated'}`, 'Reported by the source record'], ['Integrity signals', items.length, 'Review leads, not findings']])}
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Project details</p><h2>Fields in the archived DPWH record</h2>${projectDetails(record)}<dl class="evidence-details"><div><dt>Source of funds</dt><dd>${html(record.source_of_funds || 'Not stated')}</dd></div><div><dt>Normalized family</dt><dd>${html(record.project_family_id)}</dd></div><div><dt>Artifact SHA-256</dt><dd>${hash(record.detail_artifact_sha256 || record.artifact_sha256)}</dd></div></dl></section>${district(record.district_context)}</div>
<section class="evidence-section"><p class="kicker">Contractor identities</p><h2>Parties stated in the project record</h2>${contractorCards(contractors)}</section>
<section class="evidence-section"><p class="kicker">Deterministic review</p><h2>Published source-record signals</h2>${signals(items)}</section>
<section class="evidence-section"><p class="kicker">Possible appropriation records</p><h2>Same normalized family</h2>${relatedBudgets(budgets)}${candidates.map((item) => `<a class="candidate-callout" href="${idPath('candidate', item.candidate_id)}"><strong>Compare candidate appropriation and delivery rows</strong><span>Unreviewed · evidence score ${item.score}</span></a>`).join('')}${projects.map((item) => `<a class="reviewed-callout" href="/projects/${html(item.slug)}/"><strong>${html(item.title)}</strong><span>${html(item.status_label)}</span></a>`).join('')}</section>
<section class="evidence-section"><p class="kicker">Related delivery history</p><h2>Other records sharing the family identity</h2>${relatedDeliveries(related)}</section>${availability()}
${acquisitionEvidence(acquisition)}
${boundary('A DPWH delivery record is not by itself proof that work exists at the stated location, that payment occurred, that completion is accurate, or that the project produced public value.')}</article>`;

export const candidateRecordBody = ({ record, budgets, delivery, projects }) => `${breadcrumb('Candidate comparison', record.candidate_id)}
<article class="evidence-dossier">${heading({ badge: 'Unreviewed candidate comparison', tone: 'candidate', kicker: `FY ${record.fiscal_year} · Evidence score ${record.score}`, title: record.budget_description, summary: 'Two separate source records placed side by side for documentary review.' })}
${boundary('Similarity is not identity. This candidate has not passed the reviewed-link publication gate and must not be cited as a confirmed project relationship.')}
<div class="comparison-grid"><section class="evidence-panel"><p class="kicker">Appropriation side</p><h2>${html(record.budget_description)}</h2><strong class="large-money">${html(money(record.budget_amount_centavos))}</strong>${budgets.map((item) => `<a class="evidence-action" href="${idPath('budget', item.record_id)}">Open appropriation record</a>`).join('')}</section><section class="evidence-panel"><p class="kicker">Delivery side</p><h2>${html(record.delivery_description)}</h2><strong class="large-money">${html(money(record.delivery_budget_centavos))}</strong>${delivery ? `<a class="evidence-action" href="${idPath('delivery', delivery.contract_id)}">Open delivery record</a>` : '<p>Matching delivery row is not available.</p>'}</section></div>
${facts([['Recorded difference', money(record.difference_centavos), 'Comparison only'], ['Confidence label', record.confidence], ['Review status', record.review_status]])}
<section class="evidence-panel"><p class="kicker">Why the rule proposed this pair</p><h2>Explainable matching signals</h2><ul class="evidence-list">${record.signals.map((item) => `<li><strong>${html(item.replaceAll('_', ' '))}</strong></li>`).join('')}</ul>${projects.map((item) => `<a class="reviewed-callout" href="/projects/${html(item.slug)}/"><strong>${html(item.title)}</strong><span>${html(item.status_label)}</span></a>`).join('')}</section></article>`;

export const changeRecordBody = ({ record, related, prior }) => `${breadcrumb('FY2027 comparison', record.record_id)}
<article class="evidence-dossier">${heading({ badge: 'Provisional stage comparison', tone: 'candidate', kicker: `${record.dataset.toUpperCase()} · ${record.change_label}`, title: record.title, summary: [record.program, record.region, record.office].filter(Boolean).join(' · ') })}
${facts([['NEP', money(record.nep_centavos)], ['House bill', money(record.house_centavos)], ['Recorded movement', money(record.difference_centavos), 'Arithmetic comparison, not proof of an insertion']])}
${boundary('This row compares acquired proposal and House bill evidence. It does not identify an author, sponsor, motive, release, payment, or final enacted amount.')}
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Document evidence</p><h2>Inspect the compared pages</h2>${safeLink(record.nep_pdf_url) ? `<a class="evidence-action" href="${html(safeLink(record.nep_pdf_url))}" target="_blank" rel="noopener noreferrer">Open NEP PDF${record.nep_page ? ` · page ${record.nep_page}` : ''}</a>` : '<p>NEP page not available for this row.</p>'}${safeLink(record.house_pdf_url) ? `<a class="evidence-action" href="${html(safeLink(record.house_pdf_url))}" target="_blank" rel="noopener noreferrer">Open House bill PDF${record.house_page ? ` · page ${record.house_page}` : ''}</a>` : '<p>House page not available for this row.</p>'}<dl class="evidence-details"><div><dt>Review status</dt><dd>${html(record.review_status)}</dd></div><div><dt>Confidence</dt><dd>${html(record.confidence)}</dd></div><div><dt>Artifact SHA-256</dt><dd>${hash(record.artifact_sha256)}</dd></div></dl></section>${district(record.district_context)}</div>
<section class="evidence-section"><p class="kicker">Prior-year context</p><h2>Appropriations sharing the normalized family label</h2>${relatedBudgets(prior)}</section>
<section class="evidence-section"><p class="kicker">FY2027 related rows</p><h2>Other rows in the same normalized family</h2>${related.length ? related.map((item) => `<a class="candidate-callout" href="${idPath('change', item.record_id)}"><strong>${html(item.title)}</strong><span>${html(item.change_type.replaceAll('_', ' '))} · ${html(money(item.difference_centavos))}</span></a>`).join('') : empty('No other FY2027 comparison row shares this family label.')}</section></article>`;

export const integrityRecordBody = ({ record, delivery, contractor, related }) => `${breadcrumb('Integrity review signal', record.signal_id)}
<article class="evidence-dossier">${heading({ badge: 'Review signal, not a finding', tone: 'signal', kicker: `${record.classification.replaceAll('_', ' ')} · Contract ${record.contract_id}`, title: record.label, summary: record.description })}
${boundary('This deterministic rule identifies a source-record pattern for verification. It does not prove fraud, corruption, a ghost project, non-performance, or wrongdoing.')}
${facts([['Recorded project budget', money(record.budget_centavos)], ['Status / progress', `${record.status || 'Not stated'} / ${record.progress || 'Not stated'}%`], ['Location', [record.province, record.region].filter(Boolean).join(', ') || 'Not stated']])}
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Rule evidence</p><h2>Why this record was surfaced</h2><p>${html(record.evidence)}</p><p class="evidence-limit"><strong>Known limit:</strong> ${html(record.limitations)}</p><dl class="evidence-details"><div><dt>Rule code</dt><dd>${html(record.code)}</dd></div><div><dt>Snapshot fingerprint</dt><dd>${hash(record.source_artifact_sha256)}</dd></div></dl>${delivery ? `<a class="evidence-action" href="${idPath('delivery', delivery.contract_id)}">Open underlying delivery record</a>` : ''}</section>${district(record.district_context)}</div>
${contractor ? `<section class="evidence-panel"><p class="kicker">Recorded contractor identity</p><h2>${html(contractor.contractor_name)}</h2><p>${contractor.project_count} archived project associations · ${html(money(contractor.total_budget_centavos))}</p><a class="evidence-action" href="${contractorPath(contractor.contractor_key)}">Open contractor activity</a></section>` : ''}
<section class="evidence-section"><p class="kicker">Other rules on this contract</p><h2>${related.length} additional signal${related.length === 1 ? '' : 's'}</h2>${signals(related)}</section></article>`;

export const contractorRecordBody = ({ record, signals: items, concentrations }) => `${breadcrumb('Contractor activity', record.contractor_key)}
<article class="evidence-dossier">${heading({ badge: 'Archived contractor activity', kicker: record.pcab_id ? `Recorded PCAB ID ${record.pcab_id}` : 'No PCAB ID in source identity', title: record.contractor_name, summary: `Project associations in the acquired DPWH snapshot, FY ${record.first_year} to FY ${record.last_year}.` })}
${facts([['Project associations', record.project_count, 'Associations, not necessarily unique completed works'], ['Associated project budget', money(record.total_budget_centavos), 'Not revenue, payment, or contract value received'], ['Joint-project associations', record.joint_project_count]])}
${boundary('These counts describe archived project-record associations. They do not prove beneficial ownership, payment, performance quality, political connection, market misconduct, or wrongdoing.')}
<div class="evidence-columns"><section class="evidence-panel"><p class="kicker">Recorded status mix</p><h2>Projects by source status</h2>${facts([['Completed', record.completed_count], ['Ongoing', record.ongoing_count], ['Terminated', record.terminated_count]])}</section><section class="evidence-panel"><p class="kicker">PCAB verification snapshot</p><h2>${html(record.pcab_status.replaceAll('_', ' '))}</h2><dl class="evidence-details"><div><dt>Listed name</dt><dd>${html(record.pcab_name || 'Not available')}</dd></div><div><dt>Category</dt><dd>${html(record.pcab_category || 'Not available')}</dd></div><div><dt>Valid to</dt><dd>${html(record.pcab_valid_to || 'Not available')}</dd></div></dl>${record.pcab_id ? `<a class="evidence-action" href="${html(record.pcab_url)}" target="_blank" rel="noopener noreferrer">Verify in the current PCAB table</a>` : ''}</section></div>
<section class="evidence-section"><p class="kicker">Review leads</p><h2>Signals associated with this contractor identity</h2>${signals(items)}</section>
<section class="evidence-section"><p class="kicker">Concentration context</p><h2>Groups where this was the leading recorded party</h2>${concentrations.length ? concentrations.map((item) => `<div class="candidate-callout"><strong>${html(item.group_label)}</strong><span>${(Number(item.top_share_basis_points) / 100).toFixed(1)}% of contractor-party associations · FY ${item.fiscal_year || 'all years'}</span></div>`).join('') : empty('No published concentration group lists this contractor as the leading recorded party.')}</section></article>`;

const auditEvidencePanel = (evidence) => {
  if (!evidence) return `<section class="evidence-section" id="audit-evidence"><p class="kicker">COA audit evidence</p><h2>Coverage review not yet recorded</h2><p class="evidence-empty">This dossier has not yet passed the separate COA catalogue review.</p><a class="evidence-action" href="/audit/">Open the COA audit evidence desk</a></section>`;
  if (evidence.status === 'not_covered') return `<section class="evidence-section" id="audit-evidence"><p class="kicker">COA audit evidence</p><h2>No qualifying project-level COA evidence located</h2><p>${html(evidence.review_note)}</p><dl class="evidence-details"><div><dt>Coverage status</dt><dd>Not covered by a located project-level report</dd></div><div><dt>Last reviewed</dt><dd>${html(evidence.reviewed_at)}</dd></div></dl><p class="evidence-limit">Absence is not clearance. It does not mean COA audited, approved, or cleared this project.</p><a class="evidence-action" href="/audit/">Open the COA audit evidence desk</a></section>`;
  const pages = evidence.page_start ? `pages ${evidence.page_start}–${evidence.page_end}` : 'No cited page range';
  const label = evidence.status === 'reviewed_observation_match'
    ? 'Reviewed project observation match'
    : evidence.status.replaceAll('_', ' ');
  return `<section class="evidence-section" id="audit-evidence"><p class="kicker">COA audit evidence</p><h2>${html(label)}</h2><p>${html(evidence.observation_summary || evidence.review_note)}</p><dl class="evidence-details"><div><dt>Report</dt><dd>${html(evidence.report_title)}</dd></div><div><dt>Citation</dt><dd>${html(pages)}</dd></div><div><dt>Match confidence</dt><dd>${html(evidence.match_confidence)}</dd></div><div><dt>Implementation status</dt><dd>${html(evidence.implementation_status.replaceAll('_', ' '))}</dd></div></dl>${evidence.recommendation_summary ? `<h3>COA recommendation</h3><p>${html(evidence.recommendation_summary)}</p>` : ''}${evidence.management_response ? `<h3>Management response</h3><p>${html(evidence.management_response)}</p>` : ''}<a class="evidence-action" href="/audit/reports/${encodeURIComponent(evidence.report_id)}/">Read the audit evidence record</a><p class="evidence-limit">An audit observation is not automatically a disallowance, criminal finding, or proof of wrongdoing.</p></section>`;
};

const procurementStageLabel = (stage) => ({
  pre_procurement_conference: 'Pre-procurement conference',
  advertisement: 'Advertisement or posting',
  pre_bid: 'Pre-bid conference',
  eligibility_check: 'Eligibility check',
  bid_opening: 'Bid opening',
  bid_evaluation: 'Bid evaluation',
  post_qualification: 'Post qualification',
  bac_resolution: 'BAC award resolution',
  notice_of_award: 'Notice of award',
  contract_signing: 'Contract signing',
  notice_to_proceed: 'Notice to proceed',
  delivery_completion: 'Delivery or completion',
  inspection_acceptance: 'Inspection and acceptance',
}[stage] || stage.replaceAll('_', ' '));

const procurementRecordCard = (item) => {
  const source = safeLink(item.source_url);
  const amounts = [
    item.abc_centavos === null ? null : `<div><dt>Approved budget</dt><dd>${html(money(item.abc_centavos))}</dd></div>`,
    item.contract_cost_centavos === null ? null : `<div><dt>Contract cost</dt><dd>${html(money(item.contract_cost_centavos))}</dd></div>`,
    item.savings_centavos === null ? null : `<div><dt>Difference below ABC</dt><dd>${html(money(item.savings_centavos))}</dd></div>`,
  ].filter(Boolean).join('');
  const events = item.events.length ? `<ol class="procurement-timeline">${item.events.map((event) => `<li class="${html(event.date_kind)}"><span>${html(event.event_date)}</span><strong>${html(procurementStageLabel(event.stage))}</strong><small>${html(event.date_kind)}</small></li>`).join('')}</ol>` : empty('No event dates are stated in this evidence record.');
  const sourceState = item.acquisition_status === 'verified_archived'
    ? `<div><dt>Archived source SHA-256</dt><dd>${hash(item.artifact_sha256)}</dd></div>`
    : '<div><dt>Archive status</dt><dd>Official source discovered, original bytes not acquired</dd></div>';
  return `<article class="procurement-record"><header><span>${html(item.evidence_type.replaceAll('_', ' '))}</span><b>${html(item.procurement_status)}</b></header><h3>${html(item.source_title)}</h3><p>${html(item.procuring_entity)} · ${html(item.procurement_mode)}</p><dl class="evidence-details">${amounts}<div><dt>Contract match</dt><dd>${html(item.match_basis.replaceAll('_', ' '))}</dd></div>${item.page_number ? `<div><dt>Source citation</dt><dd>Page ${item.page_number}</dd></div>` : ''}${item.reference_number ? `<div><dt>Reference number</dt><dd>${html(item.reference_number)}</dd></div>` : ''}${sourceState}</dl>${events}${item.observers.length ? `<p class="evidence-limit"><strong>Invited observers stated:</strong> ${html(item.observers.join(', '))}</p>` : ''}${source ? `<a class="evidence-action" href="${html(source)}" target="_blank" rel="noopener noreferrer">Open official procurement document</a>` : ''}<p class="evidence-limit">${html(item.boundary_note)}</p></article>`;
};

const procurementEvidencePanel = (evidence) => {
  if (!evidence) return `<section class="evidence-section" id="procurement-evidence"><p class="kicker">Procurement timeline</p><h2>Coverage review not yet recorded</h2><p class="evidence-empty">This dossier has not passed the separate procurement evidence review.</p><a class="evidence-action" href="/procurement/">Open the procurement evidence desk</a></section>`;
  if (!evidence.records.length) return `<section class="evidence-section" id="procurement-evidence"><p class="kicker">Procurement timeline</p><h2>No exact official procurement artifact located</h2><p>${html(evidence.coverage.review_note)}</p><dl class="evidence-details"><div><dt>Coverage status</dt><dd>${html(evidence.coverage.status.replaceAll('_', ' '))}</dd></div><div><dt>Last reviewed</dt><dd>${html(evidence.coverage.reviewed_at)}</dd></div></dl><p class="evidence-limit">Missing evidence is not evidence that procurement did not occur.</p><a class="evidence-action" href="/procurement/">Open the procurement evidence desk</a></section>`;
  return `<section class="evidence-section" id="procurement-evidence"><p class="kicker">Procurement timeline</p><h2>${evidence.records.length} exact official evidence record${evidence.records.length === 1 ? '' : 's'}</h2><p>${html(evidence.coverage.review_note)}</p><div class="procurement-records">${evidence.records.map(procurementRecordCard).join('')}</div><a class="evidence-action" href="/procurement/">Open the procurement evidence desk</a></section>`;
};

const outcomeState = (category, item) => `<div><dt>${html(category)}</dt><dd><strong>${html(item.label)}</strong><br>${html(item.detail)}</dd></div>`;

const contractOutcomePanel = (outcome) => {
  if (!outcome) return `<section class="evidence-section" id="contract-outcome"><p class="kicker">Contract outcome pack</p><h2>No cross-source outcome review available</h2><p class="evidence-empty">Comparable procurement and delivery evidence has not been acquired for this dossier.</p></section>`;
  const amount = outcome.amount_check;
  const amountRows = amount.procurement_centavos === null
    ? `<div><dt>Amount cross-check</dt><dd>${html(amount.label)}</dd></div>`
    : `<div><dt>${html(amount.source_label || 'Procurement contract amount')}</dt><dd>${html(money(amount.procurement_centavos))}</dd></div><div><dt>DPWH delivery value</dt><dd>${html(money(amount.delivery_centavos))}</dd></div><div><dt>Recorded difference</dt><dd>${html(money(amount.difference_centavos))}</dd></div>`;
  const questions = outcome.questions.length
    ? `<ul class="outcome-questions">${outcome.questions.map((item) => `<li><span>${html(item.severity.replaceAll('_', ' '))}</span><strong>${html(item.label)}</strong><p>${html(item.detail)}</p></li>`).join('')}</ul>`
    : empty('No deterministic cross-source question was produced from the acquired fields.');
  const mirror = outcome.award_mirror;
  const mirrorUrl = safeLink(mirror?.dataset_url);
  const mirrorEvidence = mirror ? `<section class="outcome-mirror"><p class="kicker">Secondary award mirror</p><h3>${html(mirror.awardee_name)}</h3><dl class="evidence-details"><div><dt>Mirror award amount</dt><dd>${html(money(mirror.contract_amount_centavos))}</dd></div><div><dt>Award date</dt><dd>${html(mirror.award_date)}</dd></div><div><dt>Source row</dt><dd>${html(mirror.source_row_id)}</dd></div><div><dt>Row SHA-256</dt><dd>${hash(mirror.row_sha256)}</dd></div><div><dt>Dataset revision</dt><dd>${hash(mirror.source_revision)}</dd></div><div><dt>Acquisition boundary</dt><dd>Complete mirror snapshot archived; original official award page not archived</dd></div></dl>${mirrorUrl ? `<a class="evidence-action" href="${html(mirrorUrl)}" target="_blank" rel="noopener noreferrer">Open versioned mirror dataset</a>` : ''}</section>` : '';
  return `<section class="evidence-section" id="contract-outcome"><p class="kicker">Contract outcome pack</p><h2>What the acquired records establish, conflict on, and leave unanswered</h2><div class="outcome-summary"><article><span>Delivery record contractor</span><strong>${html(outcome.contractor_name || 'Not stated')}</strong><p>This is not presented as an independently verified awardee.</p></article><article><span>Delivery status</span><strong>${html(outcome.delivery_status || 'Not stated')}</strong><p>${outcome.delivery_progress ? `${html(outcome.delivery_progress)}% reported progress` : 'Progress not stated'}</p></article><article><span>Recorded period</span><strong>${html(outcome.start_date || 'Not stated')}</strong><p>Completion: ${html(outcome.completion_date || 'Not stated')}</p></article></div><dl class="evidence-details outcome-evidence">${amountRows}${outcomeState('Award evidence', outcome.award_evidence)}${outcomeState('Awardee evidence', outcome.awardee_evidence)}${outcomeState('Awardee name cross-check', outcome.awardee_check)}${outcomeState('Inspection evidence', outcome.inspection_evidence)}${outcomeState('Payment evidence', outcome.payment_evidence)}</dl>${mirrorEvidence}<h3>Questions for documentary review</h3>${questions}<p class="evidence-limit">These checks compare acquired official records and explicitly labelled secondary mirror rows. They are review leads, not findings of wrongdoing, non-delivery, or improper payment.</p></section>`;
};

export const enhancedProjectBody = ({
  record, delivery, signals: items, related, budgets, deliveries, contractors,
  candidates, changes, provenance, auditEvidence, procurementEvidence, contractEvidence,
  contractOutcome,
}) => `${breadcrumb('Reviewed dossier', record.contract_id)}
<article class="evidence-dossier">${heading({ badge: record.is_quarantined ? 'Quarantined project candidate' : 'Reviewed project evidence dossier', tone: record.is_quarantined ? 'candidate' : 'reviewed', kicker: `FY ${record.fiscal_year} · ${record.contract_id}`, title: record.title, summary: record.location })}
${record.is_quarantined ? boundary('This relationship remains quarantined and is not a confirmed cross-source link.') : ''}
${facts([['GAA appropriation', money(record.appropriation_centavos), 'Authority to spend'], ['DPWH project budget', money(record.contract_budget_centavos), 'Archived snapshot value'], ['Recorded difference', money(record.variance_centavos), 'Comparison only']])}
<nav class="dossier-index" aria-label="Dossier sections"><span>Jump to</span><a href="#project-record">Project record</a><a href="#link-evidence">Link evidence</a><a href="#procurement-evidence">Procurement</a><a href="#contract-evidence">Evidence status</a><a href="#contract-outcome">Outcome cross-check</a><a href="#contractors">Contractors</a><a href="#audit-evidence">COA audit</a><a href="#phases">Related phases</a><a href="#source-records">Source records</a><a href="#provenance">Provenance</a></nav>
<section class="project-status-band"><div><span>Source status</span><strong>${html(delivery?.status || 'Not stated')}</strong></div><div><span>Reported progress</span><strong>${delivery?.progress ? `${html(delivery.progress)}%` : 'Not stated'}</strong></div><div><span>Recorded period</span><strong>${html(delivery?.start_date || 'Not stated')} to ${html(delivery?.completion_date || 'Not stated')}</strong></div><div><span>Category</span><strong>${html(delivery?.category || 'Not stated')}</strong></div></section>
<div class="evidence-columns" id="project-record"><section class="evidence-panel"><p class="kicker">DPWH project record</p><h2>Recorded implementation details</h2>${projectDetails(delivery)}${delivery ? `<a class="evidence-action" href="${idPath('delivery', delivery.contract_id)}">Open complete delivery record</a>` : ''}</section>${delivery ? district(delivery.district_context) : district(null)}</div>
<div class="evidence-columns" id="link-evidence"><section class="evidence-panel"><p class="kicker">Reviewed relationship</p><h2>Why the appropriation and delivery records may relate</h2><ul class="evidence-list">${record.match_signals.map((item) => `<li><strong>${html(item.replaceAll('_', ' '))}</strong></li>`).join('')}</ul><p class="evidence-limit">${html(record.match_limitations)}</p><dl class="evidence-details"><div><dt>Confidence</dt><dd>${html(record.confidence)} · score ${record.confidence_score}</dd></div><div><dt>Publication status</dt><dd>${html(record.status_label)}</dd></div></dl></section>${projectAvailability(delivery, procurementEvidence, auditEvidence)}</div>
${procurementEvidencePanel(procurementEvidence)}
${contractEvidencePanel(contractEvidence)}
${contractOutcomePanel(contractOutcome)}
<section class="evidence-section" id="contractors"><p class="kicker">Contractor identities</p><h2>Parties stated in the DPWH record</h2>${contractorCards(contractors)}</section>
<section class="evidence-section"><p class="kicker">Integrity review</p><h2>Deterministic signals on this contract</h2>${signals(items)}</section>
${auditEvidencePanel(auditEvidence)}
<section class="evidence-section" id="phases"><p class="kicker">Related reviewed phases</p><h2>Other dossiers sharing the reviewed family identity</h2>${related.length ? related.map((item) => `<a class="reviewed-callout" href="/projects/${html(item.slug)}/"><strong>FY ${item.fiscal_year} · ${html(item.title)}</strong><span>${html(item.contract_id)} · ${html(item.status_label)}</span></a>`).join('') : empty('No other reviewed dossier shares this exact family identity.')}</section>
<section class="evidence-section"><p class="kicker">Possible later budget records</p><h2>FY2027 rows sharing the normalized family label</h2>${changes.length ? changes.map((item) => `<a class="candidate-callout" href="${idPath('change', item.record_id)}"><strong>${html(item.title)}</strong><span>${html(item.change_label)} · ${html(money(item.difference_centavos))}</span></a>`).join('') : empty('No FY2027 stage-comparison row shares this normalized family label.')}<p class="evidence-limit">Family-label similarity is review context only. It does not confirm that a later proposal funds the same phase or contract.</p></section>
<section class="evidence-section"><p class="kicker">Cross-source candidates</p><h2>Other automated comparisons involving this contract</h2>${candidates.length ? candidates.map((item) => `<a class="candidate-callout" href="${idPath('candidate', item.candidate_id)}"><strong>${html(item.budget_description)}</strong><span>Unreviewed · score ${item.score} · ${html(money(item.difference_centavos))} difference</span></a>`).join('') : empty('No additional unreviewed comparison involves this contract.')}</section>
<section class="evidence-section" id="source-records"><p class="kicker">Source-family evidence</p><h2>Appropriation records</h2>${relatedBudgets(budgets)}<h2>Delivery records</h2>${relatedDeliveries(deliveries)}</section>
<section class="evidence-panel"><p class="kicker">Reader evidence links</p><h2>Open the records behind this dossier</h2>${budgets.map((item) => `<a class="evidence-action" href="${idPath('budget', item.record_id)}">FY ${item.fiscal_year} appropriation · ${html(item.description)}</a>`).join('')}${delivery ? `<a class="evidence-action" href="${idPath('delivery', delivery.contract_id)}">DPWH delivery record · ${html(delivery.contract_id)}</a>` : ''}<a class="evidence-action" href="${html(gaaDocumentsUrl(record.fiscal_year))}" target="_blank" rel="noopener noreferrer">FY ${record.fiscal_year} GAA document index</a></section>
${projectProvenance(record, delivery, provenance)}
${boundary('A reviewed cross-source link means the records passed Busisi’s identity-review gate. It does not prove release, payment, physical completion, quality, public benefit, or wrongdoing.')}</article>`;
