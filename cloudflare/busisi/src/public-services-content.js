import { reviewClassEntries } from './reader-language.js';

const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const number = (value) => Number(value || 0).toLocaleString('en-PH');

const option = (value, label) => `<option value="${html(value)}">${html(label)}</option>`;

const flagGuide = () => reviewClassEntries().map(([classification, copy]) => `<article>
  <span>${html(copy.label)}</span>
  <p><strong>Why check:</strong> ${html(copy.why_check)}</p>
  <p><strong>What it does not prove:</strong> ${html(copy.not_proof)}</p>
  <small>Technical tag: ${html(classification.replaceAll('_', ' '))}</small>
</article>`).join('');

export const publicServicesBody = (summary) => {
  const records = summary?.records || {};
  const facilities = summary?.facilities || {};
  const work = summary?.work_types || {};
  return `
  <section class="services-hero">
    <div><p class="eyebrow">Schools and health services</p><h1>Schools and health facilities in the public record.</h1><p class="lede">Search records that name a school, hospital, or health center. See the amount, place, type of work, and anything that needs checking.</p></div>
    <aside aria-label="Current public-services scope"><span>Records found</span><strong>${number(records.total)} records that name a facility</strong><dl><div><dt>Budget records</dt><dd>${number(records.budget)}</dd></div><div><dt>Project contracts</dt><dd>${number(records.delivery)}</dd></div><div><dt>Needs checking</dt><dd>${number(records.flagged)} records with things to check</dd></div></dl></aside>
  </section>
  <section class="services-boundary"><strong>What this count means</strong><p>These are records, not separate buildings. One facility can have several budget records or contracts. A record also does not prove that work started or finished.</p></section>
  <section class="services-snapshot" aria-label="Title classification summary">
    <article><span>School records</span><strong>${number(facilities.school)}</strong><small>School or classroom explicitly named</small></article>
    <article><span>Hospital records</span><strong>${number(facilities.hospital)}</strong><small>Hospital or medical center explicitly named</small></article>
    <article><span>Health-center records</span><strong>${number(facilities.health_center)}</strong><small>Health center, rural health unit, station, or facility</small></article>
    <article><span>New-build wording</span><strong>${number(work.new_build)}</strong><small>Construction or establishment explicitly named</small></article>
  </section>
  <section class="services-flag-guide" aria-labelledby="services-flags-heading">
    <div><p class="kicker">Red flags in plain language</p><h2 id="services-flags-heading">Things that need checking.</h2><p>A red flag is a question, not an answer. This does not mean the project is bad or illegal. It means a record is missing, different, repeated, or unclear.</p></div>
    <div class="services-flag-grid">${flagGuide()}</div>
  </section>
  <section class="services-desk" data-public-services-desk>
    <header><div><p class="kicker">Search the records</p><h2>Open a record and see what supports it.</h2></div><p>A budget amount and a contract budget mean different things. Busisi keeps them separate and never adds them together here.</p></header>
    <form data-services-form class="services-controls" role="search">
      <label>Search<input name="q" type="search" maxlength="200" placeholder="School, hospital, place, office…"></label>
      <label>Source<select name="source">${option('all', 'All record sources')}${option('budget', 'Budget-stage rows')}${option('delivery', 'Delivery contracts')}</select></label>
      <label>Facility<select name="facility">${option('all', 'All facilities')}${option('school', 'Schools')}${option('hospital', 'Hospitals')}${option('health_center', 'Health centers')}</select></label>
      <label>Work type<select name="work">${option('all', 'All work types')}${option('new_build', 'New build')}${option('rehabilitation', 'Rehabilitation')}${option('expansion', 'Expansion')}${option('equipment', 'Equipment')}${option('continuation', 'Continuation or phase')}${option('unspecified', 'Unspecified')}</select></label>
      <label>Things to check<select name="flag">${option('all', 'All records')}${option('with_flags', 'Has something to check')}${option('without_flags', 'Nothing flagged')}${option('stage_change', 'Budget entry changed')}${option('record_contradiction', 'Record says different things')}${option('location_review', 'Place needs checking')}${option('identity_conflict', 'Project ID needs checking')}${option('coverage_gap', 'Information is missing')}${option('repeat_family', 'Similar project appears again')}</select></label>
      <label>Sort<select name="sort">${option('amount_desc', 'Largest amount')}${option('year_desc', 'Newest fiscal year')}${option('flags_desc', 'Most things to check')}${option('title_asc', 'Title A to Z')}</select></label>
      <button type="submit">Apply filters</button><button type="button" class="secondary-control" data-services-reset>Reset</button>
    </form>
    <div class="services-result-summary" aria-live="polite"><p><strong data-services-count>0</strong> of <span data-services-total>0</span> records shown</p><p data-services-status>Loading records…</p></div>
    <div class="services-results" data-services-results></div>
    <div class="services-actions"><button type="button" data-services-more hidden>Load more</button></div>
    <noscript><p class="services-error">JavaScript is required for interactive filtering. The evidence desks remain available from the main navigation.</p></noscript>
  </section>
  <section class="services-method"><div><p class="kicker">What Busisi can say</p><h2>We show what the records say and where they stop.</h2></div><div><p><strong>Busisi can show:</strong> records that name a facility, the stated work, the amount, and the source.</p><p><strong>Busisi cannot prove from these records alone:</strong> how many separate buildings exist, whether work finished, whether payment happened, or whether people received the promised service.</p></div><a href="/methodology/">See how Busisi checks records <span aria-hidden="true">→</span></a></section>`;
};
