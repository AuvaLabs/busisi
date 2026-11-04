import { renderDistrictContext } from './district-context-v1.js';

const root = document.querySelector('[data-review-desk]');

const form = root.querySelector('[data-review-form]');
const rankings = root.querySelector('[data-review-rankings]');
const concentrations = root.querySelector('[data-review-concentrations]');
const status = root.querySelector('[data-review-status]');
const total = root.querySelector('[data-review-total]');
const exportLink = root.querySelector('[data-review-export]');
const groupFilter = root.querySelector('[data-review-group]');
const summary = document.querySelector('[data-review-summary]');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
const number = new Intl.NumberFormat('en-PH');
let controller = null;
const initial = new URLSearchParams(location.search);
let activeGroup = (initial.get('group') || '').trim();

const signalCopy = Object.freeze({
  house_only: Object.freeze({
    label: 'Only in the House bill',
    noticed: 'This row appears in the House bill but not in the matched NEP rows.',
    why: 'The source pages may show whether the item is new, renamed, split, merged, or outside the matched scope.',
    notProof: 'This does not prove who added it, why it changed, or whether it was improper.',
    next: 'Compare the House page with the NEP program pages and later budget stages.',
  }),
  increased: Object.freeze({
    label: 'The amount increased',
    noticed: 'The House bill amount is higher than the matched NEP amount.',
    why: 'The change may alter what work can be funded and deserves an explanation in the source documents.',
    notProof: 'An increase does not prove waste, favoritism, an insertion, or wrongdoing.',
    next: 'Compare both source pages, the work description, and later Senate and enacted amounts when available.',
  }),
  decreased: Object.freeze({
    label: 'The amount decreased',
    noticed: 'The House bill amount is lower than the matched NEP amount.',
    why: 'The change may reduce, move, or change the planned work.',
    notProof: 'A decrease does not prove that a project was cancelled or that another item received the money.',
    next: 'Compare both source pages and check later budget stages for the final amount.',
  }),
  nep_only: Object.freeze({
    label: 'Only in the NEP',
    noticed: 'This row appears in the matched NEP rows but not in the House bill comparison.',
    why: 'The item may have been removed, renamed, combined, moved, or placed outside the matched scope.',
    notProof: 'This does not prove that the project was cancelled or that its funding disappeared.',
    next: 'Search the House bill for a renamed or moved item and check later budget stages.',
  }),
  repeat_family: Object.freeze({
    label: 'Similar to an earlier-year project',
    noticed: 'A project with a similar cleaned-up name appears in an earlier budget year.',
    why: 'The records may describe a continuation, a new phase, maintenance, or separate work.',
    notProof: 'A similar name does not prove duplicate funding or a ghost project.',
    next: 'Compare the year, work description, amount, location, phase, and contract number.',
  }),
  similar_family: Object.freeze({
    label: 'Similar to another FY2027 project',
    noticed: 'More than one FY2027 row shares a similar cleaned-up project name.',
    why: 'The rows may be duplicates, separate phases, or different work with similar titles.',
    notProof: 'Similar wording does not prove that the same work was funded twice.',
    next: 'Compare each row, office, place, amount, work description, and source page.',
  }),
});

const appendText = (parent, tag, value, className) => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const evidenceLink = (parent, label, href) => {
  if (!href) return;
  const link = appendText(parent, 'a', label);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
};

const formatMoney = (centavos) => peso.format(Number(centavos || 0) / 100);

const query = () => {
  const values = new FormData(form);
  const params = new URLSearchParams({
    signal: String(values.get('signal')),
    dataset: String(values.get('dataset')),
    dimension: String(values.get('dimension')),
    limit: '20',
  });
  if (activeGroup) params.set('group', activeGroup);
  return params;
};

const groupUrl = (label) => {
  const params = query();
  params.set('group', label);
  return `${location.pathname}?${params}`;
};

const renderGroupFilter = () => {
  groupFilter.hidden = !activeGroup;
  groupFilter.replaceChildren();
  if (!activeGroup) return;
  appendText(groupFilter, 'span', `Filtered group: ${activeGroup}`);
  const params = query();
  params.delete('group');
  const clear = appendText(groupFilter, 'a', 'Clear group filter');
  clear.href = `${location.pathname}?${params}`;
};

const renderSummary = (payload) => {
  const changeMap = Object.fromEntries(payload.changes.map((item) => [item.change_type, item]));
  const keys = ['house_only', 'increased', 'decreased', 'nep_only'];
  summary.replaceChildren(...keys.map((key) => {
    const item = changeMap[key] || { record_count: 0, difference_centavos: 0 };
    const card = document.createElement('article');
    appendText(card, 'strong', number.format(item.record_count));
    appendText(card, 'span', signalCopy[key].label);
    appendText(card, 'small', formatMoney(item.difference_centavos), 'review-summary-money');
    return card;
  }));
};

