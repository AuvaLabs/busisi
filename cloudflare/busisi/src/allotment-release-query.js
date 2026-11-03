import { QueryError } from './query.js';

const MAX_QUERY_TEXT = 200;
const MAX_LIMIT = 100;
const LEVELS = Object.freeze(['all', 'departments', 'attached', 'special']);
const BANDS = Object.freeze(['all', 'below_50', 'below_90', '90_to_100', 'over_100', 'unreleased']);
const SORTS = Object.freeze({
  balance_desc: ['a.balance_centavos', 'DESC'],
  release_desc: ['a.release_centavos', 'DESC'],
  program_desc: ['a.adjusted_program_centavos', 'DESC'],
  rate_asc: ['a.release_bps', 'ASC'],
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

const fingerprint = (query) => [query.q, query.level, query.band, query.sort].join('|');

export const parseAllotmentReleaseQuery = (url) => {
  const q = (url.searchParams.get('q') || '').trim();
  const level = url.searchParams.get('level') || 'departments';
  const band = url.searchParams.get('band') || 'all';
  const sort = url.searchParams.get('sort') || 'balance_desc';
  const limit = parseInteger(url.searchParams.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (q.length > MAX_QUERY_TEXT) throw new QueryError('q is too long');
  if (!LEVELS.includes(level)) throw new QueryError('level is invalid');
  if (!BANDS.includes(band)) throw new QueryError('band is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = { q, level, band, sort, limit, offset: 0 };
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
  if (query.level === 'departments') clauses.push("a.level = 'department'");
  if (query.level === 'attached') clauses.push("a.level IN ('attached_agency', 'subunit')");
  if (query.level === 'special') clauses.push("a.level = 'special_purpose_fund'");
  if (query.band === 'below_50') clauses.push('a.release_bps < 5000');
  if (query.band === 'below_90') clauses.push('a.release_bps < 9000');
  if (query.band === '90_to_100') clauses.push('a.release_bps BETWEEN 9000 AND 10000');
  if (query.band === 'over_100') clauses.push('a.release_bps > 10000');
  if (query.band === 'unreleased') clauses.push('a.adjusted_program_centavos > 0 AND a.release_centavos = 0');
  return { clauses, bindings };
};

export const queryAllotmentReleases = async (database, query) => {
  const { clauses, bindings } = filters(query);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [field, direction] = SORTS[query.sort];
  const count = await database.prepare(
    `SELECT COUNT(*) AS total FROM allotment_release_items a ${where}`,
  ).bind(...bindings).first();
  const result = await database.prepare(`
    SELECT a.*, p.name AS parent_name
    FROM allotment_release_items a
    LEFT JOIN allotment_release_items p ON p.record_id = a.parent_id
    ${where}
    ORDER BY ${field} ${direction}, a.record_id ASC
    LIMIT ? OFFSET ?
  `).bind(...bindings, query.limit, query.offset).all();
  const records = (result.results || []).map((record) => ({
    ...record,
    source_reader_url: '/releases/#source',
  }));
  const nextOffset = query.offset + records.length;
  const nextCursor = nextOffset < Number(count.total)
    ? encodeCursor({ v: 1, offset: nextOffset, fingerprint: fingerprint(query) })
    : null;
  return Object.freeze({ records, total: Number(count.total), nextCursor });
};

const NUMERIC_METADATA = new Set([
  'fiscal_year', 'record_count', 'department_count', 'attached_agency_count',
  'special_purpose_fund_count', 'current_gaa_adjusted_centavos',
  'current_gaa_releases_centavos', 'current_gaa_balance_centavos',
  'total_program_centavos', 'total_releases_centavos', 'total_balance_centavos',
]);

export const getAllotmentReleaseSummary = async (database) => {
  const result = await database.prepare(
    'SELECT key, value FROM allotment_release_metadata ORDER BY key',
  ).all();
  return Object.fromEntries((result.results || []).map((row) => [
    row.key,
    NUMERIC_METADATA.has(row.key) ? Number(row.value) : row.value,
  ]));
};
