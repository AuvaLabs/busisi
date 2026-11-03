(() => {
  const search = document.querySelector('[data-watch-search]');
  const year = document.querySelector('[data-year-filter]');
  const sort = document.querySelector('[data-sort]');
  const list = document.querySelector('[data-evidence-list]');
  const count = document.querySelector('[data-result-count]');
  const total = document.querySelector('[data-total-count]');
  const empty = document.querySelector('[data-empty-state]');
  const reset = document.querySelector('[data-reset]');
  const exportButton = document.querySelector('[data-export]');
  const loadMore = document.querySelector('[data-load-more]');
  const sourceStatus = document.querySelector('[data-source-status]');
  const radios = [...document.querySelectorAll('input[name="status"]')];

  if (!search || !year || !sort || !list || !count) return;

  const staticRows = [...document.querySelectorAll('[data-status][data-search]')];
  let rows = [...staticRows];
  let nextCursor = null;
  let requestController = null;
  let requestSequence = 0;
  let debounceTimer = null;

  const statusValue = () => radios.find((radio) => radio.checked)?.value || 'all';
  const number = (row, field) => Number(row.dataset[field] || 0);
  const text = (row, field) => row.dataset[field] || '';
  const peso = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });

  const comparators = {
    appropriation_desc: (a, b) => number(b, 'appropriation') - number(a, 'appropriation'),
    difference_desc: (a, b) => number(b, 'variance') - number(a, 'variance'),
    year_desc: (a, b) => number(b, 'year') - number(a, 'year'),
    title_asc: (a, b) => text(a, 'title').localeCompare(text(b, 'title')),
  };

  const visibleRows = () => rows.filter((row) => !row.hidden);
  const csvCell = (value) => `"${String(value).replaceAll('"', '""')}"`;

  const filterParams = () => {
    const params = new URLSearchParams();
    if (search.value.trim()) params.set('q', search.value.trim());
    if (year.value !== 'all') params.set('year', year.value);
    if (statusValue() !== 'all') params.set('status', statusValue());
    if (sort.value !== 'appropriation_desc') params.set('sort', sort.value);
    return params;
  };

  const syncUrl = () => {
    const query = filterParams().toString();
    history.replaceState(null, '', `${location.pathname}${query ? `?${query}` : ''}`);
  };

  const updateLocalExport = () => {
    if (!exportButton) return;
    const records = visibleRows();
    const header = ['Fiscal year', 'Project', 'Location', 'Contract ID', 'Status', 'Appropriation centavos', 'Contract budget centavos', 'Dossier'];
    const body = records.map((row) => [
      row.dataset.year, row.dataset.title, row.dataset.location, row.dataset.contract,
      row.dataset.status, row.dataset.appropriation, row.dataset.contractBudget,
      new URL(row.dataset.url, location.origin).href,
    ]);
    const csv = [header, ...body].map((record) => record.map(csvCell).join(',')).join('\n');
    exportButton.href = records.length
      ? `data:text/csv;charset=utf-8,${encodeURIComponent(`${csv}\n`)}`
      : '#';
    exportButton.setAttribute('aria-disabled', String(records.length === 0));
  };

  const applyLocal = ({ updateUrl = true } = {}) => {
    const query = search.value.trim().toLocaleLowerCase();
    const status = statusValue();
    rows.forEach((row) => {
      const matchesText = row.dataset.search.toLocaleLowerCase().includes(query);
      const matchesStatus = status === 'all' || row.dataset.status === status;
      const matchesYear = year.value === 'all' || row.dataset.year === year.value;
      row.hidden = !(matchesText && matchesStatus && matchesYear);
    });
    rows.sort(comparators[sort.value] || comparators.appropriation_desc);
    rows.forEach((row) => list.append(row));
    const visible = visibleRows().length;
    count.textContent = String(visible);
    if (total) total.textContent = String(staticRows.length);
    if (empty) empty.hidden = visible !== 0;
    updateLocalExport();
    if (loadMore) loadMore.hidden = true;
    if (updateUrl) syncUrl();
  };

  const appendText = (parent, tag, value, className) => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };

  const recordElement = (record) => {
    const status = record.is_quarantined ? 'quarantine' : 'reviewed';
    const article = document.createElement('article');
    article.className = 'evidence-row';
    Object.assign(article.dataset, {
      status,
      search: `${record.title} ${record.contract_id} ${record.location}`,
      title: record.title,
      year: String(record.fiscal_year),
      appropriation: String(record.appropriation_centavos),
      contractBudget: String(record.contract_budget_centavos),
      variance: String(record.variance_centavos),
      contract: record.contract_id,
      location: record.location,
      url: `/projects/${record.slug}/`,
    });

    const main = document.createElement('div');
    main.className = 'evidence-main';
    appendText(main, 'span', record.status_label, `status ${status}`);
    const heading = document.createElement('h3');
    const link = appendText(heading, 'a', record.title);
    link.href = `/projects/${record.slug}/`;
    main.append(heading);
    appendText(main, 'p', `FY ${record.fiscal_year} · ${record.location} · Contract ${record.contract_id}`);

    const amounts = document.createElement('div');
    amounts.className = 'amount-pair';
    const appropriation = appendText(amounts, 'span', 'Appropriation');
    appendText(appropriation, 'strong', peso.format(record.appropriation_centavos / 100));
    const contract = appendText(amounts, 'span', 'Contract record');
    appendText(contract, 'strong', peso.format(record.contract_budget_centavos / 100));
    article.append(main, amounts);
    return article;
  };

  const restoreStatic = () => {
    rows = [...staticRows];
    list.replaceChildren(...rows);
    applyLocal({ updateUrl: false });
    if (sourceStatus) sourceStatus.textContent = 'Showing the embedded reviewed snapshot.';
  };

  const loadApi = async ({ append = false } = {}) => {
    requestController?.abort();
    requestController = new AbortController();
    const sequence = ++requestSequence;
    const params = filterParams();
    params.set('limit', '25');
    if (append && nextCursor) params.set('cursor', nextCursor);
    if (sourceStatus) sourceStatus.textContent = 'Checking the indexed publication record…';
    try {
      const response = await fetch(`/api/v1/projects?${params.toString()}`, {
        headers: { Accept: 'application/json' },
        signal: requestController.signal,
      });
      if (!response.ok) throw new Error(`publication API returned ${response.status}`);
      const payload = await response.json();
      if (sequence !== requestSequence) return;
      const rendered = payload.data.map(recordElement);
      rows = append ? [...rows, ...rendered] : rendered;
      if (append) list.append(...rendered);
      else list.replaceChildren(...rendered);
      nextCursor = payload.meta.next_cursor;
      count.textContent = String(rows.length);
      if (total) total.textContent = String(payload.meta.total);
      if (empty) empty.hidden = payload.meta.total !== 0;
      if (loadMore) loadMore.hidden = !nextCursor;
      if (exportButton) {
        exportButton.href = `/api/v1/projects.csv?${filterParams().toString()}`;
        exportButton.setAttribute('aria-disabled', 'false');
      }
      if (sourceStatus) sourceStatus.textContent = 'Showing the indexed reviewed publication record.';
    } catch (error) {
      if (error.name !== 'AbortError') restoreStatic();
    }
  };

  const scheduleApi = () => {
    syncUrl();
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => loadApi(), 180);
  };

  const hydrate = () => {
    const params = new URLSearchParams(location.search);
    search.value = params.get('q') || '';
    const requestedYear = params.get('year') || 'all';
    if ([...year.options].some((option) => option.value === requestedYear)) year.value = requestedYear;
    const requestedStatus = params.get('status') || 'all';
    const radio = radios.find((item) => item.value === requestedStatus);
    if (radio) radio.checked = true;
    const requestedSort = params.get('sort') || 'appropriation_desc';
    if ([...sort.options].some((option) => option.value === requestedSort)) sort.value = requestedSort;
    applyLocal({ updateUrl: false });
    loadApi();
  };

  const clear = () => {
    search.value = '';
    year.value = 'all';
    sort.value = 'appropriation_desc';
    const all = radios.find((radio) => radio.value === 'all');
    if (all) all.checked = true;
    scheduleApi();
    search.focus();
  };

  search.addEventListener('input', scheduleApi);
  year.addEventListener('change', scheduleApi);
  sort.addEventListener('change', scheduleApi);
  radios.forEach((radio) => radio.addEventListener('change', scheduleApi));
  reset?.addEventListener('click', clear);
  loadMore?.addEventListener('click', () => loadApi({ append: true }));
  window.addEventListener('popstate', hydrate);
  hydrate();
})();
