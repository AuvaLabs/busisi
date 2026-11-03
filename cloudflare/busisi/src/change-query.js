import { QueryError } from './query.js';
import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';

const MAX_QUERY_TEXT = 200;
const MAX_LIMIT = 100;
const DATASETS = Object.freeze(['all', 'dpwh', 'fmr', 'hfep', 'nia']);
const CHANGE_TYPES = Object.freeze([
  'all', 'house_only', 'nep_only', 'unchanged', 'increased', 'decreased', 'scope_review',
]);
const REVIEW_STATES = Object.freeze(['all', 'candidate', 'quarantine']);
const SORTS = Object.freeze({
  absolute_desc: ['ABS(c.difference_centavos)', 'DESC'],
  house_desc: ['c.house_centavos', 'DESC'],
  increase_desc: ['c.difference_centavos', 'DESC'],
  decrease_desc: ['c.difference_centavos', 'ASC'],
  title_asc: ['LOWER(c.title)', 'ASC'],
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
    const padding = '='.repeat((4 - normalized.length % 4) % 4);
    const payload = JSON.parse(atob(`${normalized}${padding}`));
    if (payload.v !== 1 || !Number.isSafeInteger(payload.offset) || payload.offset < 0) {
      throw new Error('invalid cursor');
    }
    return payload;
  } catch (error) {
    throw new QueryError('cursor is invalid for this query');
  }
};

const fingerprint = (query) => [
  query.q, query.dataset, query.change, query.region, query.review, query.sort,
].join('|');

export const parseChangeQuery = (url) => {
  const q = (url.searchParams.get('q') || '').trim();
  const dataset = url.searchParams.get('dataset') || 'all';
  const change = url.searchParams.get('change') || 'all';
  const region = (url.searchParams.get('region') || '').trim();
  const review = url.searchParams.get('review') || 'all';
  const sort = url.searchParams.get('sort') || 'absolute_desc';
  const limit = parseInteger(url.searchParams.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (q.length > MAX_QUERY_TEXT) throw new QueryError('q is too long');
  if (region.length > MAX_QUERY_TEXT) throw new QueryError('region is too long');
  if (!DATASETS.includes(dataset)) throw new QueryError('dataset is invalid');
  if (!CHANGE_TYPES.includes(change)) throw new QueryError('change is invalid');
  if (!REVIEW_STATES.includes(review)) throw new QueryError('review is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = { q, dataset, change, region, review, sort, limit, offset: 0 };
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

const filters = (query) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    const search = `%${query.q.toLocaleLowerCase('en')}%`;
    clauses.push('(LOWER(c.title) LIKE ? OR LOWER(c.program) LIKE ? OR LOWER(c.office) LIKE ?)');
    bindings.push(search, search, search);
  }
  if (query.dataset !== 'all') {
    clauses.push('c.dataset = ?');
    bindings.push(query.dataset);
  }
  if (query.change !== 'all') {
    clauses.push('c.change_type = ?');
    bindings.push(query.change);
  }
  if (query.region) {
    clauses.push('c.region = ?');
    bindings.push(query.region);
  }
  if (query.review !== 'all') {
    clauses.push('c.review_status = ?');
    bindings.push(query.review);
  }
  return { clauses, bindings };
};

export const queryChanges = async (database, query) => {
  const { clauses, bindings } = filters(query);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [field, direction] = SORTS[query.sort];
  const count = await database
    .prepare(`SELECT COUNT(*) AS total FROM stage_change_items c ${where}`)
    .bind(...bindings)
    .first();
  const districtJoin = districtOfficeJoin('c.office');
  const result = await database.prepare(
    `SELECT c.*, ${DISTRICT_SELECT} FROM stage_change_items c ${districtJoin} ${where} ORDER BY ${field} ${direction}, c.record_id ASC LIMIT ? OFFSET ?`,
  ).bind(...bindings, query.limit, query.offset).all();
  const records = (result.results || []).map((row) => ({
    ...row,
    district_context: districtContext(row),
    district_classification: undefined,
    district_office_name: undefined,
    districts_json: undefined,
  }));
  const nextOffset = query.offset + records.length;
  const nextCursor = nextOffset < Number(count.total)
    ? encodeCursor({ v: 1, offset: nextOffset, fingerprint: fingerprint(query) })
    : null;
  return Object.freeze({ records, total: Number(count.total), nextCursor });
};

export const getChangeStats = async (database) => {
  const result = await database.prepare('SELECT key, value FROM stage_change_metadata').all();
  const numeric = new Set(['record_count', 'quarantine_count', 'fiscal_year']);
  return Object.fromEntries(
    (result.results || []).map((row) => [row.key, numeric.has(row.key) ? Number(row.value) : row.value]),
  );
};
