import { QueryError } from './query.js';

const MAX_QUERY_TEXT = 200;
const MAX_LIMIT = 100;
const MIN_YEAR = 2000;
const MAX_YEAR = 2100;
const SIGNALS = new Set([
  'all',
  'status_progress_conflict',
  'completed_progress_conflict',
  'date_order_conflict',
  'nonpositive_active_budget',
  'missing_coordinate',
  'coordinate_outside_philippines',
  'completed_without_satellite_image',
  'reused_coordinate',
  'coordinate_location_conflict',
]);
const CLASSIFICATIONS = new Set([
  'all', 'source_conflict', 'amount_review', 'identity_review', 'coverage_gap',
]);
const INTEGRITY_SORTS = Object.freeze({
  budget_desc: ['budget_centavos', 'DESC'],
  year_desc: ['fiscal_year', 'DESC'],
  contract_asc: ['contract_id', 'ASC'],
});
const CONTRACTOR_SORTS = Object.freeze({
  count_desc: ['project_count', 'DESC', 'total_budget_centavos'],
  budget_desc: ['total_budget_centavos', 'DESC', 'project_count'],
  name_asc: ['LOWER(contractor_name)', 'ASC', 'contractor_key'],
});

const integer = (value, field, fallback = null) => {
  if (value === null || value === '') return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${field} is invalid`);
  return Number(value);
};

const text = (url, field) => {
  const value = (url.searchParams.get(field) || '').trim();
  if (value.length > MAX_QUERY_TEXT) throw new QueryError(`${field} is too long`);
  return value;
};

const decodeCursor = (value, fingerprint) => {
  if (!value) return 0;
  try {
    const payload = JSON.parse(atob(value.replaceAll('-', '+').replaceAll('_', '/')));
    if (payload.v !== 1 || !Number.isInteger(payload.offset) || payload.offset < 0) throw new Error();
    if (payload.fingerprint !== fingerprint) throw new Error();
    return payload.offset;
  } catch {
    throw new QueryError('cursor is invalid for this query');
  }
};

const encodeCursor = (offset, fingerprint) => {
  const value = btoa(JSON.stringify({ v: 1, offset, fingerprint }));
  return value.replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
};

const limit = (url) => {
  const value = integer(url.searchParams.get('limit'), 'limit', 25);
  if (value < 1 || value > MAX_LIMIT) throw new QueryError('limit is outside the supported range');
  return value;
};

export const parseIntegrityQuery = (url) => {
  const q = text(url, 'q');
  const signal = url.searchParams.get('signal') || 'all';
  const classification = url.searchParams.get('classification') || 'all';
  const year = integer(url.searchParams.get('year'), 'year');
  const sort = url.searchParams.get('sort') || 'budget_desc';
  if (!SIGNALS.has(signal)) throw new QueryError('signal is invalid');
  if (!CLASSIFICATIONS.has(classification)) throw new QueryError('classification is invalid');
  if (year !== null && (year < MIN_YEAR || year > MAX_YEAR)) {
    throw new QueryError('year is outside the supported range');
  }
  if (!INTEGRITY_SORTS[sort]) throw new QueryError('sort is invalid');
  const parsed = { q, signal, classification, year, sort, limit: limit(url), offset: 0 };
  const fingerprint = [q, signal, classification, year, sort].join('|');
  return { ...parsed, offset: decodeCursor(url.searchParams.get('cursor'), fingerprint) };
};

export const parseContractorQuery = (url) => {
  const q = text(url, 'q');
  const sort = url.searchParams.get('sort') || 'count_desc';
  if (!CONTRACTOR_SORTS[sort]) throw new QueryError('sort is invalid');
  const parsed = { q, sort, limit: limit(url), offset: 0 };
  const fingerprint = [q, sort].join('|');
  return { ...parsed, offset: decodeCursor(url.searchParams.get('cursor'), fingerprint) };
};

const integrityWhere = (query) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    clauses.push('(contract_id LIKE ? OR description LIKE ? OR contractor_name LIKE ? OR province LIKE ? OR region LIKE ?)');
    const pattern = `%${query.q}%`;
    bindings.push(pattern, pattern, pattern, pattern, pattern);
  }
  if (query.signal !== 'all') {
    clauses.push('code = ?');
    bindings.push(query.signal);
  }
  if (query.classification !== 'all') {
    clauses.push('classification = ?');
    bindings.push(query.classification);
  }
  if (query.year !== null) {
    clauses.push('fiscal_year = ?');
    bindings.push(query.year);
  }
  return { sql: clauses.length ? ` WHERE ${clauses.join(' AND ')}` : '', bindings };
};

const signalRecord = (row) => ({
  ...row,
  fiscal_year: Number(row.fiscal_year),
  budget_centavos: Number(row.budget_centavos),
  source_url: `https://api.dpwh.bettergov.ph/projects/${encodeURIComponent(row.contract_id)}`,
});

