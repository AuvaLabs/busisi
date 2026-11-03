import { QueryError } from './query.js';

const MAX_TEXT = 200;
const MAX_FACET_TEXT = 120;
const MAX_LIMIT = 100;
const MAX_EXPORT_ROWS = 10_000;
const STATES = new Set([
  'all', 'structured_exact', 'title_exact', 'multiple_exact_rows',
  'conflict_review', 'no_exact_row', 'invalid_identifier',
]);
const SIGNALS = new Set(['all', 'with_signals', 'without_signals']);
const BUDGETS = new Set([
  'all', 'under_10m', '10m_50m', '50m_100m', '100m_500m', '500m_plus',
]);
const SORTS = Object.freeze({
  budget_desc: ['d.budget_centavos', 'DESC'],
  year_desc: ['a.fiscal_year', 'DESC'],
  signals_desc: ['signal_count', 'DESC'],
  awards_desc: ['award_row_count', 'DESC'],
  contract_asc: ['a.contract_id', 'ASC'],
});
const BUDGET_RANGES = Object.freeze({
  under_10m: [null, 1_000_000_000],
  '10m_50m': [1_000_000_000, 5_000_000_000],
  '50m_100m': [5_000_000_000, 10_000_000_000],
  '100m_500m': [10_000_000_000, 50_000_000_000],
  '500m_plus': [50_000_000_000, null],
});

