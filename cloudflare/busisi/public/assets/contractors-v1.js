const root = document.querySelector('[data-contractor-directory]');
const form = root.querySelector('[data-contractor-form]');
const results = root.querySelector('[data-contractor-results]');
const status = root.querySelector('[data-contractor-status]');
const shown = root.querySelector('[data-contractor-count]');
const total = root.querySelector('[data-contractor-total]');
const more = root.querySelector('[data-contractor-more]');
const count = new Intl.NumberFormat('en-PH');
const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
let cursor = null;
let controller = null;

const text = (parent, tag, value, className = '') => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const link = (parent, label, href) => {
  const element = text(parent, 'a', label);
  element.href = href;
  parent.append(element);
  return element;
};

const money = (centavos) => peso.format(Number(centavos || 0) / 100);

const params = () => {
  const values = new FormData(form);
  const query = new URLSearchParams({ sort: String(values.get('sort')), limit: '20' });
  const q = String(values.get('q') || '').trim();
  if (q) query.set('q', q);
  return query;
};

const render = (record) => {
  const row = document.createElement('article');
  row.className = 'contractor-record';
  const identity = text(row, 'div', '');
  const heading = text(identity, 'h2', '');
  link(heading, record.contractor_name, `/contractors/${encodeURIComponent(record.contractor_key)}/`);
  text(identity, 'p', record.pcab_id ? `Recorded PCAB ID ${record.pcab_id}` : 'No PCAB ID stated in the source identity');
  text(identity, 'span', String(record.pcab_status || 'PCAB status unavailable').replaceAll('_', ' '), 'pcab-status');
  for (const [label, value] of [
    ['Projects', count.format(record.project_count)],
    ['Associated project budget', money(record.total_budget_centavos)],
  ]) {
    const metric = text(row, 'div', '', 'contractor-metric');
    text(metric, 'span', label);
    text(metric, 'strong', value);
  }
  const details = text(row, 'div', '', 'contractor-status');
  text(details, 'span', `${count.format(record.completed_count)} completed`);
  text(details, 'span', `${count.format(record.ongoing_count)} ongoing`);
  text(details, 'span', `FY ${record.first_year} to ${record.last_year}`);
  if (record.joint_project_count) text(details, 'span', `${count.format(record.joint_project_count)} joint projects`);
  link(details, 'Open contractor evidence', `/contractors/${encodeURIComponent(record.contractor_key)}/`);
  return row;
};

const syncUrl = () => {
  const query = params();
  query.delete('limit');
  history.replaceState(null, '', `${location.pathname}${query.size ? `?${query}` : ''}`);
};

const load = async ({ append = false } = {}) => {
  controller?.abort();
  controller = new AbortController();
  status.textContent = 'Aggregating archived project records...';
  const query = params();
  if (append && cursor) query.set('cursor', cursor);
  try {
    const response = await fetch(`/api/v1/contractors?${query}`, {
      headers: { Accept: 'application/json' }, signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Contractor service returned ${response.status}`);
    const payload = await response.json();
    const rows = payload.data.map(render);
    if (append) results.append(...rows);
    else results.replaceChildren(...rows);
    cursor = payload.meta.next_cursor;
    more.hidden = !cursor;
    shown.textContent = count.format(results.children.length);
    total.textContent = count.format(payload.meta.total);
    status.textContent = payload.meta.total
      ? 'Activity comes from archived source records. It is not a performance rating.'
      : 'No contractor identities match this search.';
    if (!append) syncUrl();
  } catch (error) {
    if (error.name === 'AbortError') return;
    if (!append) results.replaceChildren();
    more.hidden = true;
    status.textContent = 'Contractor activity is temporarily unavailable.';
  }
};

form.addEventListener('submit', (event) => {
  event.preventDefault();
  cursor = null;
  load();
});
more.addEventListener('click', () => load({ append: true }));
const initial = new URLSearchParams(location.search);
if (initial.has('q')) form.elements.q.value = initial.get('q');
if (initial.has('sort')) form.elements.sort.value = initial.get('sort');
load();
