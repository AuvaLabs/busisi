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

const answerType = (state) => ({
  answerable: 'Based on official or checked records',
  partially_answerable: 'Useful answer, but the records are incomplete',
  not_supported: 'Not enough evidence to answer',
}[state] || label(state));

const card = (record) => `<article class="question-card question-${html(record.state)}">
  <header><span class="question-state">${html(record.state_label)}</span><span>${html(record.category)}</span></header>
  <h3>${html(record.question)}</h3>
  <p>${html(record.answer_summary)}</p>
  <dl>
    <div><dt>Records checked</dt><dd>${html(record.scope_label)}</dd></div>
    <div><dt>Date</dt><dd>${date(record.as_of)}</dd></div>
    <div><dt>Answer type</dt><dd>${html(answerType(record.state))}</dd></div>
    <div><dt>Source</dt><dd>${html(record.source_label)}</dd></div>
  </dl>
  <p class="question-limit"><strong>What this answer cannot prove:</strong> ${html(record.limitation)}</p>
  ${record.answer_url ? `<a href="${html(record.answer_url)}">See the records behind this answer <span aria-hidden="true">→</span></a>` : ''}
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
    <div><p class="eyebrow">What the records can tell us</p><h1>What can Busisi answer today?</h1><p class="lede">Choose a question. Busisi shows the answer, the records used, the date, and what those records cannot prove.</p></div>
    <aside aria-label="Question catalogue status"><span>Questions checked</span><strong>${records.length} public questions</strong><dl><div><dt>Can answer</dt><dd>${answerable.length}</dd></div><div><dt>Can partly answer</dt><dd>${partial.length}</dd></div><div><dt>Cannot answer yet</dt><dd>${unsupported.length}</dd></div></dl></aside>
  </section>
  <nav class="question-index" aria-label="Question answer states"><a href="#answerable">Can answer <b>${answerable.length}</b></a><a href="#partial">Can partly answer <b>${partial.length}</b></a><a href="#unsupported">Cannot answer yet <b>${unsupported.length}</b></a></nav>
  ${section('answerable', 'Answers available', 'Questions Busisi can answer', 'These questions link to records that support an answer. Each answer still has a clear limit.', answerable)}
  ${section('partial', 'Part of the answer is available', 'Useful answers with missing pieces', 'Busisi has useful records, but not enough to answer every part of the question.', partial)}
  ${section('unsupported', 'Not enough evidence', 'Questions Busisi cannot answer yet', 'Busisi will not turn missing information or an unusual pattern into a fact.', unsupported)}
  <section class="question-method"><div><p class="kicker">How to use these answers</p><h2>Read the limit before sharing the answer.</h2></div><p>Counts and dates come from the current Busisi records. They can change when new checked records are published.</p><a href="/methodology/">See how Busisi checks records <span aria-hidden="true">→</span></a></section>`;
};
