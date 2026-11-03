const html = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const safeLink = (value) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.toString() : '';
  } catch {
    return '';
  }
};

const STATUS_LABELS = {
  verified_archived: 'Official source archived and verified',
  indexed_unarchived: 'Official source indexed, not archived',
  blocked: 'Official source indexed, archive blocked',
  secondary: 'Secondary mirror evidence',
  not_located: 'Target document not located',
};

const itemStatus = (item) => STATUS_LABELS[item.status] || item.status.replaceAll('_', ' ');

const sourceAction = (item) => {
  if (item.status === 'blocked') return `Try official source (last returned HTTP ${item.http_status})`;
  if (item.status === 'verified_archived') return 'Open official source';
  if (item.status === 'secondary') return 'Open secondary source';
  if (item.reported_date) return 'Open date-reporting source';
  return 'Open supporting source';
};

const dateLine = (item) => {
  if (!item.reported_date) return '';
  const prefix = item.status === 'not_located'
    ? 'Reported date, document missing'
    : item.date_kind === 'planned' ? 'Planned date' : 'Recorded date';
  return `<p class="lifecycle-date"><span>${html(prefix)}</span><strong>${html(item.reported_date)}</strong></p>`;
};

const sourceDetails = (item) => {
  const url = safeLink(item.source_url);
  const fingerprint = item.artifact_sha256
    ? `<p><span>Evidence SHA-256</span><code>${html(item.artifact_sha256)}</code></p>` : '';
  const revision = item.source_revision
    ? `<p><span>Source revision</span><code>${html(item.source_revision)}</code></p>` : '';
  const http = item.http_status && item.status === 'blocked'
    ? `<p><span>Last acquisition result</span><strong>HTTP ${item.http_status}</strong></p>` : '';
  const source = item.source_title
    ? `<p><span>Supporting source</span><strong>${html(item.source_title)}</strong></p>` : '';
  const action = url
    ? `<a href="${html(url)}" target="_blank" rel="noopener noreferrer">${html(sourceAction(item))}</a>` : '';
  return `${source}${http}${fingerprint}${revision}${action}`;
};

const compactItem = (item) => `<li class="lifecycle-item status-${html(item.status)}"><div><span>${html(item.title)}</span><b>${html(itemStatus(item))}</b></div>${dateLine(item)}</li>`;

const detailItem = (item) => `<li class="lifecycle-item lifecycle-detail status-${html(item.status)}"><header><span>${html(item.title)}</span><b>${html(itemStatus(item))}</b></header>${dateLine(item)}<p>${html(item.limitation)}</p><div class="lifecycle-source">${sourceDetails(item)}</div></li>`;

const grouped = (items) => items.reduce((result, item) => {
  const existing = result.get(item.contract_id) || [];
  result.set(item.contract_id, [...existing, item]);
  return result;
}, new Map());

export const contractEvidenceLedger = (summary, items) => {
  const metadata = summary?.metadata || {};
  const contracts = grouped(items);
  const legends = Object.entries(STATUS_LABELS).map(([status, label]) => (
    `<li class="status-${html(status)}"><span></span>${html(label)}</li>`
  )).join('');
  const cards = [...contracts.entries()].map(([contractId, records]) => {
    const first = records[0];
    const confirmed = records.filter((item) => item.status === 'verified_archived').length;
    return `<article class="lifecycle-card"><header><div><span>FY ${first.fiscal_year}</span><h3>${html(contractId)}</h3></div><strong>${confirmed} original document${confirmed === 1 ? '' : 's'} archived</strong></header><ol class="lifecycle-list">${records.map(compactItem).join('')}</ol><a href="/projects/${html(first.case_id)}/#contract-evidence">Open document checklist</a></article>`;
  }).join('');
  return `<section class="evidence-section" id="acquisition-ledger"><div class="section-heading-inline"><div><p class="kicker">Document acquisition</p><h2>Contract evidence acquisition ledger</h2><p>Every expected document has an explicit acquisition state. Reported dates remain separate from the underlying document.</p></div><aside><strong>${html(metadata.retry_item_count || '0')} acquisition checks queued</strong><span>${html(metadata.item_count || '0')} checks across ${html(metadata.contract_count || '0')} contracts</span></aside></div><ul class="evidence-status-legend" aria-label="Evidence status legend">${legends}</ul><div class="lifecycle-grid">${cards}</div></section>`;
};

export const contractEvidencePanel = (items = []) => {
  if (!items.length) return `<section class="evidence-section" id="contract-evidence"><p class="kicker">Document acquisition</p><h2>Contract evidence checklist</h2><p class="evidence-empty">No lifecycle document checklist is available for this dossier.</p></section>`;
  const archived = items.filter((item) => item.status === 'verified_archived').length;
  const retry = items.filter((item) => item.retry_eligible).length;
  return `<section class="evidence-section" id="contract-evidence"><p class="kicker">Document acquisition</p><h2>Contract evidence checklist</h2><p>${archived} of ${items.length} target documents is archived as an original official source. ${retry} acquisition check${retry === 1 ? '' : 's'} remain retryable.</p><ol class="lifecycle-list lifecycle-full">${items.map(detailItem).join('')}</ol><p class="evidence-limit">A reported event date is not a substitute for the signed contract, Notice to Proceed, completion certificate, inspection record, acceptance record, voucher, receipt, or payment confirmation.</p></section>`;
};