const renderRanking = (record) => {
  const card = document.createElement('article');
  card.className = 'review-record';
  const heading = document.createElement('header');
  const explanation = signalCopy[record.signal] || signalCopy.house_only;
  appendText(heading, 'span', explanation.label, 'review-badge');
  appendText(heading, 'span', record.dataset.toUpperCase(), 'review-badge dataset');
  if (record.review_status === 'quarantine') {
    appendText(heading, 'span', 'Held back for checking', 'review-badge quarantine');
  }
  card.append(heading);
  const title = appendText(card, 'h3', '');
  const detailUrl = `/records/change/${encodeURIComponent(record.record_id)}/`;
  const titleLink = appendText(title, 'a', record.title, 'review-record-title');
  titleLink.href = detailUrl;
  appendText(
    card,
    'p',
    [record.program, record.region, record.office].filter(Boolean).join(' · ') || 'Context not stated',
    'review-record-context',
  );
  card.append(renderDistrictContext(record.district_context));
  const explanationBlock = appendText(card, 'div', '', 'review-record-explanation');
  for (const [label, value] of [
    ['What we noticed', explanation.noticed],
    ['Why check it', explanation.why],
    ['What this does not prove', explanation.notProof],
    ['What to check next', explanation.next],
  ]) {
    const paragraph = appendText(explanationBlock, 'p', '');
    appendText(paragraph, 'strong', `${label}: `);
    paragraph.append(document.createTextNode(value));
  }
  const values = appendText(card, 'dl', '', 'review-record-values');
  for (const [label, value] of [
    ['NEP', formatMoney(record.nep_centavos)],
    ['House', formatMoney(record.house_centavos)],
    ['Movement', formatMoney(record.difference_centavos)],
  ]) {
    const block = document.createElement('div');
    appendText(block, 'dt', label);
    appendText(block, 'dd', value);
    values.append(block);
  }
  if (record.prior_years.length) {
    appendText(card, 'p', `Earlier budget years with a positive amount: ${record.prior_years.join(', ')}`, 'review-record-note');
  }
  if (record.family_count > 1) {
    appendText(card, 'p', `${record.family_count} FY2027 rows have a similar cleaned-up project name.`, 'review-record-note');
  }
  const links = appendText(card, 'div', '', 'review-record-links');
  const detail = appendText(links, 'a', 'Inspect project evidence');
  detail.href = detailUrl;
  evidenceLink(links, 'View NEP PDF', record.nep_pdf_url);
  evidenceLink(links, 'View House bill PDF', record.house_pdf_url);
  return card;
};

const renderConcentrations = (items) => {
  const maximum = Math.max(...items.map((item) => Number(item.movement_centavos)), 1);
  concentrations.replaceChildren(...items.map((item) => {
    const row = document.createElement('article');
    const copy = document.createElement('div');
    const label = appendText(copy, 'a', item.label, 'review-concentration-link');
    label.href = groupUrl(item.label);
    appendText(copy, 'span', `${number.format(item.record_count)} rows`);
    row.append(copy);
    const bar = document.createElement('progress');
    bar.max = maximum;
    bar.value = Number(item.movement_centavos);
    bar.setAttribute('aria-label', `${item.label}: ${formatMoney(item.movement_centavos)} movement`);
    row.append(bar);
    appendText(row, 'small', formatMoney(item.movement_centavos));
    return row;
  }));
};

const loadSummary = async () => {
  const response = await fetch('/api/v1/review-summary', { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Summary service returned ${response.status}`);
  renderSummary((await response.json()).data);
};

const loadReview = async () => {
  controller?.abort();
  controller = new AbortController();
  status.textContent = 'Checking records against the selected rule…';
  const params = query();
  exportLink.href = `/api/v1/review.csv?${params}`;
  try {
    const options = { headers: { Accept: 'application/json' }, signal: controller.signal };
    const [rankedResponse, concentrationResponse] = await Promise.all([
      fetch(`/api/v1/review-rankings?${params}`, options),
      fetch(`/api/v1/review-concentrations?${params}`, options),
    ]);
    if (!rankedResponse.ok || !concentrationResponse.ok) throw new Error('Review service failed');
    const ranked = await rankedResponse.json();
    const grouped = await concentrationResponse.json();
    rankings.replaceChildren(...ranked.data.map(renderRanking));
    renderConcentrations(grouped.data);
    total.textContent = number.format(ranked.meta.total);
    status.textContent = ranked.meta.total
      ? `${activeGroup ? `Filtered to ${activeGroup}. ` : ''}These records are questions to check, not accusations.`
      : 'No records match this rule and program.';
    renderGroupFilter();
    history.replaceState(null, '', `${location.pathname}?${params}`);
  } catch (error) {
    if (error.name === 'AbortError') return;
    rankings.replaceChildren();
    concentrations.replaceChildren();
    status.textContent = 'The review desk is temporarily unavailable. No result was inferred.';
  }
};

form.addEventListener('submit', (event) => {
  event.preventDefault();
  activeGroup = '';
  loadReview();
});
for (const name of ['signal', 'dataset', 'dimension']) {
  if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
}
loadSummary().catch(() => {
  summary.textContent = 'Summary unavailable.';
});
loadReview();
