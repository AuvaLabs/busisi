const number = (value) => Number(value || 0).toLocaleString('en-PH');
const html = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

export const coverageStatusBody = (record) => {
  if (!record) {
    return `<section class="data-intro"><div><p class="kicker">Coverage automation</p><h1>Coverage release is not available.</h1><p class="lede">The public status record has not passed the release gate. Existing reviewed evidence remains available.</p></div></section>`;
  }
  const completion = record.universe_contracts
    ? ((record.completed_contracts / record.universe_contracts) * 100).toFixed(1)
    : '0.0';
  return `
  <section class="data-intro"><div><p class="kicker">Coverage automation</p><h1>See what the evidence pipeline has verified.</h1><p class="lede">This status describes deterministic project-image acquisition. A source hint enters the queue, but only archived and reconciled evidence can be published.</p></div><aside class="snapshot-card"><span>Latest gated release</span><strong>${completion}% reviewed</strong><p>${number(record.completed_contracts)} of ${number(record.universe_contracts)} contracts<br>${html(record.released_at)}</p><a href="/methodology/#coverage-automation">Read the controls</a></aside></section>
  <section class="value-summary" aria-label="Coverage release summary"><article><span>Exact reconciliations</span><strong>${number(record.verified_exact_contracts)}</strong><small>Detail and endpoint counts agree</small></article><article><span>Explicit no-image results</span><strong>${number(record.no_image_contracts)}</strong><small>Both source representations report zero</small></article><article><span>Quarantined conflicts</span><strong>${number(record.conflict_contracts)}</strong><small>Source counts disagree</small></article><article><span>Pending or retrying</span><strong>${number(record.pending_contracts + record.retry_contracts)}</strong><small>Not published as verified evidence</small></article></section>
  <section class="standards-grid"><article class="standard-panel"><p class="kicker">Published evidence</p><h2>${number(record.verified_images)} verified images</h2><p>Every published image uses the registered DPWH media origin and passed JPEG, byte-size, dimension, hash, and contract-level count checks.</p></article><article class="standard-panel"><p class="kicker">Fail-closed boundary</p><h2>${number(record.quarantined_images)} images withheld</h2><p>Conflicts and validation failures do not become verified evidence. The last passing release remains public when a candidate release regresses or changes immutable media.</p></article></section>
  <section class="integrity-method"><div><p class="kicker">What this does not prove</p><h2>An archived image is evidence of a source response, not a field inspection.</h2></div><div><ul><li>Source coordinates and timestamps remain source-reported.</li><li>An image does not independently prove physical completion, construction quality, payment, or public benefit.</li><li>Blocked and pending records are coverage gaps, not findings of wrongdoing.</li><li>No model or generative system decides publication status.</li></ul><p><small>Release fingerprint: ${html(record.release_id)}<br>Source snapshot: ${html(record.source_sha256)}</small></p></div></section>`;
};
