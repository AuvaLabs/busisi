const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const number = (value) => Number(value || 0).toLocaleString('en-PH');

const option = (value, label) => `<option value="${html(value)}">${html(label)}</option>`;

export const publicServicesBody = (summary) => {
  const records = summary?.records || {};
  const facilities = summary?.facilities || {};
  const work = summary?.work_types || {};
  return `
  <section class="services-hero">
    <div><p class="eyebrow">Public services inventory</p><h1>Schools and health facilities in the public record.</h1><p class="lede">Find budget-stage rows and DPWH delivery contracts whose titles explicitly name a school, hospital, or health facility. Review the source record, work type, amount, place, and evidence flags without treating a title as proof of a completed facility.</p></div>
    <aside aria-label="Current public-services scope"><span>Current classified scope</span><strong>${number(records.total)} title-classified records</strong><dl><div><dt>Budget-stage rows</dt><dd>${number(records.budget)}</dd></div><div><dt>Delivery contracts</dt><dd>${number(records.delivery)}</dd></div><div><dt>Review coverage</dt><dd>${number(records.flagged)} records with review flags</dd></div></dl></aside>
  </section>
  <section class="services-boundary"><strong>Counting boundary</strong><p>Budget rows and delivery contracts are never added together as facilities. These are title-classified records, not a count of unique or physically completed buildings.</p></section>
  <section class="services-snapshot" aria-label="Title classification summary">
    <article><span>School records</span><strong>${number(facilities.school)}</strong><small>School or classroom explicitly named</small></article>
    <article><span>Hospital records</span><strong>${number(facilities.hospital)}</strong><small>Hospital or medical center explicitly named</small></article>
    <article><span>Health-center records</span><strong>${number(facilities.health_center)}</strong><small>Health center, rural health unit, station, or facility</small></article>
    <article><span>New-build wording</span><strong>${number(work.new_build)}</strong><small>Construction or establishment explicitly named</small></article>
  </section>
  <section class="services-flag-guide" aria-labelledby="services-flags-heading">
    <div><p class="kicker">Red flags, separated by evidence</p><h2 id="services-flags-heading">Questions for review, never verdicts.</h2><p>A record may carry more than one flag. The classes explain what kind of source problem or comparison deserves attention.</p></div>
    <div class="services-flag-grid">
      <article><span>Stage change</span><p>The amount or presence differs between acquired budget stages.</p></article>
      <article><span>Record contradiction</span><p>Fields inside the archived delivery record do not reconcile.</p></article>
      <article><span>Location review</span><p>Coordinates are missing, outside broad bounds, reused, or conflict with labels.</p></article>
      <article><span>Identity conflict</span><p>Exact identifier evidence points to conflicting secondary records.</p></article>
      <article><span>Coverage gap</span><p>Exact secondary evidence, coordinates, or source images are unavailable or conflict.</p></article>
      <article><span>Repeat family</span><p>A normalized project family appears across years or records and may represent phases.</p></article>
    </div>
  </section>
  <section class="services-desk" data-public-services-desk>
    <header><div><p class="kicker">Search the classified records</p><h2>Inspect the record and its evidence.</h2></div><p>Amounts remain labelled by source. A budget-stage amount and a delivery contract budget are not interchangeable and are never summed here.</p></header>
    <form data-services-form class="services-controls" role="search">
      <label>Search<input name="q" type="search" maxlength="200" placeholder="School, hospital, place, office…"></label>
      <label>Source<select name="source">${option('all', 'All record sources')}${option('budget', 'Budget-stage rows')}${option('delivery', 'Delivery contracts')}</select></label>
      <label>Facility<select name="facility">${option('all', 'All facilities')}${option('school', 'Schools')}${option('hospital', 'Hospitals')}${option('health_center', 'Health centers')}</select></label>
      <label>Work type<select name="work">${option('all', 'All work types')}${option('new_build', 'New build')}${option('rehabilitation', 'Rehabilitation')}${option('expansion', 'Expansion')}${option('equipment', 'Equipment')}${option('continuation', 'Continuation or phase')}${option('unspecified', 'Unspecified')}</select></label>
      <label>Review flag<select name="flag">${option('all', 'All records')}${option('with_flags', 'With any flag')}${option('without_flags', 'Without flags')}${option('stage_change', 'Stage change')}${option('record_contradiction', 'Record contradiction')}${option('location_review', 'Location review')}${option('identity_conflict', 'Identity conflict')}${option('coverage_gap', 'Coverage gap')}${option('repeat_family', 'Repeat family')}</select></label>
      <label>Sort<select name="sort">${option('amount_desc', 'Largest amount')}${option('year_desc', 'Newest fiscal year')}${option('flags_desc', 'Most review flags')}${option('title_asc', 'Title A to Z')}</select></label>
      <button type="submit">Apply filters</button><button type="button" class="secondary-control" data-services-reset>Reset</button>
    </form>
    <div class="services-result-summary" aria-live="polite"><p><strong data-services-count>0</strong> of <span data-services-total>0</span> records shown</p><p data-services-status>Loading classified records…</p></div>
    <div class="services-results" data-services-results></div>
    <div class="services-actions"><button type="button" data-services-more hidden>Load more</button></div>
    <noscript><p class="services-error">JavaScript is required for interactive filtering. The evidence desks remain available from the main navigation.</p></noscript>
  </section>
  <section class="services-method"><div><p class="kicker">What this can establish</p><h2>Precise wording, limited claim.</h2></div><div><p><strong>Included:</strong> explicit facility terms in an acquired title, a transparent work-type rule, source-specific money, and deterministic evidence flags.</p><p><strong>Not established:</strong> a unique-facility count, physical existence, completion, payment, engineering quality, service readiness, or measured public benefit.</p></div><a href="/methodology/">Read the evidence method <span aria-hidden="true">→</span></a></section>`;
};