export const queryIntegritySignals = async (database, query) => {
  const where = integrityWhere(query);
  const total = await database.prepare(
    `SELECT COUNT(*) AS total FROM integrity_signal_items${where.sql}`,
  ).bind(...where.bindings).first('total');
  const [column, direction] = INTEGRITY_SORTS[query.sort];
  const rows = await database.prepare(`
    SELECT contract_id, fiscal_year, code, classification, label, description,
      contractor_name, pcab_id, budget_centavos, status, progress, province, region,
      latitude, longitude, evidence, limitations, source_artifact_sha256
    FROM integrity_signal_items${where.sql}
    ORDER BY ${column} ${direction}, signal_id ASC
    LIMIT ? OFFSET ?
  `).bind(...where.bindings, query.limit, query.offset).all();
  const records = rows.results.map(signalRecord);
  const fingerprint = [query.q, query.signal, query.classification, query.year, query.sort].join('|');
  const nextOffset = query.offset + records.length;
  return {
    total: Number(total),
    records,
    nextCursor: nextOffset < Number(total) ? encodeCursor(nextOffset, fingerprint) : null,
  };
};

export const getIntegritySummary = async (database) => {
  const rows = await database.prepare(
    "SELECT key, value FROM integrity_metadata WHERE key IN ('source_records', 'integrity_signals', 'contractors', 'source_artifact_sha256') OR key LIKE 'signal:%' ORDER BY key",
  ).all();
  const metadata = Object.fromEntries(rows.results.map((row) => [row.key, row.value]));
  const signals = rows.results
    .filter((row) => row.key.startsWith('signal:'))
    .map((row) => ({ code: row.key.slice(7), count: Number(row.value) }));
  return {
    source_records: Number(metadata.source_records),
    integrity_signals: Number(metadata.integrity_signals),
    contractors: Number(metadata.contractors),
    source_artifact_sha256: metadata.source_artifact_sha256,
    signals,
  };
};

const contractorWhere = (query) => {
  if (!query.q) return { sql: '', bindings: [] };
  const pattern = `%${query.q}%`;
  return {
    sql: ' WHERE contractor_name LIKE ? OR pcab_id LIKE ?',
    bindings: [pattern, pattern],
  };
};

const contractorRecord = (row) => ({
  ...row,
  project_count: Number(row.project_count),
  total_budget_centavos: Number(row.total_budget_centavos),
  completed_count: Number(row.completed_count),
  ongoing_count: Number(row.ongoing_count),
  terminated_count: Number(row.terminated_count),
  first_year: Number(row.first_year),
  last_year: Number(row.last_year),
  pcab_url: 'https://www.pcab.construction.gov.ph/verify/',
});

export const queryContractors = async (database, query) => {
  const where = contractorWhere(query);
  const total = await database.prepare(
    `SELECT COUNT(*) AS total FROM contractor_rankings${where.sql}`,
  ).bind(...where.bindings).first('total');
  const [column, direction, secondary] = CONTRACTOR_SORTS[query.sort];
  const secondaryDirection = query.sort === 'name_asc' ? 'ASC' : 'DESC';
  const rows = await database.prepare(`
    SELECT * FROM contractor_rankings${where.sql}
    ORDER BY ${column} ${direction}, ${secondary} ${secondaryDirection}, contractor_key ASC
    LIMIT ? OFFSET ?
  `).bind(...where.bindings, query.limit, query.offset).all();
  const records = rows.results.map(contractorRecord);
  const fingerprint = [query.q, query.sort].join('|');
  const nextOffset = query.offset + records.length;
  return {
    total: Number(total),
    records,
    nextCursor: nextOffset < Number(total) ? encodeCursor(nextOffset, fingerprint) : null,
  };
};

const csvCell = (value) => {
  const textValue = String(value ?? '');
  const safe = /^[=+\-@]/.test(textValue) ? `'${textValue}` : textValue;
  return `"${safe.replaceAll('"', '""')}"`;
};

export const exportIntegrityCsv = async (database, query) => {
  const where = integrityWhere(query);
  const [column, direction] = INTEGRITY_SORTS[query.sort];
  const rows = await database.prepare(`
    SELECT code, classification, contract_id, fiscal_year, description, contractor_name,
      pcab_id, budget_centavos, status, progress, province, region, latitude, longitude,
      evidence, limitations, source_artifact_sha256
    FROM integrity_signal_items${where.sql}
    ORDER BY ${column} ${direction}, signal_id ASC
    LIMIT 10000
  `).bind(...where.bindings).all();
  const headers = [
    'code', 'classification', 'contract_id', 'fiscal_year', 'description', 'contractor_name',
    'pcab_id', 'budget_centavos', 'status', 'progress', 'province', 'region', 'latitude',
    'longitude', 'evidence', 'limitations', 'source_artifact_sha256',
  ];
  return [headers, ...rows.results.map((row) => headers.map((header) => row[header]))]
    .map((row) => row.map(csvCell).join(','))
    .join('\r\n');
};
