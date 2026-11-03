const MAX_QUERY_TEXT = 200;
const MAX_QUERY_LIMIT = 100;
const MAX_EXPORT_ROWS = 10_000;
const MIN_YEAR = 2000;
const MAX_YEAR = 2100;

const SORTS = Object.freeze({
  appropriation_desc: ['p.appropriation_centavos', 'DESC', 'integer'],
  difference_desc: ['p.variance_centavos', 'DESC', 'integer'],
  year_desc: ['p.fiscal_year', 'DESC', 'integer'],
  title_asc: ['LOWER(p.title)', 'ASC', 'text'],
});

export class QueryError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.name = 'QueryError';
    this.status = status;
  }
}

const parseInteger = (value, fallback, minimum, maximum, name) => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${name} is invalid`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new QueryError(`${name} is outside the supported range`);
  }
  return parsed;
};

export const parseRegisterQuery = (url) => {
  const params = url.searchParams;
  const q = (params.get('q') || '').trim();
  const year = parseInteger(params.get('year'), null, MIN_YEAR, MAX_YEAR, 'year');
  const status = params.get('status') || 'all';
  const sort = params.get('sort') || 'appropriation_desc';
  const limit = parseInteger(params.get('limit'), 25, 1, MAX_QUERY_LIMIT, 'limit');
  const cursor = params.get('cursor');
  if (q.length > MAX_QUERY_TEXT) throw new QueryError('q is too long');
  if (!['all', 'reviewed', 'quarantine'].includes(status)) {
    throw new QueryError('status is invalid');
  }
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  if (cursor && cursor.length > 1000) throw new QueryError('cursor is invalid for this query');
  return Object.freeze({ q, year, status, sort, limit, cursor });
};

const searchExpression = (value) => {
  const tokens = value.toLocaleLowerCase('en').match(/[\p{L}\p{N}_-]+/gu) || [];
  if (!tokens.length) return null;
  return tokens.map((token) => `"${token.replaceAll('"', '""')}"*`).join(' AND ');
};

const base64Encode = (value) => {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
};

const base64Decode = (value) => {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
  const binary = atob(`${normalized}${'='.repeat((4 - normalized.length % 4) % 4)}`);
  return new TextDecoder().decode(Uint8Array.from(binary, (character) => character.charCodeAt(0)));
};

const encodeCursor = (sort, value, slug) => base64Encode(JSON.stringify({ v: 1, sort, value, slug }));

const decodeCursor = (value, sort, kind) => {
  try {
    const payload = JSON.parse(base64Decode(value));
    const validValue = kind === 'integer'
      ? Number.isSafeInteger(payload.value)
      : typeof payload.value === 'string';
    if (payload.v !== 1 || payload.sort !== sort || typeof payload.slug !== 'string' || !validValue) {
      throw new Error('cursor contract mismatch');
    }
    return [payload.value, payload.slug];
  } catch (error) {
    throw new QueryError('cursor is invalid for this query');
  }
};

const filters = (query) => {
  const clauses = [];
  const bindings = [];
  const search = searchExpression(query.q);
  if (search) {
    clauses.push('p.slug IN (SELECT slug FROM project_search WHERE project_search MATCH ?)');
    bindings.push(search);
  }
  if (query.year !== null) {
    clauses.push('p.fiscal_year = ?');
    bindings.push(query.year);
  }
  if (query.status !== 'all') {
    clauses.push('p.publication_status = ?');
    bindings.push(query.status);
  }
  return { clauses, bindings };
};

const rowToDossier = (row) => ({
  case_id: row.case_id,
  slug: row.slug,
  title: row.title,
  fiscal_year: row.fiscal_year,
  location: row.location,
  appropriation_centavos: row.appropriation_centavos,
  contract_budget_centavos: row.contract_budget_centavos,
  variance_centavos: row.variance_centavos,
  contract_id: row.contract_id,
  delivery_title: row.delivery_title,
  implementing_office: row.implementing_office,
  source_of_funds: row.source_of_funds,
  confidence: row.confidence,
  confidence_score: row.confidence_score,
  match_signals: JSON.parse(row.match_signals_json),
  match_limitations: row.match_limitations,
  evidence_urls: JSON.parse(row.evidence_urls_json),
  family_id: row.family_id,
  family_label: row.family_label,
  status_label: row.status_label,
  is_confirmed_link: Boolean(row.is_confirmed_link),
  is_quarantined: !Boolean(row.is_confirmed_link),
});

export const queryRegister = async (database, query) => {
  const [field, direction, kind] = SORTS[query.sort];
  const { clauses, bindings } = filters(query);
  const initialWhere = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const countStatement = database.prepare(`SELECT COUNT(*) AS total FROM projects p ${initialWhere}`);
  const countRow = await countStatement.bind(...bindings).first();
  if (query.cursor) {
    const [value, slug] = decodeCursor(query.cursor, query.sort, kind);
    const operator = direction === 'DESC' ? '<' : '>';
    clauses.push(`(${field} ${operator} ? OR (${field} = ? AND p.slug > ?))`);
    bindings.push(value, value, slug);
  }
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const statement = database.prepare(
    `SELECT p.* FROM projects p ${where} ORDER BY ${field} ${direction}, p.slug ASC LIMIT ?`,
  );
  const result = await statement.bind(...bindings, query.limit + 1).all();
  const rows = result.results || [];
  const records = rows.slice(0, query.limit).map(rowToDossier);
  let nextCursor = null;
  if (rows.length > query.limit && records.length) {
    const last = records.at(-1);
    const column = field.split('.').at(-1);
    const value = kind === 'text' ? last.title.toLocaleLowerCase('en') : last[column];
    nextCursor = encodeCursor(query.sort, value, last.slug);
  }
  return Object.freeze({ records, total: Number(countRow.total), nextCursor });
};

export const getProject = async (database, slug) => {
  const row = await database.prepare('SELECT * FROM projects WHERE slug = ?').bind(slug).first();
  return row ? rowToDossier(row) : null;
};

const csvCell = (value) => `"${String(value).replaceAll('"', '""')}"`;

export const exportRegisterCsv = async (database, query) => {
  const header = [
    'fiscal_year', 'project', 'location', 'contract_id', 'status',
    'appropriation_centavos', 'contract_budget_centavos', 'dossier',
  ];
  const rows = [header];
  let cursor = null;
  do {
    const page = await queryRegister(database, { ...query, limit: MAX_QUERY_LIMIT, cursor });
    for (const record of page.records) {
      rows.push([
        record.fiscal_year,
        record.title,
        record.location,
        record.contract_id,
        record.is_quarantined ? 'quarantine' : 'reviewed',
        record.appropriation_centavos,
        record.contract_budget_centavos,
        `/projects/${record.slug}/`,
      ]);
    }
    cursor = page.nextCursor;
    if (rows.length - 1 > MAX_EXPORT_ROWS) throw new QueryError('export exceeds record limit');
  } while (cursor);
  return `${rows.map((row) => row.map(csvCell).join(',')).join('\n')}\n`;
};
