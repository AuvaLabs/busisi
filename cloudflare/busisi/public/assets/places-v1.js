const root = document.querySelector('[data-place-directory]');
const form = root.querySelector('[data-place-form]');
const results = root.querySelector('[data-place-results]');
const status = root.querySelector('[data-place-status]');
const number = new Intl.NumberFormat('en-PH');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
let controller = null;

const text = (parent, tag, value) => {
  const element = document.createElement(tag);
  element.textContent = value;
  parent.append(element);
  return element;
};

const metric = (list, label, value) => {
  const item = text(list, 'div', '');
  text(item, 'dt', label);
  text(item, 'dd', value);
};

const params = () => {
  const values = new FormData(form);
  const query = new URLSearchParams({ level: String(values.get('level')), limit: '100' });
  const q = String(values.get('q') || '').trim();
  if (q) query.set('q', q);
  return query;
};

const render = (record) => {
  const row = document.createElement('article');
  row.className = 'place-record';
  const heading = text(row, 'h2', '');
  const link = text(heading, 'a', record.place_name);
  link.href = record.reader_url;
  const list = text(row, 'dl', '');
  metric(list, 'Project records', number.format(record.project_count));
  metric(list, 'Recorded budgets', peso.format(Number(record.total_budget_centavos || 0) / 100));
  metric(list, 'Contractor identities', number.format(record.contractor_count));
  metric(list, 'Projects needing a check', number.format(record.projects_needing_check));
  return row;
};

const load = async () => {
  controller?.abort();
  controller = new AbortController();
  const query = params();
  status.textContent = 'Grouping recorded source labels...';
  try {
    const response = await fetch(`/api/v1/places?${query}`, {
      headers: { Accept: 'application/json' }, signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Place service returned ${response.status}`);
    const payload = await response.json();
    results.replaceChildren(...payload.data.map(render));
    status.textContent = payload.data.length
      ? `${number.format(payload.data.length)} recorded place labels shown. Source labels are not verified map boundaries.`
      : 'No recorded place labels match this search.';
    query.delete('limit');
    history.replaceState(null, '', `${location.pathname}?${query}`);
  } catch (error) {
    if (error.name === 'AbortError') return;
    results.replaceChildren();
    status.textContent = 'The place directory is temporarily unavailable.';
  }
};

form.addEventListener('submit', (event) => {
  event.preventDefault();
  load();
});
const initial = new URLSearchParams(location.search);
if (initial.has('q')) form.elements.q.value = initial.get('q');
if (initial.has('level')) form.elements.level.value = initial.get('level');
load();
