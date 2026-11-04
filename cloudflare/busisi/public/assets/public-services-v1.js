(() => {
  const root = document.querySelector('[data-public-services-desk]');
  if (!root) return;
  const form = root.querySelector('[data-services-form]');
  const results = root.querySelector('[data-services-results]');
  const shown = root.querySelector('[data-services-count]');
  const total = root.querySelector('[data-services-total]');
  const status = root.querySelector('[data-services-status]');
  const more = root.querySelector('[data-services-more]');
  const reset = root.querySelector('[data-services-reset]');
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

  const label = (value) => String(value || '').replaceAll('_', ' ')
    .replace(/^./, (character) => character.toUpperCase());

  const renderRecord = (record) => {
    const readerUrl = record.reader_url || (record.source_type === 'budget'
      ? `/records/change/${encodeURIComponent(record.record_id)}/`
      : `/contracts/${encodeURIComponent(record.record_id)}/`);
    const card = document.createElement('article');
    card.className = 'services-card';
    const main = document.createElement('div');
    const header = document.createElement('header');
    appendText(header, 'span', record.source_type === 'budget' ? 'Budget-stage row' : 'Delivery contract', `services-tag ${record.source_type}`);
    appendText(header, 'span', label(record.facility_type), 'services-tag');
    appendText(header, 'span', label(record.work_type), 'services-tag');
    const identity = record.facility_identity || { state: 'unlinked' };
    const identityLabels = {
      official_exact: 'Official facility ID linked',
      group_only: 'Possible facility group',
      ambiguous: 'Facility identity needs review',
      unlinked: 'Facility not linked yet',
    };
    appendText(header, 'span', identityLabels[identity.state] || 'Facility not linked yet',
      `services-tag identity ${identity.state || 'unlinked'}`);
    if (record.flag_count) appendText(header, 'span', `${record.flag_count} thing${record.flag_count === 1 ? '' : 's'} to check`, 'services-tag flag');
    main.append(header);
    const heading = appendText(main, 'h3', '');
    const link = appendText(heading, 'a', record.title);
    link.href = readerUrl;
    const meta = appendText(main, 'p', '', 'services-meta');
    [
      `FY ${record.fiscal_year}`,
      record.record_id,
      record.location || 'Location not stated',
      record.office || 'Office not stated',
      record.status || 'Status not stated',
    ].forEach((value) => appendText(meta, 'span', value));
    if (record.flags.length) {
      const flags = appendText(main, 'div', '', 'services-flags');
      record.flags.forEach((flag) => {
        const copy = flag.plain_language || {};
        const item = appendText(flags, 'article', '', 'services-flag');
        appendText(item, 'b', copy.label || flag.label);
        appendText(item, 'p', `Why check: ${copy.why_check || flag.label}`);
        appendText(item, 'p', `What this does not prove: ${copy.not_proof || flag.limitation}`);
        appendText(item, 'small', `Technical tag: ${label(flag.classification)}`);
      });
    }
    const identityNote = appendText(main, 'div', '', 'services-identity-note');
    appendText(identityNote, 'b', identity.name || identityLabels[identity.state] || 'Facility identity');
    appendText(identityNote, 'p', identity.explanation || 'No facility identity explanation is available.');
    if (identity.official_id) appendText(identityNote, 'small', `Official ID: ${identity.official_id}`);
    const side = document.createElement('div');
    side.className = 'services-card-side';
    appendText(side, 'strong', peso.format(Number(record.amount_centavos || 0) / 100));
    appendText(side, 'span', record.source_type === 'budget' ? 'Published stage amount' : 'Recorded contract budget');
    const evidence = appendText(side, 'a', 'See record and source');
    evidence.href = readerUrl;
    card.append(main, side);
    return card;
  };

  const parameters = () => {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) {
      const normalized = String(value).trim();
      if (normalized && normalized !== 'all' && normalized !== 'amount_desc') {
        params.set(key, normalized);
      }
    }
    params.set('limit', '25');
    return params;
  };

  const load = async (append = false) => {
    if (controller) controller.abort();
    controller = new AbortController();
    const params = parameters();
    if (append && nextCursor) params.set('cursor', nextCursor);
    status.textContent = append ? 'Loading more records…' : 'Loading records…';
    try {
      const response = await fetch(`/api/v1/public-services?${params}`, { signal: controller.signal });
      if (!response.ok) throw new Error(`Request failed with HTTP ${response.status}`);
      const payload = await response.json();
      if (!append) results.replaceChildren();
      payload.data.forEach((record) => results.append(renderRecord(record)));
      if (!payload.data.length && !append) appendText(results, 'p', 'No records match these filters.', 'services-empty');
      nextCursor = payload.meta.next_cursor;
      more.hidden = !nextCursor;
      total.textContent = payload.meta.total.toLocaleString('en-PH');
      shown.textContent = results.querySelectorAll('.services-card').length.toLocaleString('en-PH');
      status.textContent = payload.meta.total
        ? 'These are records, not a count of separate buildings. Open one to see its source.'
        : 'No record matches these choices.';
    } catch (error) {
      if (error.name === 'AbortError') return;
      status.textContent = 'The records could not be loaded. Try again.';
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    load(false);
  });
  reset.addEventListener('click', () => {
    form.reset();
    load(false);
  });
  more.addEventListener('click', () => load(true));
  load(false);
})();
