import { QueryError } from './query.js';

const MAX_LIMIT = 100;
const MAX_TEXT = 200;
const MIN_YEAR = 2000;
const MAX_YEAR = 2100;
const RELATIONSHIPS = new Set(['all', 'sole', 'joint']);
const SIGNALS = new Set(['all', 'with_signals', 'without_signals']);
const SORTS = Object.freeze({
  budget_desc: ['d.budget_centavos', 'DESC'],
  year_desc: ['d.fiscal_year', 'DESC'],
  contract_asc: ['d.contract_id', 'ASC'],
});

const integer = (value, field, fallback = null) => {
  if (value === null || value === '') return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${field} is invalid`);
  return Number(value);
};

const boundedText = (url, field) => {
  const value = (url.searchParams.get(field) || '').trim();
  if (value.length > MAX_TEXT) throw new QueryError(`${field} is too long`);
  return value;
};

const fingerprint = (query) => [
  query.year,
  query.relationship,
  query.status,
  query.signal,
  query.sort,
].join('|');

const decodeCursor = (value, expected) => {
  if (!value) return 0;
  try {
    const payload = JSON.parse(atob(value.replaceAll('-', '+').replaceAll('_', '/')));
    if (payload.v !== 1 || !Number.isInteger(payload.offset) || payload.offset < 0) {
      throw new Error();
    }
    if (payload.fingerprint !== expected) throw new Error();
    return payload.offset;
  } catch {
    throw new QueryError('cursor is invalid for this query');
  }
};

const encodeCursor = (offset, query) => btoa(JSON.stringify({
  v: 1,
  offset,
  fingerprint: fingerprint(query),
})).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');

export const parseContractorProjectQuery = (url) => {
  const year = integer(url.searchParams.get('year'), 'year');
  const relationship = url.searchParams.get('relationship') || 'all';
  const status = boundedText(url, 'status');
  const signal = url.searchParams.get('signal') || 'all';
  const sort = url.searchParams.get('sort') || 'budget_desc';
  const limit = integer(url.searchParams.get('limit'), 'limit', 25);
  if (year !== null && (year < MIN_YEAR || year > MAX_YEAR)) {
    throw new QueryError('year is outside the supported range');
  }
  if (!RELATIONSHIPS.has(relationship)) throw new QueryError('relationship is invalid');
  if (!SIGNALS.has(signal)) throw new QueryError('signal is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  if (limit < 1 || limit > MAX_LIMIT) {
    throw new QueryError('limit is outside the supported range');
  }
  const query = { year, relationship, status, signal, sort, limit, offset: 0 };
  return Object.freeze({
    ...query,
    offset: decodeCursor(url.searchParams.get('cursor'), fingerprint(query)),
  });
};

const filters = (contractorKey, query) => {
  const clauses = ['association.contractor_key = ?'];
  const bindings = [contractorKey];
  if (query.year !== null) {
    clauses.push('d.fiscal_year = ?');
    bindings.push(query.year);
  }
  if (query.relationship !== 'all') {
    clauses.push('association.relationship = ?');
    bindings.push(query.relationship);
  }
  if (query.status) {
    clauses.push('LOWER(detail.status) = LOWER(?)');
    bindings.push(query.status);
  }
  if (query.signal !== 'all') {
    const operator = query.signal === 'with_signals' ? 'EXISTS' : 'NOT EXISTS';
    clauses.push(`${operator} (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = association.contract_id
    )`);
  }
  return { sql: `WHERE ${clauses.join(' AND ')}`, bindings };
};

const safeArray = (value) => {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const projectRecord = (row) => ({
  ...row,
  fiscal_year: Number(row.fiscal_year),
  budget_centavos: Number(row.budget_centavos),
  party_position: Number(row.party_position),
  party_count: Number(row.party_count),
  signal_count: Number(row.signal_count),
  contractor_parties: safeArray(row.contractor_parties_json),
  contractor_parties_json: undefined,
  reader_url: `/contracts/${encodeURIComponent(row.contract_id)}/`,
});

export const queryContractorProjects = async (database, contractorKey, query) => {
  const where = filters(contractorKey, query);
  const [sortField, direction] = SORTS[query.sort];
  const [total, result] = await Promise.all([
    database.prepare(`
      SELECT COUNT(*) AS total
      FROM contractor_project_associations association
      JOIN delivery_items d ON d.contract_id = association.contract_id
      JOIN delivery_project_details detail ON detail.contract_id = association.contract_id
      ${where.sql}
    `).bind(...where.bindings).first(),
    database.prepare(`
      SELECT association.party_position, association.party_count, association.relationship,
        d.contract_id, d.fiscal_year, d.description, d.budget_centavos, d.location,
        d.source_of_funds, detail.category, detail.status, detail.progress,
        detail.contractor_parties_json, detail.province, detail.region,
        acquisition.match_state,
        (SELECT COUNT(*) FROM integrity_signal_items signal
          WHERE signal.contract_id = association.contract_id) AS signal_count
      FROM contractor_project_associations association
      JOIN delivery_items d ON d.contract_id = association.contract_id
      JOIN delivery_project_details detail ON detail.contract_id = association.contract_id
      LEFT JOIN contract_acquisition_details acquisition
        ON acquisition.contract_id = association.contract_id
      ${where.sql}
      ORDER BY ${sortField} ${direction}, d.contract_id ASC
      LIMIT ? OFFSET ?
    `).bind(...where.bindings, query.limit, query.offset).all(),
  ]);
  const records = (result.results || []).map(projectRecord);
  const nextOffset = query.offset + records.length;
  return Object.freeze({
    total: Number(total.total),
    records,
    nextCursor: nextOffset < Number(total.total) ? encodeCursor(nextOffset, query) : null,
  });
};

export const getContractorAssociationSummary = async (database, contractorKey) => {
  const summary = await database.prepare(`
    SELECT COUNT(*) AS project_count,
      SUM(association.relationship = 'sole') AS sole_project_count,
      SUM(association.relationship = 'joint') AS joint_project_count,
      SUM(CASE WHEN association.relationship = 'sole' THEN d.budget_centavos ELSE 0 END)
        AS sole_budget_centavos,
      SUM(CASE WHEN association.relationship = 'joint' THEN d.budget_centavos ELSE 0 END)
        AS joint_budget_centavos,
      SUM(EXISTS (
        SELECT 1 FROM integrity_signal_items signal
        WHERE signal.contract_id = association.contract_id
      )) AS projects_with_signals
    FROM contractor_project_associations association
    JOIN delivery_items d ON d.contract_id = association.contract_id
    WHERE association.contractor_key = ?
  `).bind(contractorKey).first();
  return Object.fromEntries(Object.entries(summary || {}).map(([key, value]) => [
    key,
    Number(value || 0),
  ]));
};
