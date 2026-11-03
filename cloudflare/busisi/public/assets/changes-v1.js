import { renderDistrictContext } from './district-context-v1.js';

(() => {
  const root = document.querySelector('[data-change-ledger]');
  if (!root) return;

  const form = root.querySelector('[data-change-form]');
  const results = root.querySelector('[data-change-results]');
  const count = root.querySelector('[data-change-count]');
  const total = root.querySelector('[data-change-total]');
  const status = root.querySelector('[data-change-status]');
  const more = root.querySelector('[data-change-more]');
  const reset = root.querySelector('[data-change-reset]');
  const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
  const datasetLabels = Object.freeze({
    dpwh: 'DPWH infrastructure',
    fmr: 'Farm-to-market roads',
    hfep: 'Health facilities',
    nia: 'Irrigation',
  });
  const changeLabels = Object.freeze({
    house_only: 'In the House bill only',
    nep_only: 'In the NEP only',
    unchanged: 'Same amount in both',
    increased: 'Amount increased',
    decreased: 'Amount decreased',
    scope_review: 'Different scope · review',
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

  const evidenceLink = (parent, label, href) => {
    if (!href) return;
    const link = appendText(parent, 'a', label);
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  };

  const amount = (parent, label, centavos, className = '') => {
    const block = document.createElement('div');
    appendText(block, 'span', label);
    appendText(block, 'strong', peso.format(Number(centavos || 0) / 100), className);
    parent.append(block);
  };

  const renderRecord = (record) => {
    const card = document.createElement('article');
    card.className = 'change-card';
    const copy = document.createElement('div');
    const header = document.createElement('header');
    appendText(header, 'span', changeLabels[record.change_type] || record.change_label, `change-badge ${record.change_type}`);
    appendText(header, 'span', datasetLabels[record.dataset] || record.dataset, 'change-badge');
    if (record.review_status === 'quarantine') {
      appendText(header, 'span', 'Quarantine', 'change-badge quarantine');
    }
    copy.append(header);
    const title = appendText(copy, 'h2', '');
    const titleLink = appendText(title, 'a', record.title, 'record-title-link');
    titleLink.href = `/records/change/${encodeURIComponent(record.record_id)}/`;
    const context = [record.program, record.region, record.office].filter(Boolean).join(' · ');
    appendText(copy, 'p', context || 'Context not stated in source row', 'change-meta');
    copy.append(renderDistrictContext(record.district_context));
    const links = appendText(copy, 'div', '', 'change-evidence');
    const detail = appendText(links, 'a', 'Open comparison record');
    detail.href = titleLink.href;
    evidenceLink(links, record.nep_page ? `View NEP PDF · page ${record.nep_page}` : 'View NEP PDF', record.nep_pdf_url);
    evidenceLink(links, record.house_page ? `View House bill PDF · page ${record.house_page}` : 'View House bill PDF', record.house_pdf_url);
    card.append(copy);

    const amounts = appendText(card, 'div', '', 'change-amounts');
    amount(amounts, 'NEP', record.nep_centavos);
    amount(amounts, 'House bill', record.house_centavos);
    const differenceClass = record.difference_centavos > 0 ? 'positive' : record.difference_centavos < 0 ? 'negative' : '';
    amount(amounts, 'Recorded movement', record.difference_centavos, differenceClass);
    return card;
  };

  const params = (cursor) => {
    const output = new URLSearchParams();
    const data = new FormData(form);
    for (const name of ['q', 'dataset', 'change', 'review', 'sort']) {
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
    status.textContent = 'Loading reconciled comparisons…';
    try {
      const response = await fetch(`/api/v1/changes?${params(append ? nextCursor : null)}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
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
        ? 'Provisional comparisons · inspect source pages before drawing conclusions.'
        : 'No rows match these filters.';
      syncUrl();
    } catch (error) {
      if (error.name === 'AbortError') return;
      results.replaceChildren();
      nextCursor = null;
      more.hidden = true;
      status.textContent = 'The change ledger is temporarily unavailable. No result was inferred.';
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
  window.addEventListener('popstate', () => location.reload());

  const initial = new URLSearchParams(location.search);
  for (const name of ['q', 'dataset', 'change', 'review', 'sort']) {
    if (initial.has(name) && form.elements[name]) form.elements[name].value = initial.get(name);
  }
  load();
})();
