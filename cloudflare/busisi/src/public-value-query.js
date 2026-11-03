const NUMERIC_METADATA = new Set([
  'indicator_count',
  'improving_count',
  'pressure_count',
  'context_count',
  'fiscal_year',
  'baseline_year',
  'revenue_coverage_bps',
  'expenditure_per_capita_centavos',
]);

export const getPublicValueSummary = async (database) => {
  const result = await database.prepare('SELECT key, value FROM public_value_metadata').all();
  return Object.fromEntries((result.results || []).map((row) => [
    row.key,
    NUMERIC_METADATA.has(row.key) ? Number(row.value) : row.value,
  ]));
};

export const queryPublicValueIndicators = async (database) => {
  const result = await database.prepare(`
    SELECT * FROM public_value_indicators
    ORDER BY
      CASE category
        WHEN 'economy' THEN 1
        WHEN 'fiscal_space' THEN 2
        WHEN 'composition' THEN 3
        ELSE 4
      END,
      indicator_id ASC
  `).all();
  return result.results || [];
};
