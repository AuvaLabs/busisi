import { renderDistrictContext } from './district-context-v1.js';

const integrityRoot = document.querySelector('[data-integrity-desk]');
const contractorRoot = document.querySelector('[data-contractor-desk]');
const concentrationRoot = document.querySelector('[data-concentration-desk]');

const integrityForm = integrityRoot.querySelector('[data-integrity-form]');
const integrityResults = integrityRoot.querySelector('[data-integrity-results]');
const integrityStatus = integrityRoot.querySelector('[data-integrity-status]');
const integrityCount = integrityRoot.querySelector('[data-integrity-count]');
const integrityTotal = integrityRoot.querySelector('[data-integrity-total]');
const integrityMore = integrityRoot.querySelector('[data-integrity-more]');
const integrityExport = integrityRoot.querySelector('[data-integrity-export]');
const integritySummary = document.querySelector('[data-integrity-summary]');

const contractorForm = contractorRoot.querySelector('[data-contractor-form]');
const contractorResults = contractorRoot.querySelector('[data-contractor-results]');
const contractorStatus = contractorRoot.querySelector('[data-contractor-status]');
const contractorCount = contractorRoot.querySelector('[data-contractor-count]');
const contractorTotal = contractorRoot.querySelector('[data-contractor-total]');
const contractorMore = contractorRoot.querySelector('[data-contractor-more]');
const concentrationForm = concentrationRoot.querySelector('[data-concentration-form]');
const concentrationResults = concentrationRoot.querySelector('[data-concentration-results]');
const concentrationStatus = concentrationRoot.querySelector('[data-concentration-status]');

const number = new Intl.NumberFormat('en-PH');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
let integrityCursor = null;
let contractorCursor = null;
let integrityController = null;
let contractorController = null;

const signalLabels = Object.freeze({
  status_progress_conflict: 'Ongoing at 100% progress',
  completed_progress_conflict: 'Completed below 100%',
  date_order_conflict: 'Date order conflict',
  nonpositive_active_budget: 'Nonpositive active budget',
  missing_coordinate: 'Coordinate not available',
  coordinate_outside_philippines: 'Coordinate outside broad bounds',
  completed_without_satellite_image: 'Completed without satellite image',
  reused_coordinate: 'Coordinate reused across projects',
  coordinate_location_conflict: 'Coordinate and location conflict',
  past_completion_not_complete: 'Completion date passed without completed status',
  same_site_repeat_family: 'Same site and project family across fiscal years',
});

const classificationLabels = Object.freeze({
  source_conflict: 'The record disagrees with itself',
  amount_review: 'The amount needs checking',
  identity_review: 'The project identity needs checking',
  coverage_gap: 'We do not have enough information yet',
});

const appendText = (parent, tag, value, className) => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const appendLink = (parent, label, href) => {
  if (!href) return;
  const link = appendText(parent, 'a', label);
  link.href = href;
  if (href.startsWith('http')) {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  }
};

const formatMoney = (centavos) => peso.format(Number(centavos || 0) / 100);
const displayValue = (value, fallback = 'Not stated') => value ? String(value) : fallback;
const percent = (basisPoints) => `${(Number(basisPoints || 0) / 100).toFixed(1)}%`;

const pcabStatusLabels = Object.freeze({
  current_regular: 'In current PCAB regular-license table',
  current_not_government_infra: 'Current regular license, not marked for government infrastructure',
  expired_regular: 'Expired in current regular-license table',
  not_found_current_regular: 'Not found in current regular-license table',
  not_checked: 'No PCAB number available to check',
});

const integrityParams = () => {
  const values = new FormData(integrityForm);
  const params = new URLSearchParams({
    signal: String(values.get('signal')),
    classification: String(values.get('classification')),
    sort: String(values.get('sort')),
    limit: '20',
  });
  const q = String(values.get('q')).trim();
  const year = String(values.get('year')).trim();
  if (q) params.set('q', q);
  if (year) params.set('year', year);
  return params;
};

const contractorParams = () => {
  const values = new FormData(contractorForm);
  const params = new URLSearchParams({
    sort: String(values.get('sort')),
    limit: '20',
  });
  const q = String(values.get('q')).trim();
  if (q) params.set('q', q);
  return params;
};

