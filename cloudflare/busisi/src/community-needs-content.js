const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const count = (value) => new Intl.NumberFormat('en-PH').format(Number(value) || 0);

const checkTime = (value) => {
  if (!value) return 'Not scheduled yet';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return html(value);
  return new Intl.DateTimeFormat('en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Manila',
  }).format(parsed);
};

const povertyStatus = (status) => {
  const ready = status?.source_state === 'validated';
  const published = status?.publication_state === 'published';
  const heading = published
    ? 'Checked poverty estimates are available.'
    : ready
      ? 'The official spreadsheet passed its checks.'
      : 'Poverty estimates are not published yet.';
  const explanation = status?.status_note
    || 'The automatic check will try the official spreadsheet again. No poverty estimate will appear until the complete file passes the required checks.';
  const next = status?.next_check_at
    ? `<p><strong>Next automatic check</strong><br><time datetime="${html(status.next_check_at)}">${checkTime(status.next_check_at)}</time></p>`
    : '<p><strong>Next automatic check</strong><br>Not scheduled yet</p>';
  return `<section class="needs-source-status"><div><p class="kicker">Poverty estimate status</p><h2>${heading}</h2><p>${html(explanation)}</p></div><aside><p><strong>Expected places</strong><br>${count(status?.expected_records || 1611)}</p><p><strong>Places that passed</strong><br>${count(status?.validated_records)}</p>${next}</aside></section>`;
};

export const communityNeedsBody = (status = null) => `
  <section class="data-intro needs-intro"><div><p class="kicker">Community needs</p><h1>What do communities need?</h1><p class="lede">Start with how many people and households live in each place, then compare that context with the public projects and budgets recorded there.</p></div><aside class="snapshot-card"><span>Available now</span><strong>2024 population and households</strong><p>Official Philippine Statistics Authority counts for regions, provinces, cities, municipalities, Manila districts, and barangays.</p><a href="https://openstat.psa.gov.ph/" rel="external">Visit PSA OpenSTAT</a></aside></section>
  <section class="needs-answer"><div><p class="kicker">How to read this</p><h2>Need is context, not an accusation.</h2></div><p>A large population, many households, or a service gap can help people ask whether public spending matches local conditions. It is not a red flag or a verdict about any project, agency, contractor, or public official.</p></section>
  <section class="needs-summary" aria-label="PSA population coverage"><article><span>People counted nationwide</span><strong data-needs-population>Loading...</strong><small>PSA national count, 1 July 2024</small></article><article><span>Households</span><strong data-needs-households>Loading...</strong><small>PSA national count</small></article><article><span>Places available</span><strong data-needs-places>Loading...</strong><small>Regions through barangays</small></article><article><span>Barangays available</span><strong data-needs-barangays>Loading...</strong><small>Official geographic labels</small></article></section>
  <section class="needs-shell" data-community-needs><form class="needs-controls" data-needs-form role="search"><label>Find a place<input type="search" name="q" maxlength="200" placeholder="Manila, Cebu, Siayan..."></label><label>Show<select name="level"><option value="city_or_municipality">Cities and municipalities</option><option value="province_or_huc">Provinces and highly urbanized cities</option><option value="region">Regions</option><option value="submunicipality">Manila districts</option><option value="barangay">Barangays</option><option value="all">All place levels</option></select></label><button type="submit">Search places</button></form><p class="needs-status" data-needs-status aria-live="polite">Loading official population context...</p><div class="needs-list" data-needs-results></div><noscript><p>JavaScript is required for this directory. The read-only community needs API remains available.</p></noscript></section>
  ${povertyStatus(status)}
  <section class="needs-limits"><article><p class="kicker">What we know</p><h2>Population is one part of need.</h2><p>The current release can show population, household population, and number of households. Every value keeps its PSA geographic code, date, and official source table.</p></article><article><p class="kicker">What needs checking</p><h2>National and regional totals differ by 1,708 people.</h2><p>PSA's national count is 112,729,484. The 18 regional tables add to 112,727,776. Busisi shows the difference and does not assign it to any region.</p></article><article><p class="kicker">What comes next</p><h2>Poverty and CBMS service needs.</h2><p>City and municipal poverty estimates can be added after their source file passes the same checks. Public Community-Based Monitoring System totals can add water, sanitation, schooling, work, electricity, internet, health, food, and disaster context. No information about individual families will be published.</p></article></section>
  <section class="needs-source-note"><div><p class="kicker">Where this information came from</p><h2>Philippine Statistics Authority</h2></div><p>These counts come from PSA OpenSTAT tables for the 2024 Census of Population. Busisi saved and checked all 18 regional tables against PSA's national total before publishing them.</p></section>`;