const parseInteger = (value, fallback, minimum, maximum, name) => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${name} is invalid`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new QueryError(`${name} is outside the supported range`);
  }
  return parsed;
};

const boundedText = (params, name, maximum = MAX_FACET_TEXT) => {
  const value = (params.get(name) || '').trim();
  if (value.length > maximum) throw new QueryError(`${name} is too long`);
  return value;
};

const fingerprint = (query) => [
  query.q, query.year, query.state, query.category, query.region, query.province, query.status,
  query.contractor, query.signal, query.budget, query.sort,
].join('|');

const encodeCursor = (query, offset) => btoa(JSON.stringify({
  v: 1, offset, fingerprint: fingerprint(query),
})).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');

const decodeCursor = (value, query) => {
  try {
    const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
    const padding = '='.repeat((4 - normalized.length % 4) % 4);
    const payload = JSON.parse(atob(`${normalized}${padding}`));
    if (payload.v !== 1 || !Number.isSafeInteger(payload.offset) || payload.offset < 0
      || payload.fingerprint !== fingerprint(query)) {
      throw new Error('invalid cursor payload');
    }
    return payload.offset;
  } catch {
    throw new QueryError('cursor is invalid for this query');
  }
};

export const parseContractIntelligenceQuery = (url) => {
  const params = url.searchParams;
  const q = boundedText(params, 'q', MAX_TEXT);
  const year = parseInteger(params.get('year'), null, 2000, 2100, 'year');
  const state = params.get('state') || 'all';
  const category = boundedText(params, 'category');
  const region = boundedText(params, 'region');
  const province = boundedText(params, 'province');
  const status = boundedText(params, 'status');
  const contractor = boundedText(params, 'contractor', MAX_TEXT);
  const signal = params.get('signal') || 'all';
  const budget = params.get('budget') || 'all';
  const sort = params.get('sort') || 'budget_desc';
  const limit = parseInteger(params.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (!STATES.has(state)) throw new QueryError('state is invalid');
  if (!SIGNALS.has(signal)) throw new QueryError('signal is invalid');
  if (!BUDGETS.has(budget)) throw new QueryError('budget is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = {
    q, year, state, category, region, province, status, contractor, signal, budget,
    sort, limit, offset: 0,
  };
  const cursor = params.get('cursor');
  if (cursor) query.offset = decodeCursor(cursor, query);
  return Object.freeze(query);
};

const filters = (query) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    const search = `%${query.q.toLocaleLowerCase('en')}%`;
    clauses.push(`(
      LOWER(a.contract_id) LIKE ? OR LOWER(d.description) LIKE ?
      OR LOWER(d.location) LIKE ? OR LOWER(detail.contractor_name) LIKE ?
      OR EXISTS (
        SELECT 1 FROM contract_award_matches search_award
        WHERE search_award.contract_id = a.contract_id
          AND LOWER(search_award.awardee_name) LIKE ?
      )
    )`);
    bindings.push(search, search, search, search, search);
  }
  if (query.year !== null) {
    clauses.push('a.fiscal_year = ?');
    bindings.push(query.year);
  }
  for (const [value, field] of [
    [query.state, 'a.match_state'], [query.category, 'detail.category'],
    [query.region, 'detail.region'], [query.province, 'detail.province'],
    [query.status, 'detail.status'],
  ]) {
    if (value && value !== 'all') {
      clauses.push(`${field} = ?`);
      bindings.push(value);
    }
  }
  if (query.contractor) {
    const search = `%${query.contractor.toLocaleLowerCase('en')}%`;
    clauses.push(`(
      LOWER(detail.contractor_name) LIKE ? OR EXISTS (
        SELECT 1 FROM contract_award_matches contractor_award
        WHERE contractor_award.contract_id = a.contract_id
          AND LOWER(contractor_award.awardee_name) LIKE ?
      )
    )`);
    bindings.push(search, search);
  }
  if (query.signal !== 'all') {
    const operator = query.signal === 'with_signals' ? 'EXISTS' : 'NOT EXISTS';
    clauses.push(`${operator} (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = a.contract_id
    )`);
  }
  if (query.budget !== 'all') {
    const [minimum, maximum] = BUDGET_RANGES[query.budget];
    if (minimum !== null) {
      clauses.push('d.budget_centavos >= ?');
      bindings.push(minimum);
    }
    if (maximum !== null) {
      clauses.push('d.budget_centavos < ?');
      bindings.push(maximum);
    }
  }
  return { clauses, bindings };
};

const SELECT = `
  SELECT a.contract_id, a.fiscal_year, a.identifier_status, a.year_alignment,
    a.match_state, a.accepted_match_rows, a.quarantined_match_rows,
    d.description, d.budget_centavos, d.location, d.source_of_funds,
    d.artifact_sha256, detail.category, detail.status, detail.progress,
    detail.contractor_name, detail.contractor_parties_json, detail.province, detail.region,
    (SELECT COUNT(*) FROM contract_award_matches award
      WHERE award.contract_id = a.contract_id) AS award_row_count,
    (SELECT GROUP_CONCAT(ordered_awards.awardee_name, ' | ') FROM (
      SELECT DISTINCT award.awardee_name FROM contract_award_matches award
      WHERE award.contract_id = a.contract_id ORDER BY award.awardee_name
    ) ordered_awards) AS awardee_names,
    (SELECT COUNT(*) FROM integrity_signal_items signal
      WHERE signal.contract_id = a.contract_id) AS signal_count,
    (SELECT GROUP_CONCAT(ordered_signals.code, ',') FROM (
      SELECT DISTINCT signal.code FROM integrity_signal_items signal
      WHERE signal.contract_id = a.contract_id ORDER BY signal.code
    ) ordered_signals) AS signal_codes
  FROM contract_acquisition_details a
  JOIN delivery_items d ON d.contract_id = a.contract_id
  LEFT JOIN delivery_project_details detail ON detail.contract_id = a.contract_id`;

const safeArray = (value) => {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const mapRecord = (row) => ({
  ...row,
  contractor_parties: safeArray(row.contractor_parties_json),
  contractor_parties_json: undefined,
  awardee_names: row.awardee_names || '',
  signal_codes: row.signal_codes ? row.signal_codes.split(',') : [],
  reader_url: `/contracts/${encodeURIComponent(row.contract_id)}/`,
});

export const queryContractIntelligence = async (database, query) => {
  const { clauses, bindings } = filters(query);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [field, direction] = SORTS[query.sort];
  const [count, result] = await Promise.all([
    database.prepare(`
      SELECT COUNT(*) AS total FROM contract_acquisition_details a
      JOIN delivery_items d ON d.contract_id = a.contract_id
      LEFT JOIN delivery_project_details detail ON detail.contract_id = a.contract_id
      ${where}
    `).bind(...bindings).first(),
    database.prepare(`
      ${SELECT} ${where}
      ORDER BY ${field} ${direction}, a.contract_id ASC LIMIT ? OFFSET ?
    `).bind(...bindings, query.limit, query.offset).all(),
  ]);
  const records = (result.results || []).map(mapRecord);
  const nextOffset = query.offset + records.length;
  const nextCursor = nextOffset < Number(count.total)
    ? encodeCursor(query, nextOffset)
    : null;
  return Object.freeze({ records, total: Number(count.total), nextCursor });
};

const facet = async (database, field) => {
  const result = await database.prepare(`
    SELECT ${field} AS value, COUNT(*) AS count
    FROM delivery_project_details
    WHERE ${field} <> '' GROUP BY ${field}
    ORDER BY count DESC, value ASC LIMIT 100
  `).all();
  return result.results || [];
};

export const getContractIntelligenceSummary = async (database) => {
  const [states, total, signals, categories, regions, provinces, statuses] = await Promise.all([
    database.prepare(`
      SELECT match_state AS state, COUNT(*) AS count
      FROM contract_acquisition_details GROUP BY match_state ORDER BY state
    `).all(),
    database.prepare(`
      SELECT COUNT(*) AS total_contracts, SUM(d.budget_centavos) AS budget_centavos
      FROM contract_acquisition_details a
      JOIN delivery_items d ON d.contract_id = a.contract_id
    `).first(),
    database.prepare(`
      SELECT COUNT(DISTINCT contract_id) AS count FROM integrity_signal_items
    `).first(),
    facet(database, 'category'),
    facet(database, 'region'),
    facet(database, 'province'),
    facet(database, 'status'),
  ]);
  return Object.freeze({
    total_contracts: Number(total.total_contracts),
    budget_centavos: Number(total.budget_centavos),
    contracts_with_signals: Number(signals.count),
    states: Object.fromEntries((states.results || []).map((item) => [
      item.state, Number(item.count),
    ])),
    facets: { categories, regions, provinces, statuses },
  });
};

const csvCell = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`;

