const number = (value) => Number(value || 0).toLocaleString('en-PH');
const html = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const array = (value) => (Array.isArray(value) ? value : []);

const plainPublicText = (value) => String(value ?? '')
  .replace(/\bunattended acquisition\b/gi, 'automatic download')
  .replace(/\bacquisition\b/gi, 'download')
  .replace(/\bdeterministic\b/gi, 'rule-based')
  .replace(/\breconciled\b/gi, 'checked');

const sourceStatusSection = (source) => {
  if (!source) return `<section class="standards-grid"><article class="standard-panel"><p class="kicker">Source check</p><h2>No new source check is available</h2><p>Busisi can still show its dated records, but it cannot say whether the source changed after that date.</p></article></section>`;
  const drift = source.status !== 'unchanged';
  const differences = array(source.differences);
  const limitations = array(source.limitations);
  return `<section class="standards-grid"><article class="standard-panel"><p class="kicker">Did the sources change?</p><h2>${drift ? 'A source changed and needs checking' : 'The checked sources have not changed'}</h2><p>Last checked ${html(source.checked_at)}. ${drift ? `${number(differences.length)} change or download problem${differences.length === 1 ? '' : 's'} need${differences.length === 1 ? 's' : ''} checking. Busisi keeps the last good copy online until the change is understood.` : 'The source pages and lists still match the copies used by Busisi.'}</p>${differences.length ? `<ul>${differences.map((item) => `<li>${html(plainPublicText(item))}</li>`).join('')}</ul>` : ''}</article><article class="standard-panel"><p class="kicker">What Busisi could not check</p><h2>${number(limitations.length)} known limit${limitations.length === 1 ? '' : 's'}</h2>${limitations.length ? `<ul>${limitations.map((item) => `<li>${html(item.source)}: ${html(plainPublicText(item.effect))}</li>`).join('')}</ul>` : '<p>No other source limit was reported.</p>'}<details><summary>Saved source check code</summary><p><small>${html(source.observations_sha256)}</small></p></details></article></section>`;
};

export const coverageStatusBody = (record, source = null) => {
  if (!record) {
    return `<section class="data-intro"><div><p class="kicker">Progress of source checks</p><h1>No checked coverage update is available.</h1><p class="lede">Busisi keeps the last records that passed its checks. It does not publish an unfinished update.</p></div></section>`;
  }
  const completion = record.universe_contracts
    ? ((record.completed_contracts / record.universe_contracts) * 100).toFixed(1)
    : '0.0';
  return `
  <section class="data-intro"><div><p class="kicker">Progress of source checks</p><h1>See how many project images Busisi has checked.</h1><p class="lede">Busisi checks project-image records automatically. An image appears only after its source, file, and project count agree.</p></div><aside class="snapshot-card"><span>Latest checked update</span><strong>${completion}% reviewed</strong><p>${number(record.completed_contracts)} of ${number(record.universe_contracts)} contracts<br>${html(record.released_at)}</p><a href="/methodology/#coverage-automation">See how the checks work</a></aside></section>
  ${sourceStatusSection(source)}
  <section class="value-summary" aria-label="Coverage update summary"><article><span>Records that passed</span><strong>${number(record.verified_exact_contracts)}</strong><small>The project page and image list agree</small></article><article><span>Records reporting no images</span><strong>${number(record.no_image_contracts)}</strong><small>Both source views report zero images</small></article><article><span>Records held for checking</span><strong>${number(record.conflict_contracts)}</strong><small>The source counts or files do not agree</small></article><article><span>Still waiting or retrying</span><strong>${number(record.pending_contracts + record.retry_contracts + record.blocked_contracts)}</strong><small>Not published as checked evidence</small></article></section>
  <section class="standards-grid"><article class="standard-panel"><p class="kicker">Images shown on Busisi</p><h2>${number(record.verified_images)} checked images</h2><p>For each image, Busisi checked the DPWH source, file type, file size, dimensions, saved-file check code, and project image count.</p></article><article class="standard-panel"><p class="kicker">Images not shown</p><h2>${number(record.quarantined_images)} images held for checking</h2><p>When source counts or files do not agree, Busisi keeps the last good public update and does not show the new image as checked.</p></article></section>
  <section class="integrity-method"><div><p class="kicker">What this does not prove</p><h2>A source image is not the same as an on-site inspection.</h2></div><div><ul><li>The source provides the coordinates and time.</li><li>An image alone cannot prove completion, quality, payment, or public benefit.</li><li>A waiting or blocked record does not prove that anything is wrong.</li><li>No AI model decides whether an image is published.</li></ul><details><summary>Saved update details</summary><p><small>Update: ${html(record.release_id)}<br>Source-file check code: ${html(record.source_sha256)}</small></p></details></div></section>`;
};
