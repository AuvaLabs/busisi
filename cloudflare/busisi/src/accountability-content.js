const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const integer = (value) => Number(value || 0).toLocaleString('en-PH');
const profile = (key) => `/contractors/${encodeURIComponent(key)}/`;

const eventLabel = (event) => event.event_type === 'official_restriction'
  ? 'Official restriction record'
  : 'Official low CPES rating';

const eventMeaning = (event) => event.event_type === 'official_restriction'
  ? `GPPB reports a ${event.status} restriction beginning ${event.event_date}.`
  : `GPPB reports a ${event.qualitative_rating} final rating of ${(event.rating_bps / 100).toFixed(2)}%.`;

const eventCards = (events) => events.length ? events.map((event) => `
  <article class="accountability-card">
    <header><span>${html(eventLabel(event))}</span><time datetime="${html(event.event_date)}">${html(event.event_date)}</time></header>
    <h3><a href="${profile(event.contractor_key)}">${html(event.contractor_name)}</a></h3>
    <p><strong>What the official record says:</strong> ${html(eventMeaning(event))}</p>
    <p><strong>Record context:</strong> ${html(event.project_title)} · ${html(event.agency)}</p>
    <div><a href="${profile(event.contractor_key)}">Open evidence timeline</a><a href="${html(event.source_url)}" target="_blank" rel="noopener noreferrer">Open official publisher</a></div>
  </article>`).join('') : '<p class="evidence-empty">No strongly matched official accountability event is published.</p>';

export const accountabilityBody = (summary, events) => `
  <section class="data-intro"><div><p class="kicker">Contractor accountability</p><h1>Check the official record, then follow what happened next.</h1><p class="lede">Busisi links strongly matched contractor identities to official GPPB restriction records, official low performance ratings, and dated rows in an archived secondary award mirror.</p></div><aside class="snapshot-card"><span>Evidence checked</span><strong>${html(summary.checked_on || 'Not available')}</strong><p>${integer(summary.blacklist_events)} restriction records<br>${integer(summary.cpes_events)} low CPES ratings<br>${integer(summary.award_signals)} award-timing questions</p><a href="/methodology/">Read the evidence rules</a></aside></section>
  <section class="integrity-warning"><strong>This is not proof of corruption or an improper award.</strong><p>An official restriction or low performance rating is a narrow administrative record. An award-timing signal uses a secondary mirror row and tells readers what document to verify next.</p></section>
  <section class="evidence-section"><p class="kicker">Published matches</p><h2>Official events linked by exact identity evidence</h2><div class="accountability-grid">${eventCards(events)}</div></section>
  <section class="evidence-columns"><section class="evidence-panel"><p class="kicker">Why some names are absent</p><h2>Weak identity matches stay quarantined.</h2><p>${integer(summary.blacklist_name_only)} restriction-name matches and ${integer(summary.cpes_missing_or_unmatched_pcab)} CPES rows lack enough identity evidence for publication. Their names are not shown.</p></section><section class="evidence-panel"><p class="kicker">How to read an award-timing question</p><h2>Date overlap is a lead, not a verdict.</h2><p>Busisi requires an exact contractor identity, an exact archived award-mirror match, and a dated official event. Readers must still inspect the official procurement and award documents.</p></section></section>`;
