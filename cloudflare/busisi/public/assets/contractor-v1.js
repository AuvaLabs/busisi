(() => {
  const root = document.querySelector('[data-contractor-activity]');
  if (!root) return;

  const contractorKey = root.dataset.contractorKey;
  const form = root.querySelector('[data-contractor-project-form]');
  const results = root.querySelector('[data-contractor-project-results]');
  const status = root.querySelector('[data-contractor-project-status]');
  const more = root.querySelector('[data-contractor-project-more]');
  const number = new Intl.NumberFormat('en-PH');
  const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
  let nextCursor = null;
  let controller = null;

  const appendText = (parent, tag, value, className) => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };

  const appendLink = (parent, label, href, className) => {
    const link = appendText(parent, 'a', label, className);
    link.href = href;
    return link;
  };

  const money = (centavos) => peso.format(Number(centavos || 0) / 100);

  const query = (cursor) => {
    const values = new FormData(form);
    const params = new URLSearchParams({ limit: '25' });
    for (const name of ['year', 'relationship', 'status', 'signal', 'sort']) {
      const value = String(values.get(name) || '').trim();
      if (value && value !== 'all') params.set(name, value);
    }
    if (cursor) params.set('cursor', cursor);
    return params;
  };

  const renderParties = (parent, record) => {
    const list = appendText(parent, 'div', '', 'contractor-project-parties');
    record.contractor_parties.forEach((party) => {
      const current = party.contractor_key === contractorKey;
      const link = appendLink(
        list,
        party.contractor_name,
        `/contractors/${encodeURIComponent(party.contractor_key)}/`,
        current ? 'current-party' : '',
      );
      if (current) link.setAttribute('aria-current', 'page');
    });
  };

  const renderProject = (record) => {
    const card = document.createElement('article');
    card.className = 'contractor-project-card';
    const heading = document.createElement('header');
    appendText(heading, 'span', `FY ${record.fiscal_year}`);
    appendText(heading, 'span', record.relationship === 'joint'
      ? `Joint party ${record.party_position} of ${record.party_count}`
      : 'Sole recorded party');
    if (record.signal_count) {
      appendText(heading, 'span', `${number.format(record.signal_count)} review signal${record.signal_count === 1 ? '' : 's'}`, 'signal');
    }
    card.append(heading);
    const title = appendText(card, 'h3', '');
    appendLink(title, record.description, record.reader_url);
    appendText(
      card,
      'p',
      [record.contract_id, record.status || 'Status not stated', record.location || 'Location not stated'].join(' · '),
      'contractor-project-context',
    );
    const metrics = appendText(card, 'dl', '', 'contractor-project-metrics');
    for (const [label, value] of [
      ['Recorded project budget', money(record.budget_centavos)],
      ['Reported progress', record.progress ? `${record.progress}%` : 'Not stated'],
      ['Evidence match', (record.match_state || 'Not available').replaceAll('_', ' ')],
    ]) {
      const row = document.createElement('div');
      appendText(row, 'dt', label);
      appendText(row, 'dd', value);
      metrics.append(row);
    }
    renderParties(card, record);
    appendLink(card, 'Open complete contract evidence', record.reader_url, 'evidence-action');
    return card;
  };

  const syncUrl = () => {
    const params = query();
    params.delete('limit');
    history.replaceState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
  };

  const load = async ({ append = false } = {}) => {
    controller?.abort();
    controller = new AbortController();
    status.textContent = 'Loading structured project associations...';
    try {
      const response = await fetch(
        `/api/v1/contractors/${encodeURIComponent(contractorKey)}/projects?${query(append ? nextCursor : null)}`,
        { headers: { Accept: 'application/json' }, signal: controller.signal },
      );
      if (!response.ok) throw new Error(`Project service returned ${response.status}`);
      const payload = await response.json();
      const cards = payload.data.map(renderProject);
      if (append) results.append(...cards);
      else results.replaceChildren(...cards);
      nextCursor = payload.meta.next_cursor;
      more.hidden = !nextCursor;
      status.textContent = payload.meta.total
        ? `${number.format(results.children.length)} of ${number.format(payload.meta.total)} project associations shown. Full project budgets are not joint-party shares.`
        : 'No project associations match these filters.';
      if (!append) syncUrl();
    } catch (error) {
      if (error.name === 'AbortError') return;
      if (!append) results.replaceChildren();
      nextCursor = null;
      more.hidden = true;
      status.textContent = 'The contractor project ledger is temporarily unavailable.';
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    nextCursor = null;
    load();
  });
  more.addEventListener('click', () => load({ append: true }));
  window.addEventListener('popstate', () => location.reload());

  const initial = new URLSearchParams(location.search);
  for (const name of ['year', 'relationship', 'status', 'signal', 'sort']) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
  load();
})();
