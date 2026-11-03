const resultRows = (result) => result.results || [];

const INTEGER_KEYS = new Set([
  'accepted_match_rows',
  'contract_count',
  'examined_contracts',
  'lifecycle_task_count',
  'quarantined_source_rows',
  'valid_identifiers',
  'year_alignment_conflicts',
]);

const integer = (value, key) => {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new TypeError(`invalid acquisition coverage integer: ${key}`);
  }
  return parsed;
};

const parseMetadata = (rows) => rows.reduce((coverage, { key, value }) => {
  if (key.startsWith('state:')) {
    coverage.states[key.slice(6)] = integer(value, key);
  } else if (key.startsWith('queue:')) {
    coverage.queue[key.slice(6)] = integer(value, key);
  } else if (key.startsWith('source:')) {
    const sourceKey = key.slice(7);
    coverage.source[sourceKey] = sourceKey === 'award_source_archived'
      ? value === 'true'
      : INTEGER_KEYS.has(sourceKey) || sourceKey.endsWith('_rows')
        || sourceKey.endsWith('_size')
        ? integer(value, key)
        : value;
  } else if (INTEGER_KEYS.has(key)) {
    coverage.summary[key] = integer(value, key);
  } else {
    coverage.summary[key] = value;
  }
  return coverage;
}, { summary: {}, states: {}, queue: {}, source: {} });

const breakdown = (row) => ({
  value: row.value,
  total_contracts: integer(row.total_contracts, `${row.dimension}:total_contracts`),
  state_counts: {
    structured_exact: integer(row.structured_exact, `${row.dimension}:structured_exact`),
    title_exact: integer(row.title_exact, `${row.dimension}:title_exact`),
    multiple_exact_rows: integer(row.multiple_exact_rows, `${row.dimension}:multiple_exact_rows`),
    conflict_review: integer(row.conflict_review, `${row.dimension}:conflict_review`),
    no_exact_row: integer(row.no_exact_row, `${row.dimension}:no_exact_row`),
    invalid_identifier: integer(row.invalid_identifier, `${row.dimension}:invalid_identifier`),
  },
});

export const getAcquisitionCoverage = async (database) => {
  const [metadata, breakdowns] = await Promise.all([
    database.prepare(
      'SELECT key, value FROM acquisition_universe_metadata ORDER BY key',
    ).all(),
    database.prepare(`
      SELECT dimension, value, total_contracts, structured_exact, title_exact,
        multiple_exact_rows, conflict_review, no_exact_row, invalid_identifier
      FROM acquisition_universe_breakdowns
      ORDER BY dimension, total_contracts DESC, value
    `).all(),
  ]);
  const coverage = parseMetadata(resultRows(metadata));
  const records = resultRows(breakdowns);
  return {
    ...coverage,
    years: records.filter(({ dimension }) => dimension === 'fiscal_year').map(breakdown),
    categories: records.filter(({ dimension }) => dimension === 'category').map(breakdown),
  };
};
