const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const date = (value) => {
  if (!value) return 'Current published scope';
  if (/^FY\d{4}/.test(value)) return html(value);
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? html(value)
    : new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeZone: 'UTC' }).format(parsed);
};

const label = (value) => String(value ?? '')
  .replaceAll('_', ' ')
  .replace(/^./, (character) => character.toUpperCase());

const card = (record) => `<article class="question-card question-${html(record.state)}">
  <header><span class="question-state">${html(record.state_label)}</span><span>${html(record.category)}</span></header>
  <h3>${html(record.question)}</h3>
  <p>${html(record.answer_summary)}</p>
  <dl>
    <div><dt>Scope</dt><dd>${html(record.scope_label)}</dd></div>
    <div><dt>As of</dt><dd>${date(record.as_of)}</dd></div>
    <div><dt>Level</dt><dd>${html(label(record.evidence_level))}</dd></div>
    <div><dt>Source</dt><dd>${html(record.source_label)}</dd></div>
  </dl>
  <p class="question-limit"><strong>Limit:</strong> ${html(record.limitation)}</p>
  ${record.answer_url ? `<a href="${html(record.answer_url)}">Open the evidence <span aria-hidden="true">→</span></a>` : ''}
</article>`;

const section = (id, kicker, title, description, records) => `<section class="question-section" id="${id}" aria-labelledby="${id}-heading">
  <div class="question-section-heading"><div><p class="kicker">${kicker}</p><h2 id="${id}-heading">${title}</h2></div><p>${description}</p></div>
  <div class="question-grid">${records.map(card).join('')}</div>
</section>`;

export const questionsBody = (records) => {
  const answerable = records.filter(({ state }) => state === 'answerable');
  const partial = records.filter(({ state }) => state === 'partially_answerable');
  const unsupported = records.filter(({ state }) => state === 'not_supported');
  return `
  <section class="questions-hero">
    <div><p class="eyebrow">Evidence question catalogue</p><h1>Questions Busisi can answer from current evidence.</h1><p class="lede">Every answer is tied to a dated scope, an evidence level, a reader-facing source desk, and a stated limitation. When the records are insufficient, Busisi says so.</p></div>
    <aside aria-label="Question catalogue status"><span>Current catalogue</span><strong>${records.length} public questions</strong><dl><div><dt>Answerable</dt><dd>${answerable.length}</dd></div><div><dt>Partially answerable</dt><dd>${partial.length}</dd></div><div><dt>Not yet supported</dt><dd>${unsupported.length}</dd></div></dl></aside>
  </section>
  <nav class="question-index" aria-label="Question evidence states"><a href="#answerable">Answerable <b>${answerable.length}</b></a><a href="#partial">Partially answerable <b>${partial.length}</b></a><a href="#unsupported">Not yet supported <b>${unsupported.length}</b></a></nav>
  ${section('answerable', 'Current evidence', 'Answers with defined coverage', 'These questions have a direct evidence desk and a deterministic or official-source basis. Their limits still apply.', answerable)}
  ${section('partial', 'Incomplete coverage', 'Useful answers that must stay scoped', 'These records are real and traceable, but coverage is a growing release, a secondary source, or a reviewed pilot.', partial)}
  ${section('unsupported', 'Evidence boundary', 'What Busisi cannot establish', 'Busisi will not turn a missing source, a record contradiction, or a pattern into a factual conclusion.', unsupported)}
  <section class="question-method"><div><p class="kicker">How to use this catalogue</p><h2>Scope first. Claim second.</h2></div><p>Counts and dates come from the current publication database. They update when a new reconciled release is published. Read the limitation before quoting an answer.</p><a href="/methodology/">Read the publication method <span aria-hidden="true">→</span></a></section>`;
};
