const rows = (result) => result.results || [];

const numericKeys = new Set([
  'award_signals',
  'blacklist_active',
  'blacklist_events',
  'blacklist_name_only',
  'cpes_events',
  'cpes_missing_or_unmatched_pcab',
]);

const metadata = (records) => Object.fromEntries(records.map(({ key, value }) => [
  key,
  numericKeys.has(key) ? Number(value) : value,
]));

export const getAccountabilitySummary = async (database) => {
  const result = await database.prepare(
    'SELECT key, value FROM accountability_metadata ORDER BY key ASC',
  ).all();
  return metadata(rows(result));
};

export const queryAccountabilityEvents = async (database) => {
  const result = await database.prepare(`
    SELECT 'official_restriction' AS event_type, order_id AS event_id, contractor_key,
      contractor_name, pcab_id, start_date AS event_date, status, procuring_entity AS agency,
      project_title, NULL AS rating_bps, NULL AS qualitative_rating,
      'https://onlineblacklistingportal.gppb.gov.ph/' AS source_url
    FROM contractor_blacklist_events
    UNION ALL
    SELECT 'low_cpes_rating' AS event_type, rating_id AS event_id, contractor_key,
      contractor_name, pcab_id, evaluation_date AS event_date, 'reported' AS status,
      implementing_agency AS agency, project_title, final_rating_bps AS rating_bps,
      qualitative_rating, source_url
    FROM contractor_cpes_events
    ORDER BY event_date DESC, event_id ASC
    LIMIT 100
  `).all();
  return rows(result);
};

export const getContractorAccountability = async (database, contractorKey) => {
  const [blacklists, ratings, signals] = await Promise.all([
    database.prepare(`
      SELECT * FROM contractor_blacklist_events
      WHERE contractor_key = ? ORDER BY start_date DESC, order_id ASC
    `).bind(contractorKey).all(),
    database.prepare(`
      SELECT * FROM contractor_cpes_events
      WHERE contractor_key = ? ORDER BY evaluation_date DESC, rating_id ASC
    `).bind(contractorKey).all(),
    database.prepare(`
      SELECT * FROM contractor_award_timing_signals
      WHERE contractor_key = ? ORDER BY award_date DESC, signal_id ASC
    `).bind(contractorKey).all(),
  ]);
  return {
    blacklist_events: rows(blacklists),
    cpes_events: rows(ratings),
    award_signals: rows(signals),
  };
};
