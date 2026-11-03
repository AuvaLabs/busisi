import { QueryError } from './query.js';
import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';
import { deliveryRecordUrl } from './source-presentation.js';

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
  'past_completion_not_complete',
  'same_site_repeat_family',
]);
const CLASSIFICATIONS = new Set([
  'all', 'source_conflict', 'amount_review', 'identity_review', 'coverage_gap',
]);
const INTEGRITY_SORTS = Object.freeze({
  budget_desc: ['i.budget_centavos', 'DESC'],
  year_desc: ['i.fiscal_year', 'DESC'],
  contract_asc: ['i.contract_id', 'ASC'],
});
const CONTRACTOR_SORTS = Object.freeze({
  count_desc: ['project_count', 'DESC', 'total_budget_centavos'],
  budget_desc: ['total_budget_centavos', 'DESC', 'project_count'],
  name_asc: ['LOWER(contractor_name)', 'ASC', 'contractor_key'],
});
const CONCENTRATION_DIMENSIONS = new Set(['region', 'province', 'category']);

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

export const parseConcentrationQuery = (url) => {
  const dimension = url.searchParams.get('dimension') || 'region';
  const year = integer(url.searchParams.get('year'), 'year', 0);
  if (!CONCENTRATION_DIMENSIONS.has(dimension)) throw new QueryError('dimension is invalid');
  if (year !== 0 && (year < MIN_YEAR || year > MAX_YEAR)) {
    throw new QueryError('year is outside the supported range');
  }
  return { dimension, year };
};

const integrityWhere = (query) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    clauses.push('(i.contract_id LIKE ? OR i.description LIKE ? OR i.contractor_name LIKE ? OR i.province LIKE ? OR i.region LIKE ?)');
    const pattern = `%${query.q}%`;
    bindings.push(pattern, pattern, pattern, pattern, pattern);
  }
  if (query.signal !== 'all') {
    clauses.push('i.code = ?');
    bindings.push(query.signal);
  }
  if (query.classification !== 'all') {
    clauses.push('i.classification = ?');
    bindings.push(query.classification);
  }
  if (query.year !== null) {
    clauses.push('i.fiscal_year = ?');
    bindings.push(query.year);
  }
  return { sql: clauses.length ? ` WHERE ${clauses.join(' AND ')}` : '', bindings };
};

const signalRecord = (row) => ({
  ...row,
  fiscal_year: Number(row.fiscal_year),
  budget_centavos: Number(row.budget_centavos),
  district_context: districtContext(row),
  district_classification: undefined,
  district_office_name: undefined,
  districts_json: undefined,
  source_url: `https://api.dpwh.bettergov.ph/projects/${encodeURIComponent(row.contract_id)}`,
  reader_source_url: deliveryRecordUrl(row.contract_id),
});

