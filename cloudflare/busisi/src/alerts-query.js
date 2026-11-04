const rows = (result) => result.results || [];

const day = (value) => (String(value).includes('T') ? String(value) : `${value}T00:00:00Z`);

const sourceAlerts = async (database) => {
  const record = await database.prepare(`
    SELECT checked_at, status, differences_json
    FROM source_monitor_status WHERE singleton_id = 1
  `).first();
  if (!record) return [];
  const differences = JSON.parse(record.differences_json);
  const changed = record.status !== 'unchanged';
  return [{
    id: `source-check:${record.checked_at}`,
    kind: 'source_check',
    title: changed ? 'A monitored source needs checking' : 'Latest source check completed',
    summary: changed
      ? differences.join(' ') || 'A source could not be acquired or validated.'
      : 'No monitored revision or control-total change was detected.',
    url: '/watch/',
    published_at: day(record.checked_at),
    boundary: 'A source change is not automatically an error or a finding.',
  }];
};

const coverageAlerts = async (database) => {
  const record = await database.prepare(`
    SELECT release_id, released_at, completed_contracts, universe_contracts,
      verified_images, quarantined_images
    FROM coverage_releases ORDER BY released_at DESC, release_id DESC LIMIT 1
  `).first();
  if (!record) return [];
  return [{
    id: `coverage-release:${record.release_id}`,
    kind: 'coverage_release',
    title: `Evidence coverage reached ${Number(record.completed_contracts).toLocaleString('en-PH')} contracts`,
    summary: `${Number(record.verified_images).toLocaleString('en-PH')} source images passed the release gate; ${Number(record.quarantined_images).toLocaleString('en-PH')} remain held for checking.`,
    url: '/coverage/',
    published_at: day(record.released_at),
    boundary: `Coverage is ${Number(record.completed_contracts).toLocaleString('en-PH')} of ${Number(record.universe_contracts).toLocaleString('en-PH')} contracts, not the full universe.`,
  }];
};

const evidenceAlerts = async (database) => {
  const result = await database.prepare(`
    SELECT evidence_id, contract_id, title, status, last_checked_at, limitation
    FROM contract_evidence_items
    WHERE status IN ('verified_archived', 'secondary')
    ORDER BY last_checked_at DESC, contract_id, stage_order LIMIT 10
  `).all();
  return rows(result).map((record) => ({
    id: `contract-evidence:${record.evidence_id}`,
    kind: 'contract_evidence',
    title: `${record.title} checked for contract ${record.contract_id}`,
    summary: record.status === 'verified_archived'
      ? 'The acquired official artifact passed archive and identity checks.'
      : 'An exact row from a versioned secondary mirror is retained.',
    url: `/contracts/${encodeURIComponent(record.contract_id)}/#evidence-checklist`,
    published_at: day(record.last_checked_at),
    boundary: record.limitation,
  }));
};

const questionAlerts = async (database) => {
  const result = await database.prepare(`
    SELECT signal.signal_id, signal.contract_id, signal.label, signal.evidence,
      metadata.value AS source_as_of
    FROM integrity_signal_items signal
    JOIN integrity_metadata metadata ON metadata.key = 'source_as_of'
    ORDER BY signal.budget_centavos DESC, signal.signal_id LIMIT 10
  `).all();
  return rows(result).map((record) => ({
    id: `review-question:${record.signal_id}`,
    kind: 'review_question',
    title: `${record.label}: ${record.contract_id}`,
    summary: record.evidence,
    url: `/contracts/${encodeURIComponent(record.contract_id)}/#questions`,
    published_at: day(record.source_as_of),
    boundary: 'A review question is not a finding of wrongdoing.',
  }));
};

export const getAlertFeed = async (database) => {
  const groups = await Promise.all([
    sourceAlerts(database),
    coverageAlerts(database),
    evidenceAlerts(database),
    questionAlerts(database),
  ]);
  return Object.freeze(groups.flat().sort((left, right) => (
    right.published_at.localeCompare(left.published_at) || left.id.localeCompare(right.id)
  )).slice(0, 30));
};
