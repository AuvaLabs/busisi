import { QueryError } from './query.js';

const MAX_QUERY_TEXT = 200;
const MAX_LIMIT = 100;
const LEVELS = Object.freeze(['all', 'heads', 'congress']);
const DIRECTIONS = Object.freeze(['all', 'increase', 'decrease', 'unchanged', 'unavailable']);
const SORTS = Object.freeze({
  difference_desc: ['a.difference_centavos', 'DESC'],
  difference_asc: ['a.difference_centavos', 'ASC'],
  house_desc: ['a.house_centavos', 'DESC'],
  nep_desc: ['a.nep_centavos', 'DESC'],
  name_asc: ['LOWER(a.name)', 'ASC'],
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
  .replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');

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

const fingerprint = (query) => [query.q, query.level, query.direction, query.sort].join('|');

export const parseAgencyQuery = (url) => {
  const q = (url.searchParams.get('q') || '').trim();
  const level = url.searchParams.get('level') || 'heads';
  const direction = url.searchParams.get('direction') || 'all';
  const sort = url.searchParams.get('sort') || 'difference_desc';
  const limit = parseInteger(url.searchParams.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (q.length > MAX_QUERY_TEXT) throw new QueryError('q is too long');
  if (!LEVELS.includes(level)) throw new QueryError('level is invalid');
  if (!DIRECTIONS.includes(direction)) throw new QueryError('direction is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = { q, level, direction, sort, limit, offset: 0 };
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
    clauses.push('(LOWER(a.name) LIKE ? OR LOWER(a.code) LIKE ?)');
    const search = `%${query.q.toLocaleLowerCase('en')}%`;
    bindings.push(search, search);
  }
  if (query.level === 'heads') clauses.push("a.level = 'appropriation_head'");
  if (query.level === 'congress') clauses.push("a.level = 'congress_institution'");
  if (query.direction === 'increase') clauses.push('a.difference_centavos > 0');
  if (query.direction === 'decrease') clauses.push('a.difference_centavos < 0');
  if (query.direction === 'unchanged') clauses.push('a.difference_centavos = 0');
  if (query.direction === 'unavailable') clauses.push("a.stage_status = 'not_applicable'");
  return { clauses, bindings };
};

const parsePages = (value) => {
  try {
    const pages = JSON.parse(value);
    return Array.isArray(pages) && pages.every(Number.isSafeInteger) ? pages : [];
  } catch (error) {
    return [];
  }
};

export const queryAgencyBudgets = async (database, query) => {
  const { clauses, bindings } = filters(query);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [field, direction] = SORTS[query.sort];
  const count = await database.prepare(
    `SELECT COUNT(*) AS total FROM agency_budget_items a ${where}`,
  ).bind(...bindings).first();
  const result = await database.prepare(
    `SELECT a.* FROM agency_budget_items a ${where} ORDER BY ${field} ${direction}, a.record_id ASC LIMIT ? OFFSET ?`,
  ).bind(...bindings, query.limit, query.offset).all();
  const records = (result.results || []).map((row) => ({
    ...row,
    house_pages: parsePages(row.house_pages_json),
    house_pages_json: undefined,
  }));
  const nextOffset = query.offset + records.length;
  const nextCursor = nextOffset < Number(count.total)
    ? encodeCursor({ v: 1, offset: nextOffset, fingerprint: fingerprint(query) })
    : null;
  return Object.freeze({ records, total: Number(count.total), nextCursor });
};

export const getAgencyBudgetSummary = async (database) => {
  const result = await database.prepare('SELECT key, value FROM agency_budget_metadata').all();
  return Object.fromEntries(
    (result.results || []).map((row) => [row.key, Number(row.value)]),
  );
};
