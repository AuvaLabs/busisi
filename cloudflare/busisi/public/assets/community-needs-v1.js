const root = document.querySelector('[data-community-needs]');
const form = root?.querySelector('[data-needs-form]');
const results = root?.querySelector('[data-needs-results]');
const status = root?.querySelector('[data-needs-status]');
const number = new Intl.NumberFormat('en-PH');
let controller = null;

const text = (parent, tag, value, className = '') => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const metric = (list, label, value) => {
  const item = text(list, 'div', '');
  text(item, 'dt', label);
  text(item, 'dd', number.format(value || 0));
};

const levelLabel = (level) => ({
  region: 'Region',
  province_or_huc: 'Province or highly urbanized city',
  city_or_municipality: 'City or municipality',
  submunicipality: 'Manila district',
  barangay: 'Barangay',
}[level] || 'Place');

const render = (record) => {
  const row = document.createElement('article');
  row.className = 'needs-place';
  text(row, 'h2', record.name);
  text(row, 'p', record.parent_name ? `${levelLabel(record.geographic_level)} in ${record.parent_name}` : levelLabel(record.geographic_level), 'needs-parent');
  const list = text(row, 'dl', '');
  metric(list, 'People', record.total_population);
  metric(list, 'Household population', record.household_population);
  metric(list, 'Households', record.households);
  const footer = text(row, 'footer', '');
  text(footer, 'span', `PSGC ${record.psgc_code}`);
  const source = text(footer, 'a', 'Open PSA table');
  source.href = record.source_page_url;
  source.rel = 'external';
  if (!record.child_coverage_complete) {
    text(row, 'p', 'Some lower-level rows do not add to this place total. Use the place total as stated by PSA.', 'needs-parent');
  }
  return row;
};

const setSummary = async () => {
  const response = await fetch('/api/v1/community-needs-summary', { headers: { Accept: 'application/json' } });
  if (!response.ok) return;
  const { data } = await response.json();
  document.querySelector('[data-needs-population]').textContent = number.format(data.national_population);
  document.querySelector('[data-needs-households]').textContent = number.format(data.national_households);
  document.querySelector('[data-needs-places]').textContent = number.format(data.place_count);
  document.querySelector('[data-needs-barangays]').textContent = number.format(data.barangay_count);
};

const load = async () => {
  controller?.abort();
  controller = new AbortController();
  const values = new FormData(form);
  const query = new URLSearchParams({ level: String(values.get('level')), limit: '50' });
  const q = String(values.get('q') || '').trim();
  if (q) query.set('q', q);
  status.textContent = 'Loading official population context...';
  try {
    const response = await fetch(`/api/v1/community-needs?${query}`, {
      headers: { Accept: 'application/json' }, signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Community needs service returned ${response.status}`);
    const payload = await response.json();
    results.replaceChildren(...payload.data.map(render));
    status.textContent = payload.data.length
      ? `${number.format(payload.data.length)} places shown. Population context is not a red flag.`
      : 'No place matches this search.';
    query.delete('limit');
    history.replaceState(null, '', `${location.pathname}?${query}`);
  } catch (error) {
    if (error.name === 'AbortError') return;
    results.replaceChildren();
    status.textContent = 'Community population context is temporarily unavailable.';
  }
};

if (root && form && results && status) {
  const initial = new URLSearchParams(location.search);
  if (initial.has('q')) form.elements.q.value = initial.get('q');
  if (initial.has('level')) form.elements.level.value = initial.get('level');
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    load();
  });
  setSummary();
  load();
}