const syncIntegrityUrl = () => {
  const current = new URLSearchParams(location.search);
  for (const name of ['q', 'signal', 'classification', 'year', 'sort']) current.delete(name);
  for (const [name, value] of integrityParams()) current.set(name, value);
  history.replaceState(null, '', `${location.pathname}?${current}`);
};

const syncContractorUrl = () => {
  const current = new URLSearchParams(location.search);
  const values = new FormData(contractorForm);
  const query = String(values.get('q') || '').trim();
  const sort = String(values.get('sort') || 'count_desc');
  if (query) current.set('contractor_q', query);
  else current.delete('contractor_q');
  if (sort !== 'count_desc') current.set('contractor_sort', sort);
  else current.delete('contractor_sort');
  history.replaceState(null, '', `${location.pathname}?${current}`);
};

const renderSummary = (payload) => {
  const coordinateSignals = payload.signals
    .filter((item) => item.code.includes('coordinate'))
    .reduce((total, item) => total + item.count, 0);
  const cards = [
    [number.format(payload.source_records), 'source records examined', 'Archived FY2024 to FY2026 DPWH snapshot'],
    [number.format(payload.integrity_signals), 'things to check', 'One contract can have more than one question'],
    [number.format(coordinateSignals), 'place questions', 'Missing, unusual, repeated, or mismatched coordinates'],
    [number.format(payload.contractors), 'contractor identities', 'Explicit slash-delimited joint ventures are split by party'],
    [number.format(payload.district_count), 'legislative districts in roster', `${number.format(payload.district_offices)} mapped DPWH offices · snapshot ${payload.district_source_retrieved_on}`],
  ];
  integritySummary.replaceChildren(...cards.map(([value, label, note]) => {
    const card = document.createElement('article');
    appendText(card, 'strong', value);
    appendText(card, 'span', label);
    appendText(card, 'small', note);
    return card;
  }));
};

const renderIntegrityRecord = (record) => {
  const copy = record.plain_language || {};
  const card = document.createElement('article');
  card.className = 'integrity-record';
  const heading = document.createElement('header');
  appendText(heading, 'span', copy.label || signalLabels[record.code] || record.label, 'integrity-badge');
  appendText(
    heading,
    'span',
    copy.category || classificationLabels[record.classification] || record.classification,
    'integrity-badge classification',
  );
  card.append(heading);
  const title = appendText(card, 'h3', '');
  const titleLink = appendText(title, 'a', record.description, 'record-title-link');
  titleLink.href = `/records/integrity/${encodeURIComponent(record.signal_id)}/`;
  appendText(
    card,
    'p',
    [`FY ${record.fiscal_year}`, record.contract_id, record.contractor_name].filter(Boolean).join(' · '),
    'integrity-context',
  );

  const values = appendText(card, 'dl', '', 'integrity-values');
  for (const [label, value] of [
    ['Project budget', formatMoney(record.budget_centavos)],
    ['Status / progress', `${displayValue(record.status)} / ${displayValue(record.progress)}%`],
    ['Location', [record.province, record.region].filter(Boolean).join(', ') || 'Not stated'],
  ]) {
    const block = document.createElement('div');
    appendText(block, 'dt', label);
    appendText(block, 'dd', value);
    values.append(block);
  }
  const explanation = appendText(card, 'div', '', 'integrity-explanation');
  appendText(explanation, 'p', `What we noticed: ${record.evidence}`);
  appendText(explanation, 'p', `Why check it: ${copy.why_check || record.label}`);
  appendText(explanation, 'p', `What this does not prove: ${copy.not_proof || record.limitations}`);
  appendText(explanation, 'p', `What to check next: ${copy.next_step || 'Open the source record and look for a newer official document.'}`);
  card.append(renderDistrictContext(record.district_context));
  const links = appendText(card, 'div', '', 'integrity-links');
  appendLink(links, 'Inspect this review signal', titleLink.href);
  appendLink(links, 'View project record', record.reader_source_url);
  if (record.pcab_id) appendLink(links, `Verify PCAB ID ${record.pcab_id}`, 'https://www.pcab.construction.gov.ph/verify/');
  return card;
};

