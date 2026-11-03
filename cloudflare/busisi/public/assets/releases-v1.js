(() => {
  const root = document.querySelector('[data-release-ledger]');
  if (!root) return;
  const form = root.querySelector('[data-release-form]');
  const results = root.querySelector('[data-release-results]');
  const count = root.querySelector('[data-release-count]');
  const total = root.querySelector('[data-release-total]');
  const status = root.querySelector('[data-release-status]');
  const more = root.querySelector('[data-release-more]');
  const reset = root.querySelector('[data-release-reset]');
  const money = new Intl.NumberFormat('en-PH', {
    style: 'currency', currency: 'PHP', maximumFractionDigits: 0,
  });
  let nextCursor = null;
  let controller = null;

  const appendText = (parent, tag, value, className = '') => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };
  const peso = (centavos) => money.format(Number(centavos) / 100);
  const rate = (basisPoints) => basisPoints === null
    ? 'Not applicable' : `${(Number(basisPoints) / 100).toFixed(2)}%`;
  const levelLabel = (level) => ({
    department: 'Department', attached_agency: 'Attached agency',
    subunit: 'Agency subunit', special_purpose_fund: 'Special Purpose Fund',
  }[level] || level);
  const amount = (parent, label, value, className = '') => {
    const block = document.createElement('div');
    appendText(block, 'span', label);
    appendText(block, 'strong', value, className);
    parent.append(block);
  };

  const renderRecord = (record) => {
    const card = document.createElement('article');
    card.className = 'release-card';
    const copy = document.createElement('div');
    const header = document.createElement('header');
    appendText(header, 'span', levelLabel(record.level), 'release-badge');
    const needsAttention = record.release_bps !== null && record.release_bps < 9000;
    if (needsAttention) appendText(header, 'span', 'Below 90% released', 'release-badge attention');
    copy.append(header);
    appendText(copy, 'h2', record.name);
    appendText(copy, 'p', `Code ${record.code} · FY ${record.fiscal_year} · as of 30 Sep 2026`, 'release-meta');
    if (record.parent_name) appendText(copy, 'p', `Under ${record.parent_name}`, 'release-parent');
    card.append(copy);
    const amounts = appendText(card, 'div', '', 'release-amounts');
    amount(amounts, 'Adjusted program', peso(record.adjusted_program_centavos));
    amount(amounts, 'Allotments released', peso(record.release_centavos));
    amount(amounts, 'Unreleased balance', peso(record.balance_centavos), record.balance_centavos > 0 ? 'attention' : '');
    amount(amounts, 'Released', rate(record.release_bps));
    return card;
  };

  const query = (cursor) => {
    const params = new URLSearchParams();
    const data = new FormData(form);
    for (const name of ['q', 'level', 'band', 'sort']) {
      const value = String(data.get(name) || '').trim();
      if (value && value !== 'all') params.set(name, value);
    }
    params.set('limit', '25');
    if (cursor) params.set('cursor', cursor);
    return params;
  };
  const syncUrl = () => {
    const params = query();
    params.delete('limit');
    history.replaceState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
  };
  const load = async ({ append = false } = {}) => {
    controller?.abort();
    controller = new AbortController();
    status.textContent = 'Loading reconciled DBM release totals…';
    try {
      const response = await fetch(`/api/v1/allotment-releases?${query(append ? nextCursor : null)}`, {
        headers: { Accept: 'application/json' }, signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Data service returned ${response.status}`);
      const payload = await response.json();
      const cards = payload.data.map(renderRecord);
      if (append) results.append(...cards);
      else results.replaceChildren(...cards);
      nextCursor = payload.meta.next_cursor;
      count.textContent = String(results.children.length);
      total.textContent = String(payload.meta.total);
      more.hidden = !nextCursor;
      status.textContent = payload.meta.total
        ? 'Official DBM allotment releases. These are not obligations, disbursements, or payments.'
        : 'No release records match these filters.';
      syncUrl();
    } catch (error) {
      if (error.name === 'AbortError') return;
      results.replaceChildren();
      nextCursor = null;
      more.hidden = true;
      status.textContent = 'The release ledger is temporarily unavailable. No value was inferred.';
    }
  };

  const loadSummary = async () => {
    try {
      const response = await fetch('/api/v1/allotment-release-summary', {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) return;
      const { data } = await response.json();
      document.querySelector('[data-release-current]').textContent = peso(data.current_gaa_releases_centavos);
      document.querySelector('[data-release-balance]').textContent = peso(data.current_gaa_balance_centavos);
      document.querySelector('[data-release-all]').textContent = peso(data.total_releases_centavos);
      document.querySelector('[data-release-rows]').textContent = String(data.record_count);
    } catch {
      // The static evidence boundary remains useful if the summary service is unavailable.
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    nextCursor = null;
    load();
  });
  reset.addEventListener('click', () => {
    form.reset();
    nextCursor = null;
    load();
  });
  more.addEventListener('click', () => load({ append: true }));
  const initial = new URLSearchParams(location.search);
  for (const name of ['q', 'level', 'band', 'sort']) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
  loadSummary();
  load();
})();