export const exportContractIntelligenceCsv = async (database, query) => {
  const rows = [[
    'contract_id', 'match_state', 'fiscal_year', 'description', 'budget_centavos',
    'location', 'region', 'category', 'delivery_status', 'recorded_contractor',
    'secondary_awardees', 'accepted_secondary_rows', 'quarantined_secondary_rows',
    'integrity_signal_count', 'integrity_signal_codes', 'artifact_sha256', 'reader_url',
  ]];
  let cursor = null;
  do {
    const pageQuery = { ...query, limit: MAX_LIMIT, offset: 0 };
    if (cursor) pageQuery.offset = decodeCursor(cursor, pageQuery);
    const page = await queryContractIntelligence(database, pageQuery);
    for (const item of page.records) {
      rows.push([
        item.contract_id, item.match_state, item.fiscal_year, item.description,
        item.budget_centavos, item.location, item.region, item.category, item.status,
        item.contractor_name, item.awardee_names, item.accepted_match_rows,
        item.quarantined_match_rows, item.signal_count, item.signal_codes.join('|'),
        item.artifact_sha256, item.reader_url,
      ]);
      if (rows.length > MAX_EXPORT_ROWS) break;
    }
    cursor = rows.length > MAX_EXPORT_ROWS ? null : page.nextCursor;
  } while (cursor);
  return `${rows.map((row) => row.map(csvCell).join(',')).join('\n')}\n`;
};