export const queryIntegritySignals = async (database, query) => {
  const where = integrityWhere(query);
  const districtJoin = districtOfficeJoin('i.province');
  const total = await database.prepare(
    `SELECT COUNT(*) AS total FROM integrity_signal_items i ${where.sql}`,
  ).bind(...where.bindings).first('total');
  const [column, direction] = INTEGRITY_SORTS[query.sort];
  const rows = await database.prepare(`
    SELECT i.signal_id, i.contract_id, i.fiscal_year, i.code, i.classification, i.label, i.description,
      i.contractor_name, i.pcab_id, i.budget_centavos, i.status, i.progress, i.province, i.region,
      i.latitude, i.longitude, i.evidence, i.limitations, i.source_artifact_sha256,
      ${DISTRICT_SELECT}
    FROM integrity_signal_items i ${districtJoin}${where.sql}
    ORDER BY ${column} ${direction}, i.signal_id ASC
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
    "SELECT key, value FROM integrity_metadata WHERE key IN ('source_records', 'integrity_signals', 'contractors', 'concentrations', 'source_artifact_sha256', 'source_as_of', 'pcab_records', 'pcab_retrieved_on', 'pcab_source_sha256', 'district_count', 'district_offices', 'district_source_commit', 'district_source_built_at', 'district_source_retrieved_on', 'district_snapshot_sha256') OR key LIKE 'signal:%' OR key LIKE 'pcab_status:%' OR key LIKE 'district_coverage:%' ORDER BY key",
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
    source_as_of: metadata.source_as_of,
    concentrations: Number(metadata.concentrations || 0),
    pcab_records: Number(metadata.pcab_records || 0),
    pcab_retrieved_on: metadata.pcab_retrieved_on,
    pcab_source_sha256: metadata.pcab_source_sha256,
    district_count: Number(metadata.district_count || 0),
    district_offices: Number(metadata.district_offices || 0),
    district_source_commit: metadata.district_source_commit,
    district_source_built_at: metadata.district_source_built_at,
    district_source_retrieved_on: metadata.district_source_retrieved_on,
    district_snapshot_sha256: metadata.district_snapshot_sha256,
    district_coverage: rows.results
      .filter((row) => row.key.startsWith('district_coverage:'))
      .map((row) => ({ classification: row.key.slice(18), count: Number(row.value) })),
    signals,
    pcab_statuses: rows.results
      .filter((row) => row.key.startsWith('pcab_status:'))
      .map((row) => ({ status: row.key.slice(12), count: Number(row.value) })),
  };
};

const contractorWhere = (query) => {
  if (!query.q) return { sql: '', bindings: [] };
  const pattern = `%${query.q}%`;
  return {
    sql: ' WHERE contractor_name LIKE ? OR pcab_name LIKE ? OR pcab_id LIKE ?',
    bindings: [pattern, pattern, pattern],
  };
};

const contractorRecord = (row) => ({
  ...row,
  project_count: Number(row.project_count),
  total_budget_centavos: Number(row.total_budget_centavos),
  completed_count: Number(row.completed_count),
  ongoing_count: Number(row.ongoing_count),
  terminated_count: Number(row.terminated_count),
  joint_project_count: Number(row.joint_project_count),
  first_year: Number(row.first_year),
  last_year: Number(row.last_year),
  pcab_gov_infra: Number(row.pcab_gov_infra),
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

export const queryContractorConcentrations = async (database, query) => {
  const rows = await database.prepare(`
    SELECT * FROM contractor_concentrations
    WHERE dimension = ? AND fiscal_year = ?
    ORDER BY top_share_basis_points DESC, party_association_count DESC, group_label ASC
    LIMIT 100
  `).bind(query.dimension, query.year).all();
  return rows.results.map((row) => ({
    ...row,
    fiscal_year: Number(row.fiscal_year),
    project_count: Number(row.project_count),
    named_project_count: Number(row.named_project_count),
    party_association_count: Number(row.party_association_count),
    contractor_count: Number(row.contractor_count),
    top_project_count: Number(row.top_project_count),
    top_share_basis_points: Number(row.top_share_basis_points),
    top_associated_budget_centavos: Number(row.top_associated_budget_centavos),
  }));
};

const csvCell = (value) => {
  const textValue = String(value ?? '');
  const safe = /^[=+\-@]/.test(textValue) ? `'${textValue}` : textValue;
  return `"${safe.replaceAll('"', '""')}"`;
};

export const exportIntegrityCsv = async (database, query) => {
  const where = integrityWhere(query);
  const [column, direction] = INTEGRITY_SORTS[query.sort];
  const districtJoin = districtOfficeJoin('i.province');
  const rows = await database.prepare(`
    SELECT i.code, i.classification, i.contract_id, i.fiscal_year, i.description, i.contractor_name,
      i.pcab_id, i.budget_centavos, i.status, i.progress, i.province, i.region, i.latitude, i.longitude,
      i.evidence, i.limitations, i.source_artifact_sha256,
      district.classification AS district_classification, district.office_name AS district_office,
      district.districts_json
    FROM integrity_signal_items i ${districtJoin}${where.sql}
    ORDER BY ${column} ${direction}, i.signal_id ASC
    LIMIT 10000
  `).bind(...where.bindings).all();
  const headers = [
    'code', 'classification', 'contract_id', 'fiscal_year', 'description', 'contractor_name',
    'pcab_id', 'budget_centavos', 'status', 'progress', 'province', 'region', 'latitude',
    'longitude', 'evidence', 'limitations', 'source_artifact_sha256',
    'district_classification', 'district_office', 'districts_json',
  ];
  return [headers, ...rows.results.map((row) => headers.map((header) => row[header]))]
    .map((row) => row.map(csvCell).join(','))
    .join('\r\n');
};