const renderContractor = (record) => {
  const row = document.createElement('article');
  row.className = 'contractor-record';
  const identity = document.createElement('div');
  const title = appendText(identity, 'h3', '');
  const titleLink = appendText(title, 'a', record.contractor_name, 'record-title-link');
  titleLink.href = `/contractors/${encodeURIComponent(record.contractor_key)}/`;
  appendText(
    identity,
    'p',
    record.pcab_id ? `Recorded PCAB ID ${record.pcab_id}` : 'No PCAB ID in the source identity',
  );
  appendText(
    identity,
    'span',
    pcabStatusLabels[record.pcab_status] || 'PCAB status unavailable',
    'pcab-status',
  );
  if (record.pcab_name && record.pcab_name !== record.contractor_name) {
    appendText(identity, 'p', `Current PCAB listing: ${record.pcab_name}`);
  }
  row.append(identity);
  for (const [label, value] of [
    ['Projects', number.format(record.project_count)],
    ['Associated project budget', formatMoney(record.total_budget_centavos)],
  ]) {
    const metric = appendText(row, 'div', '', 'contractor-metric');
    appendText(metric, 'span', label);
    appendText(metric, 'strong', value);
  }
  const detail = appendText(row, 'div', '', 'contractor-status');
  appendText(detail, 'span', `${number.format(record.completed_count)} completed`);
  appendText(detail, 'span', `${number.format(record.ongoing_count)} ongoing`);
  appendText(detail, 'span', `${number.format(record.terminated_count)} terminated`);
  appendText(detail, 'span', `FY ${record.first_year} to ${record.last_year}`);
  if (record.joint_project_count) {
    appendText(detail, 'span', `${number.format(record.joint_project_count)} joint projects`);
  }
  if (record.pcab_valid_to) appendText(detail, 'span', `Current listing valid to ${record.pcab_valid_to}`);
  appendLink(detail, 'Open contractor activity', titleLink.href);
  if (record.pcab_id) appendLink(detail, 'Verify contractor registration', record.pcab_url);
  return row;
};

const contractGroupUrl = (record) => {
  const field = { region: 'region', province: 'province', category: 'category' }[record.dimension];
  const params = new URLSearchParams();
  if (field) params.set(field, record.group_label);
  if (record.fiscal_year) params.set('year', String(record.fiscal_year));
  return `/contracts/?${params}`;
};

const renderConcentration = (record) => {
  const row = document.createElement('article');
  row.className = 'concentration-record';
  const title = appendText(row, 'h3', '');
  const groupLink = appendText(title, 'a', record.group_label, 'record-title-link');
  groupLink.href = contractGroupUrl(record);
  appendText(row, 'strong', `${percent(record.top_share_basis_points)} of party associations`);
  const description = appendText(row, 'p', '');
  const contractorLink = appendText(description, 'a', record.top_contractor_name, 'concentration-contractor-link');
  contractorLink.href = `/contractors/${encodeURIComponent(record.top_contractor_key)}/`;
  description.append(document.createTextNode(
    ` appears on ${number.format(record.top_project_count)} of ${number.format(record.party_association_count)} contractor-party associations.`,
  ));
  appendText(
    row,
    'small',
    `${number.format(record.project_count)} projects · ${number.format(record.named_project_count)} with a contractor · ${number.format(record.contractor_count)} contractor identities · ${formatMoney(record.top_associated_budget_centavos)} associated with the leading party`,
  );
  return row;
};

