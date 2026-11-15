const root = document.querySelector('[data-project-type-explorer]');
const form = root.querySelector('[data-project-type-form]');
const results = root.querySelector('[data-project-type-results]');
const count = root.querySelector('[data-project-type-count]');
const total = root.querySelector('[data-project-type-total]');
const status = root.querySelector('[data-project-type-status]');
const more = root.querySelector('[data-project-type-more]');
const reset = root.querySelector('[data-project-type-reset]');
const summaryRoot = document.querySelector('[data-project-type-summary]');
const groupRoot = document.querySelector('[data-project-type-groups]');
const number = new Intl.NumberFormat('en-PH');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
let controller = null;
let nextCursor = null;
let shown = 0;

const text = (parent, tag, value, className = '') => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const addOption = (select, value, label) => {
  const option = document.createElement('option');
  option.value = String(value);
  option.textContent = label;
  select.append(option);
};

const replaceOptions = (select, records) => {
  const first = select.options[0];
  select.replaceChildren(first);
  for (const record of records) addOption(select, record.tag ?? record.value, record.label ?? record.value);
};

const renderCoverage = (coverage) => {
  const values = [
    coverage.source_records,
    coverage.classified_records,
    coverage.unclassified_records,
    coverage.classification_tags,
  ];
  [...summaryRoot.querySelectorAll('strong')].forEach((element, index) => {
    element.textContent = number.format(values[index] || 0);
  });
};

const chooseType = (tag) => {
  form.elements.type.value = tag;
  for (const button of groupRoot.querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(button.dataset.type === tag));
  }
  load(true);
};

const renderGroups = (records) => {
  const buttons = records.map((record) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.type = record.tag;
    button.setAttribute('aria-pressed', 'false');
    text(button, 'span', 'Project type');
    text(button, 'strong', record.label);
    text(button, 'small', `${number.format(record.project_count)} project records`);
    button.addEventListener('click', () => chooseType(record.tag));
    return button;
  });
  groupRoot.replaceChildren(...buttons);
};

const populateFilters = (summary) => {
  for (const [dimension, records] of Object.entries(summary.dimensions)) {
    const select = form.querySelector(`[data-project-filter="${dimension}"]`);
    replaceOptions(select, records);
  }
  replaceOptions(form.elements.region, summary.facets.regions);
  replaceOptions(form.elements.province, summary.facets.provinces);
  replaceOptions(form.elements.status, summary.facets.statuses);
  replaceOptions(form.elements.year, summary.facets.years);
};

const restoreQuery = () => {
  const initial = new URLSearchParams(location.search);
  for (const name of ['q', 'type', 'purpose', 'work', 'program', 'year', 'region', 'province', 'status', 'sort']) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
};

const query = () => {
  const params = new URLSearchParams({ limit: '25' });
  const values = new FormData(form);
  for (const [name, raw] of values.entries()) {
    const value = String(raw).trim();
    if (value && value !== 'all') params.set(name, value);
  }
  return params;
};

const evidenceLabel = (value) => ({
  project_title: 'project title',
  source_category: 'source category',
  source_category_and_title: 'project title and source category',
}[value] || 'source fields');

const renderRecord = (record) => {
  const card = document.createElement('article');
  card.className = 'project-type-card';
  const main = text(card, 'div', '');
  const tags = text(main, 'div', '', 'tag-list');
  for (const item of record.classifications) {
    const tag = text(tags, 'span', item.label);
    tag.dataset.dimension = item.dimension;
    tag.title = `Label supported by the ${evidenceLabel(item.evidence_kind)}`;
  }
  const heading = text(main, 'h2', '');
  const link = text(heading, 'a', record.description);
  link.href = record.reader_url;
  const meta = text(main, 'p', '', 'project-type-meta');
  text(meta, 'span', `FY ${record.fiscal_year}`);
  text(meta, 'span', record.region || 'Region not stated');
  text(meta, 'span', record.province || 'Province or office not stated');
  text(meta, 'span', record.status || 'Status not stated');
  text(meta, 'span', `${record.progress || 'Not stated'}${record.progress ? '%' : ''} reported progress`);
  text(main, 'p', record.contractor_name || 'Contractor not stated', 'project-type-evidence');
  const evidence = [...new Set(record.classifications.map((item) => evidenceLabel(item.evidence_kind)))];
  text(main, 'p', `Labels supported by: ${evidence.join(', ')}.`, 'project-type-evidence');
  const side = text(card, 'aside', '');
  text(side, 'strong', peso.format(Number(record.budget_centavos || 0) / 100));
  text(side, 'span', 'Recorded project budget');
  const open = text(side, 'a', 'Open project record');
  open.href = record.reader_url;
  return card;
};

const load = async (fresh) => {
  controller?.abort();
  controller = new AbortController();
  const params = query();
  if (!fresh && nextCursor) params.set('cursor', nextCursor);
  status.textContent = 'Loading matching project records…';
  more.hidden = true;
  try {
    const response = await fetch(`/api/v1/project-types?${params}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Project service returned ${response.status}`);
    const payload = await response.json();
    const cards = payload.data.map(renderRecord);
    if (fresh) {
      results.replaceChildren(...cards);
      shown = cards.length;
    } else {
      results.append(...cards);
      shown += cards.length;
    }
    nextCursor = payload.meta.next_cursor;
    count.textContent = number.format(shown);
    total.textContent = number.format(payload.meta.total);
    status.textContent = payload.meta.total
      ? 'Every result opens to its saved project record.'
      : 'No project records match these filters.';
    more.hidden = !nextCursor;
    if (fresh) {
      params.delete('limit');
      params.delete('cursor');
      history.replaceState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
    }
  } catch (error) {
    if (error.name === 'AbortError') return;
    if (fresh) results.replaceChildren();
    status.textContent = 'The project type explorer is temporarily unavailable.';
  }
};

const start = async () => {
  try {
    const response = await fetch('/api/v1/project-types/summary', {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Summary service returned ${response.status}`);
    const payload = await response.json();
    renderCoverage(payload.data.coverage);
    populateFilters(payload.data);
    renderGroups(payload.data.dimensions.project_type);
    restoreQuery();
    await load(true);
  } catch {
    groupRoot.replaceChildren();
    status.textContent = 'The project type explorer is temporarily unavailable.';
  }
};

form.addEventListener('submit', (event) => {
  event.preventDefault();
  load(true);
});
reset.addEventListener('click', () => {
  form.reset();
  for (const button of groupRoot.querySelectorAll('button')) button.setAttribute('aria-pressed', 'false');
  load(true);
});
more.addEventListener('click', () => load(false));
start();
