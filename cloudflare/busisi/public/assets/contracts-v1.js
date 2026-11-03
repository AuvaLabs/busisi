(() => {
  const root = document.querySelector('[data-contract-explorer]');
  if (!root) return;

  const form = root.querySelector('[data-contract-form]');
  const results = root.querySelector('[data-contract-results]');
  const count = root.querySelector('[data-contract-count]');
  const total = root.querySelector('[data-contract-total]');
  const status = root.querySelector('[data-contract-status-text]');
  const more = root.querySelector('[data-contract-more]');
  const reset = root.querySelector('[data-contract-reset]');
  const exportLink = root.querySelector('[data-contract-export]');
  const compare = root.querySelector('[data-contract-compare]');
  const comparison = root.querySelector('[data-contract-comparison]');
  const clear = root.querySelector('[data-contract-clear]');
  const presets = [...document.querySelectorAll('[data-contract-preset]')];
  const selected = new Map();
  const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
  const number = new Intl.NumberFormat('en-PH');
  let nextCursor = null;
  let controller = null;

  const stateLabels = Object.freeze({
    structured_exact: 'Exact structured ID',
    title_exact: 'Exact title ID',
    multiple_exact_rows: 'Multiple exact rows',
    conflict_review: 'Identifier conflict',
    no_exact_row: 'No exact row',
    invalid_identifier: 'Invalid identifier',
  });

  const appendText = (parent, tag, value, className) => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };

  const appendLink = (parent, label, href) => {
    const anchor = appendText(parent, 'a', label);
    anchor.href = href;
    return anchor;
  };

  const money = (centavos) => peso.format(Number(centavos || 0) / 100);

  const stateClass = (state) => {
    if (state === 'conflict_review') return 'conflict';
    if (['no_exact_row', 'invalid_identifier'].includes(state)) return 'gap';
    return '';
  };

  const identityBlock = (parent, label, value) => {
    const block = document.createElement('div');
    appendText(block, 'span', label);
    appendText(block, 'strong', value || 'Not stated');
    parent.append(block);
  };

  const renderComparison = () => {
    const records = [...selected.values()];
    compare.hidden = records.length < 2;
    if (records.length < 2) {
      comparison.replaceChildren();
      return;
    }
    const grid = document.createElement('dl');
    grid.className = 'contract-comparison-grid';
    grid.style.setProperty('--compare-count', records.length);
    appendText(grid, 'dt', 'Field');
    records.forEach((record) => appendText(grid, 'dd', record.contract_id));
    const fields = [
      ['Project', (record) => record.description],
      ['Budget', (record) => money(record.budget_centavos)],
      ['Location', (record) => record.location || 'Not stated'],
      ['Delivery status', (record) => record.status || 'Not stated'],
      ['Evidence state', (record) => stateLabels[record.match_state] || record.match_state],
      ['Recorded contractor', (record) => record.contractor_name || 'Not stated'],
      ['Secondary awardee', (record) => record.awardee_names || 'No exact row'],
      ['Review signals', (record) => String(record.signal_count)],
    ];
    fields.forEach(([label, value]) => {
      appendText(grid, 'dt', label);
      records.forEach((record) => appendText(grid, 'dd', value(record)));
    });
    comparison.replaceChildren(grid);
  };

  const comparisonToggle = (record) => {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = selected.has(record.contract_id);
    input.setAttribute('aria-label', `Compare contract ${record.contract_id}`);
    input.addEventListener('change', () => {
      if (input.checked && selected.size >= 3) {
        input.checked = false;
        status.textContent = 'Compare up to three contracts at a time.';
        return;
      }
      if (input.checked) selected.set(record.contract_id, record);
      else selected.delete(record.contract_id);
      renderComparison();
    });
    label.append(input, document.createTextNode('Compare'));
    return label;
  };

  const renderRecord = (record) => {
    const card = document.createElement('article');
    card.className = 'contract-card';
    const main = document.createElement('div');
    const header = document.createElement('header');
    appendText(
      header,
      'span',
      stateLabels[record.match_state] || record.match_state.replaceAll('_', ' '),
      `contract-tag ${stateClass(record.match_state)}`,
    );
    if (record.signal_count) {
      appendText(header, 'span', `${record.signal_count} review signal${record.signal_count === 1 ? '' : 's'}`, 'contract-tag signal');
    }
    main.append(header);
    const heading = appendText(main, 'h2', '');
    appendLink(heading, record.description, record.reader_url);
    const meta = appendText(main, 'p', '', 'contract-meta');
    for (const value of [
      `FY ${record.fiscal_year}`,
      `Contract ${record.contract_id}`,
      record.location || 'Location not stated',
      record.category || 'Category not stated',
      record.status || 'Status not stated',
    ]) appendText(meta, 'span', value);
    const identities = appendText(main, 'div', '', 'contract-identities');
    identityBlock(identities, 'Recorded contractor', record.contractor_name);
    identityBlock(identities, 'Secondary mirror awardee', record.awardee_names || 'No accepted exact row');
    const side = document.createElement('div');
    side.className = 'contract-card-side';
    appendText(side, 'strong', money(record.budget_centavos));
    appendText(side, 'span', 'Recorded project budget');
    side.append(comparisonToggle(record));
    const links = appendText(side, 'div', '', 'contract-evidence-links');
    appendLink(links, 'Open evidence', record.reader_url);
    if (record.signal_count) {
      appendLink(links, 'Inspect signals', `/integrity/?q=${encodeURIComponent(record.contract_id)}`);
    }
    const contractor = record.contractor_parties?.find((item) => item.contractor_key);
    if (contractor) {
      appendLink(links, 'Contractor activity', `/contractors/${encodeURIComponent(contractor.contractor_key)}/`);
    }
    card.append(main, side);
    return card;
  };

  const query = (cursor) => {
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const name of [
      'q', 'year', 'state', 'budget', 'signal', 'region', 'province', 'category', 'status',
      'contractor', 'sort',
    ]) {
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
    exportLink.href = `/api/v1/contracts.csv?${params}`;
  };

  const updatePresetState = () => {
    presets.forEach((button) => {
      const preset = button.dataset.contractPreset;
      const active = preset === 'with_signals'
        ? form.elements.signal.value === preset
        : form.elements.state.value === preset;
      button.setAttribute('aria-pressed', String(active));
    });
  };

  const load = async ({ append = false } = {}) => {
    controller?.abort();
    controller = new AbortController();
    status.textContent = 'Loading verified contract evidence...';
    try {
      const response = await fetch(`/api/v1/contracts?${query(append ? nextCursor : null)}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Contract service returned ${response.status}`);
      const payload = await response.json();
      const cards = payload.data.map(renderRecord);
      if (append) results.append(...cards);
      else results.replaceChildren(...cards);
      nextCursor = payload.meta.next_cursor;
      count.textContent = number.format(results.children.length);
      total.textContent = number.format(payload.meta.total);
      more.hidden = !nextCursor;
      status.textContent = payload.data.length
        ? 'Showing source records with explicit evidence boundaries.'
        : 'No contracts match these filters. No result was inferred.';
      updatePresetState();
      syncUrl();
    } catch (error) {
      if (error.name === 'AbortError') return;
      if (!append) results.replaceChildren();
      nextCursor = null;
      more.hidden = true;
      status.textContent = 'The contract service is temporarily unavailable. No result was inferred.';
    }
  };

  const populateFacet = (selector, items, label) => {
    const select = root.querySelector(selector);
    const initial = select.firstElementChild;
    const options = items.map((item) => {
      const option = document.createElement('option');
      option.value = item.value;
      option.textContent = `${item.value} (${number.format(item.count)})`;
      return option;
    });
    select.replaceChildren(initial, ...options);
    if (!initial) appendText(select, 'option', label);
  };

  const loadSummary = async () => {
    try {
      const response = await fetch('/api/v1/contract-intelligence-summary', {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) return;
      const { data } = await response.json();
      populateFacet('[data-contract-region]', data.facets.regions, 'All regions');
      populateFacet('[data-contract-province]', data.facets.provinces, 'All provinces');
      populateFacet('[data-contract-category]', data.facets.categories, 'All categories');
      populateFacet('[data-contract-status]', data.facets.statuses, 'All statuses');
    } catch {
      status.textContent = 'Summary filters are unavailable. Core contract search remains available.';
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    nextCursor = null;
    load();
  });
  reset.addEventListener('click', () => {
    form.reset();
    selected.clear();
    renderComparison();
    nextCursor = null;
    load();
  });
  more.addEventListener('click', () => load({ append: true }));
  clear.addEventListener('click', () => {
    selected.clear();
    results.querySelectorAll('input[type="checkbox"]').forEach((input) => { input.checked = false; });
    renderComparison();
  });
  presets.forEach((button) => button.addEventListener('click', () => {
    form.elements.state.value = 'all';
    form.elements.signal.value = 'all';
    const preset = button.dataset.contractPreset;
    if (preset === 'with_signals') form.elements.signal.value = preset;
    else form.elements.state.value = preset;
    nextCursor = null;
    load();
  }));
  window.addEventListener('popstate', () => location.reload());

  const initial = new URLSearchParams(location.search);
  for (const name of [
    'q', 'year', 'state', 'budget', 'signal', 'region', 'province', 'category', 'status',
    'contractor', 'sort',
  ]) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
  loadSummary().finally(() => {
    for (const name of ['region', 'province', 'category', 'status']) {
      if (initial.has(name)) form.elements[name].value = initial.get(name);
    }
    load();
  });
})();
