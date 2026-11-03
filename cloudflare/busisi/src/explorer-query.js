import { QueryError } from './query.js';
import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';
import {
  budgetRecordUrl,
  deliveryRecordUrl,
  gaaDocumentsUrl,
} from './source-presentation.js';

const MAX_QUERY_TEXT = 200;
const MAX_SOURCE_QUERY_TEXT = 40;
const MAX_LIMIT = 100;
const MIN_YEAR = 2000;
const MAX_YEAR = 2100;

const CONFIG = Object.freeze({
  budgets: {
    table: 'budget_items',
    alias: 'b',
    id: 'record_id',
    searchFields: ['description', 'family_label', 'budget_line_id'],
    sorts: {
      amount_desc: ['amount_centavos', 'DESC'],
      year_desc: ['fiscal_year', 'DESC'],
      title_asc: ['LOWER(description)', 'ASC'],
    },
    defaultSort: 'amount_desc',
  },
  delivery: {
    table: 'delivery_items',
    alias: 'd',
    id: 'contract_id',
    searchFields: ['description', 'location', 'source_of_funds', 'contract_id'],
    sorts: {
      budget_desc: ['budget_centavos', 'DESC'],
      year_desc: ['fiscal_year', 'DESC'],
      title_asc: ['LOWER(description)', 'ASC'],
    },
    defaultSort: 'budget_desc',
  },
  candidates: {
    table: 'candidate_links',
    alias: 'c',
    id: 'candidate_id',
    searchFields: ['budget_description', 'delivery_description', 'contract_id'],
    sorts: {
      score_desc: ['score', 'DESC'],
      difference_desc: ['difference_centavos', 'DESC'],
      year_desc: ['fiscal_year', 'DESC'],
    },
    defaultSort: 'score_desc',
  },
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

const encodeCursor = (payload) => btoa(JSON.stringify(payload))
  .replaceAll('+', '-')
  .replaceAll('/', '_')
  .replace(/=+$/, '');

const decodeCursor = (value) => {
  try {
    const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
    const payload = JSON.parse(atob(`${normalized}${'='.repeat((4 - normalized.length % 4) % 4)}`));
    if (payload.v !== 1 || !Number.isSafeInteger(payload.offset) || payload.offset < 0) {
      throw new Error('invalid cursor payload');
    }
    return payload;
  } catch (error) {
    throw new QueryError('cursor is invalid for this query');
  }
};

const fingerprint = (query) => [query.kind, query.q, query.year, query.sort, query.signal].join('|');

export const parseExplorerQuery = (url, kind) => {
  const config = CONFIG[kind];
  if (!config) throw new QueryError('collection is not available', 404);
  const q = (url.searchParams.get('q') || '').trim();
  const year = parseInteger(url.searchParams.get('year'), null, MIN_YEAR, MAX_YEAR, 'year');
  const limit = parseInteger(url.searchParams.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  const sort = url.searchParams.get('sort') || config.defaultSort;
  const signal = url.searchParams.get('signal') || 'all';
  if (q.length > MAX_QUERY_TEXT) throw new QueryError('q is too long');
  if (!Object.hasOwn(config.sorts, sort)) throw new QueryError('sort is invalid');
  if (!['all', 'zero_budget'].includes(signal) || (kind !== 'candidates' && signal !== 'all')) {
    throw new QueryError('signal is invalid');
  }
  const query = { kind, q, year, limit, sort, signal, offset: 0 };
  const cursor = url.searchParams.get('cursor');
  if (cursor) {
    const payload = decodeCursor(cursor);
    if (payload.fingerprint !== fingerprint(query)) {
      throw new QueryError('cursor is invalid for this query');
    }
    query.offset = payload.offset;
  }
  return Object.freeze(query);
};

const filters = (query, config) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    clauses.push(`(${config.searchFields.map((field) => `LOWER(${config.alias}.${field}) LIKE ?`).join(' OR ')})`);
    const search = `%${query.q.toLocaleLowerCase('en')}%`;
    bindings.push(...config.searchFields.map(() => search));
  }
  if (query.year !== null) {
    clauses.push(`${config.alias}.fiscal_year = ?`);
    bindings.push(query.year);
  }
  if (query.signal === 'zero_budget') clauses.push('c.delivery_budget_centavos = 0');
  return { clauses, bindings };
};

const boundedSourceQuery = (value) => {
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (normalized.length <= MAX_SOURCE_QUERY_TEXT) return normalized;
  const prefix = normalized.slice(0, MAX_SOURCE_QUERY_TEXT + 1);
  const wordBoundary = prefix.lastIndexOf(' ');
  const bounded = wordBoundary >= 2
    ? prefix.slice(0, wordBoundary)
    : normalized.slice(0, MAX_SOURCE_QUERY_TEXT);
  return bounded.replace(/[\s,;:-]+$/, '');
};

const sourceBudgetUrl = (row) => {
  const agency = row.budget_line_id.split('|', 1)[0];
  const department = agency.split('-', 1)[0];
  const params = new URLSearchParams({
    q: boundedSourceQuery(row.description),
    agency_id: agency,
    year: String(row.fiscal_year),
    limit: '25',
  });
  return `https://budget.bettergov.ph/api/v1/gaa/departments/${encodeURIComponent(department)}/programs?${params.toString()}`;
};

const mapBudget = (row) => ({
  ...row,
  record_type: 'budget',
  source_url: sourceBudgetUrl(row),
  reader_source_url: `/records/budget/${encodeURIComponent(row.record_id)}/`,
  official_documents_url: gaaDocumentsUrl(row.fiscal_year),
});

const mapDelivery = (row) => ({
  ...row,
  record_type: 'delivery',
  district_context: districtContext(row),
  district_classification: undefined,
  district_office_name: undefined,
  districts_json: undefined,
  source_url: `https://api.dpwh.bettergov.ph/projects/${encodeURIComponent(row.contract_id)}`,
  reader_source_url: deliveryRecordUrl(row.contract_id),
});

const mapCandidate = (row) => ({
  ...row,
  record_type: 'candidate',
  signals: JSON.parse(row.signals_json),
  signals_json: undefined,
  budget_reader_url: budgetRecordUrl(row.budget_description, row.fiscal_year),
  delivery_reader_url: deliveryRecordUrl(row.contract_id),
  review_url: `/records/candidate/${encodeURIComponent(row.candidate_id)}/`,
});

const MAPPERS = Object.freeze({ budgets: mapBudget, delivery: mapDelivery, candidates: mapCandidate });

export const queryExplorer = async (database, query) => {
  const config = CONFIG[query.kind];
  const { clauses, bindings } = filters(query, config);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [field, direction] = config.sorts[query.sort];
  const count = await database
    .prepare(`SELECT COUNT(*) AS total FROM ${config.table} ${config.alias} ${where}`)
    .bind(...bindings)
    .first();
  const deliveryJoin = query.kind === 'delivery'
    ? districtOfficeJoin("CASE WHEN INSTR(d.location, ',') > 0 THEN SUBSTR(d.location, 1, INSTR(d.location, ',') - 1) ELSE d.location END")
    : '';
  const districtSelect = query.kind === 'delivery' ? `, ${DISTRICT_SELECT}` : '';
  const result = await database.prepare(
    `SELECT ${config.alias}.*${districtSelect} FROM ${config.table} ${config.alias} ${deliveryJoin} ${where} ORDER BY ${field} ${direction}, ${config.alias}.${config.id} ASC LIMIT ? OFFSET ?`,
  ).bind(...bindings, query.limit, query.offset).all();
  const records = (result.results || []).map(MAPPERS[query.kind]);
  const nextOffset = query.offset + records.length;
  const nextCursor = nextOffset < Number(count.total)
    ? encodeCursor({ v: 1, offset: nextOffset, fingerprint: fingerprint(query) })
    : null;
  return Object.freeze({ records, total: Number(count.total), nextCursor });
};

export const getExplorerStats = async (database) => {
  const result = await database.prepare('SELECT key, value FROM public_metadata').all();
  const numeric = new Set(['budget_records', 'delivery_records', 'candidate_links', 'schema_version']);
  const metadata = Object.fromEntries(
    (result.results || []).map((row) => [row.key, numeric.has(row.key) ? Number(row.value) : row.value]),
  );
  const reviewed = await database.prepare('SELECT COUNT(*) AS total FROM projects').first();
  return Object.freeze({ ...metadata, reviewed_dossiers: Number(reviewed.total) });
};
