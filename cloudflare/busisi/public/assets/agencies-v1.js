(() => {
  const root = document.querySelector('[data-agency-ledger]');
  if (!root) return;
  const form = root.querySelector('[data-agency-form]');
  const results = root.querySelector('[data-agency-results]');
  const count = root.querySelector('[data-agency-count]');
  const total = root.querySelector('[data-agency-total]');
  const status = root.querySelector('[data-agency-status]');
  const more = root.querySelector('[data-agency-more]');
  const reset = root.querySelector('[data-agency-reset]');
  const peso = new Intl.NumberFormat('en-PH', {
    style: 'currency', currency: 'PHP', maximumFractionDigits: 0,
  });
  let nextCursor = null;
  let controller = null;

  const appendText = (parent, tag, value, className) => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };
  const money = (centavos) => peso.format(Number(centavos) / 100);
  const amount = (parent, label, centavos, className = '') => {
    const block = document.createElement('div');
    appendText(block, 'span', label);
    appendText(block, 'strong', centavos === null ? 'Not applicable' : money(centavos), className);
    parent.append(block);
  };
  const sourceLink = (parent, label, href) => {
    const link = appendText(parent, 'a', label);
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  };

  const renderRecord = (record) => {
    const card = document.createElement('article');
    card.className = 'agency-card';
    const copy = document.createElement('div');
    const header = document.createElement('header');
    const direction = record.stage_status === 'not_applicable'
      ? 'unavailable'
      : record.difference_centavos > 0 ? 'increase'
        : record.difference_centavos < 0 ? 'decrease' : 'unchanged';
    const directionLabel = {
      increase: 'House increase', decrease: 'House decrease',
      unchanged: 'No change', unavailable: 'Outside House bill',
    }[direction];
    appendText(header, 'span', directionLabel, `agency-badge ${direction}`);
    appendText(
      header,
      'span',
      record.level === 'congress_institution' ? 'Congress institution' : 'Appropriation head',
      'agency-badge',
    );
    copy.append(header);
    appendText(copy, 'h2', record.name);
    appendText(copy, 'p', `Code ${record.code} · FY ${record.fiscal_year}`, 'agency-meta');
    const evidence = appendText(copy, 'div', '', 'agency-evidence');
    sourceLink(evidence, 'NEP dataset', record.nep_source_url);
    if (record.house_source_url) {
      const page = record.house_pages[0];
      sourceLink(
        evidence,
        page ? `House source page ${page}` : 'House source',
        page ? `${record.house_source_url}#page=${page}` : record.house_source_url,
      );
    }
    card.append(copy);
    const amounts = appendText(card, 'div', '', 'agency-amounts');
    amount(amounts, 'FY2026 base', record.base_centavos);
    amount(amounts, 'FY2027 NEP', record.nep_centavos);
    amount(amounts, 'House bill', record.house_centavos);
    amount(
      amounts,
      'NEP to House movement',
      record.difference_centavos,
      record.difference_centavos > 0 ? 'positive'
        : record.difference_centavos < 0 ? 'negative' : '',
    );
    return card;
  };

  const params = (cursor) => {
    const output = new URLSearchParams();
    const data = new FormData(form);
    for (const name of ['q', 'level', 'direction', 'sort']) {
      const value = String(data.get(name) || '').trim();
      if (value && value !== 'all') output.set(name, value);
    }
    output.set('limit', '25');
    if (cursor) output.set('cursor', cursor);
    return output;
  };
  const syncUrl = () => {
    const query = params();
    query.delete('limit');
    history.replaceState(null, '', `${location.pathname}${query.size ? `?${query}` : ''}`);
  };
  const load = async ({ append = false } = {}) => {
    controller?.abort();
    controller = new AbortController();
    status.textContent = 'Loading reconciled appropriation totals…';
    try {
      const response = await fetch(
        `/api/v1/agency-budgets?${params(append ? nextCursor : null)}`,
        { headers: { Accept: 'application/json' }, signal: controller.signal },
      );
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
        ? 'Reconciled totals · open the source page before interpreting a change.'
        : 'No appropriation heads match these filters.';
      syncUrl();
    } catch (error) {
      if (error.name === 'AbortError') return;
      results.replaceChildren();
      nextCursor = null;
      more.hidden = true;
      status.textContent = 'The appropriation-head ledger is temporarily unavailable. No value was inferred.';
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
  for (const name of ['q', 'level', 'direction', 'sort']) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
  load();
})();
