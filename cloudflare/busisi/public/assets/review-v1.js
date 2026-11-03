import { renderDistrictContext } from './district-context-v1.js';

const root = document.querySelector('[data-review-desk]');

const form = root.querySelector('[data-review-form]');
const rankings = root.querySelector('[data-review-rankings]');
const concentrations = root.querySelector('[data-review-concentrations]');
const status = root.querySelector('[data-review-status]');
const total = root.querySelector('[data-review-total]');
const exportLink = root.querySelector('[data-review-export]');
const summary = document.querySelector('[data-review-summary]');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
const number = new Intl.NumberFormat('en-PH');
let controller = null;

const signalLabels = Object.freeze({
  house_only: 'House-only row',
  increased: 'Amount increased',
  decreased: 'Amount decreased',
  nep_only: 'NEP-only row',
  repeat_family: 'Prior-year family candidate',
  similar_family: 'Similar FY2027 family candidate',
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
  return new URLSearchParams({
    signal: String(values.get('signal')),
    dataset: String(values.get('dataset')),
    dimension: String(values.get('dimension')),
    limit: '20',
  });
};

const renderSummary = (payload) => {
  const changeMap = Object.fromEntries(payload.changes.map((item) => [item.change_type, item]));
  const keys = ['house_only', 'increased', 'decreased', 'nep_only'];
  summary.replaceChildren(...keys.map((key) => {
    const item = changeMap[key] || { record_count: 0, difference_centavos: 0 };
    const card = document.createElement('article');
    appendText(card, 'strong', number.format(item.record_count));
    appendText(card, 'span', signalLabels[key]);
    appendText(card, 'small', formatMoney(item.difference_centavos), 'review-summary-money');
    return card;
  }));
};

const renderRanking = (record) => {
  const card = document.createElement('article');
  card.className = 'review-record';
  const heading = document.createElement('header');
  appendText(heading, 'span', signalLabels[record.signal], 'review-badge');
  appendText(heading, 'span', record.dataset.toUpperCase(), 'review-badge dataset');
  if (record.review_status === 'quarantine') {
    appendText(heading, 'span', 'Quarantine', 'review-badge quarantine');
  }
  card.append(heading);
  appendText(card, 'h3', record.title);
  appendText(
    card,
    'p',
    [record.program, record.region, record.office].filter(Boolean).join(' · ') || 'Context not stated',
    'review-record-context',
  );
  card.append(renderDistrictContext(record.district_context));
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
    appendText(card, 'p', `Prior positive appropriations: ${record.prior_years.join(', ')}`, 'review-record-note');
  }
  if (record.family_count > 1) {
    appendText(card, 'p', `${record.family_count} FY2027 rows share this normalized family label.`, 'review-record-note');
  }
  const links = appendText(card, 'div', '', 'review-record-links');
  evidenceLink(links, 'View NEP PDF', record.nep_pdf_url);
  evidenceLink(links, 'View House bill PDF', record.house_pdf_url);
  return card;
};

const renderConcentrations = (items) => {
  const maximum = Math.max(...items.map((item) => Number(item.movement_centavos)), 1);
  concentrations.replaceChildren(...items.map((item) => {
    const row = document.createElement('article');
    const copy = document.createElement('div');
    appendText(copy, 'strong', item.label);
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
  status.textContent = 'Calculating deterministic review candidates…';
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
      ? 'Candidates are ordered for documentary review, not accusation.'
      : 'No records match this deterministic rule and dataset.';
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
  loadReview();
});
const initial = new URLSearchParams(location.search);
for (const name of ['signal', 'dataset', 'dimension']) {
  if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
}
loadSummary().catch(() => {
  summary.textContent = 'Summary unavailable.';
});
loadReview();