const loadConcentrations = async () => {
  concentrationStatus.textContent = 'Calculating disclosed concentration shares...';
  const values = new FormData(concentrationForm);
  const params = new URLSearchParams({
    dimension: String(values.get('dimension')),
    year: String(values.get('year')),
  });
  try {
    const response = await fetch(`/api/v1/contractor-concentrations?${params}`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Concentration service returned ${response.status}`);
    const payload = await response.json();
    concentrationResults.replaceChildren(...payload.data.map(renderConcentration));
    concentrationStatus.textContent = payload.data.length
      ? 'Share uses contractor-party associations, including each explicitly listed joint-venture party.'
      : 'No group meets the publication threshold for this selection.';
  } catch {
    concentrationResults.replaceChildren();
    concentrationStatus.textContent = 'Concentration analysis is temporarily unavailable.';
  }
};

const loadSummary = async () => {
  const response = await fetch('/api/v1/integrity-summary', { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Summary service returned ${response.status}`);
  renderSummary((await response.json()).data);
};

const loadIntegrity = async ({ append = false } = {}) => {
  integrityController?.abort();
  integrityController = new AbortController();
  integrityStatus.textContent = 'Checking the published rules...';
  const params = integrityParams();
  if (append && integrityCursor) params.set('cursor', integrityCursor);
  const exportParams = integrityParams();
  exportParams.delete('limit');
  integrityExport.href = `/api/v1/integrity.csv?${exportParams}`;
  try {
    const response = await fetch(`/api/v1/integrity-signals?${params}`, {
      headers: { Accept: 'application/json' },
      signal: integrityController.signal,
    });
    if (!response.ok) throw new Error(`Integrity service returned ${response.status}`);
    const payload = await response.json();
    const records = payload.data.map(renderIntegrityRecord);
    if (append) integrityResults.append(...records);
    else integrityResults.replaceChildren(...records);
    integrityCursor = payload.meta.next_cursor;
    integrityMore.hidden = !integrityCursor;
    integrityCount.textContent = number.format(integrityResults.children.length);
    integrityTotal.textContent = number.format(payload.meta.total);
    integrityStatus.textContent = payload.meta.total
      ? 'Each flag is a question to check, not proof that something is wrong.'
      : 'No source records match these filters.';
    if (!append) syncIntegrityUrl();
  } catch (error) {
    if (error.name === 'AbortError') return;
    if (!append) integrityResults.replaceChildren();
    integrityStatus.textContent = 'The integrity desk is temporarily unavailable. No result was inferred.';
    integrityMore.hidden = true;
  }
};

const loadContractors = async ({ append = false } = {}) => {
  contractorController?.abort();
  contractorController = new AbortController();
  contractorStatus.textContent = 'Aggregating archived project records...';
  const params = contractorParams();
  if (append && contractorCursor) params.set('cursor', contractorCursor);
  try {
    const response = await fetch(`/api/v1/contractors?${params}`, {
      headers: { Accept: 'application/json' },
      signal: contractorController.signal,
    });
    if (!response.ok) throw new Error(`Contractor service returned ${response.status}`);
    const payload = await response.json();
    const records = payload.data.map(renderContractor);
    if (append) contractorResults.append(...records);
    else contractorResults.replaceChildren(...records);
    contractorCursor = payload.meta.next_cursor;
    contractorMore.hidden = !contractorCursor;
    contractorCount.textContent = number.format(contractorResults.children.length);
    contractorTotal.textContent = number.format(payload.meta.total);
    contractorStatus.textContent = payload.meta.total
      ? 'Activity is aggregated from the archived snapshot, not procurement performance.'
      : 'No contractor identities match this search.';
    if (!append) syncContractorUrl();
  } catch (error) {
    if (error.name === 'AbortError') return;
    if (!append) contractorResults.replaceChildren();
    contractorStatus.textContent = 'Contractor activity is temporarily unavailable.';
    contractorMore.hidden = true;
  }
};

integrityForm.addEventListener('submit', (event) => {
  event.preventDefault();
  integrityCursor = null;
  loadIntegrity();
});
integrityMore.addEventListener('click', () => loadIntegrity({ append: true }));
contractorForm.addEventListener('submit', (event) => {
  event.preventDefault();
  contractorCursor = null;
  loadContractors();
});
contractorMore.addEventListener('click', () => loadContractors({ append: true }));
concentrationForm.addEventListener('submit', (event) => {
  event.preventDefault();
  loadConcentrations();
});

const initial = new URLSearchParams(location.search);
for (const name of ['q', 'signal', 'classification', 'year', 'sort']) {
  if (initial.has(name) && integrityForm.elements[name]) {
    integrityForm.elements[name].value = initial.get(name);
  }
}
if (initial.has('contractor_q')) contractorForm.elements.q.value = initial.get('contractor_q');
if (initial.has('contractor_sort')) {
  contractorForm.elements.sort.value = initial.get('contractor_sort');
}

loadSummary().catch(() => {
  integritySummary.textContent = 'Verified snapshot totals are temporarily unavailable.';
});
loadIntegrity();
loadContractors();
loadConcentrations();
