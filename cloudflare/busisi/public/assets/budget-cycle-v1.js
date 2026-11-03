const root = document.querySelector('[data-budget-cycle]');
const list = document.querySelector('[data-cycle-documents]');
const status = document.querySelector('[data-cycle-status]');

const LABELS = Object.freeze({
  available: 'Available',
  available_elsewhere: 'Available elsewhere',
  partial: 'Partial catalogue',
  unavailable: 'Not yet acquired',
});

const make = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

const updateStages = (stages) => {
  for (const stage of stages) {
    const card = root?.querySelector(`[data-cycle-stage="${stage.stage}"]`);
    if (!card) continue;
    card.classList.remove('available', 'partial', 'unavailable');
    card.classList.add(stage.status === 'available_elsewhere' ? 'available' : stage.status);
    const badge = card.querySelector('b');
    if (badge) badge.textContent = LABELS[stage.status] || stage.status;
  }
};

const documentCard = (record) => {
  const article = make('article', 'cycle-document');
  const meta = make('div', 'cycle-record-meta');
  meta.append(make('span', '', record.stage_label));
  if (record.publication_date) meta.append(make('span', '', record.publication_date));
  const verified = record.acquisition_status === 'verified_archived';
  meta.append(make(
    'span',
    `cycle-status${verified ? ' verified' : ''}`,
    verified ? 'Archived copy verified' : 'Catalogue record only',
  ));

  const content = make('div');
  content.append(make('h3', '', record.title));
  content.append(make('p', '', record.evidence_note));
  const links = make('div', 'cycle-links');
  const source = make('a', '', 'Open Senate publication index');
  source.href = record.source_url;
  source.target = '_blank';
  source.rel = 'noopener noreferrer';
  links.append(source);
  if (record.mirror_url) {
    const archived = make('a', '', 'Read archived document copy');
    archived.href = record.mirror_url;
    archived.target = '_blank';
    archived.rel = 'noopener noreferrer';
    links.append(archived);
  }
  content.append(links);
  article.append(meta, content);
  return article;
};

const load = async () => {
  try {
    const [summaryResponse, documentsResponse] = await Promise.all([
      fetch('/api/v1/budget-cycle'),
      fetch('/api/v1/budget-cycle/documents'),
    ]);
    if (!summaryResponse.ok || !documentsResponse.ok) throw new Error('request failed');
    const [{ data: summary }, { data: documents, meta }] = await Promise.all([
      summaryResponse.json(), documentsResponse.json(),
    ]);
    updateStages(summary.stages);
    list.replaceChildren(...documents.map(documentCard));
    status.textContent = `${meta.total} source-separated records in the FY2027 catalogue.`;
  } catch {
    list.replaceChildren(make('p', 'cycle-empty', 'The document register is temporarily unavailable.'));
    status.textContent = 'Publication register unavailable.';
  }
};

if (root && list && status) load();
