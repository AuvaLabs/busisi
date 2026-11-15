import { QueryError } from './query.js';

const MAX_TEXT = 200;
const MAX_FACET_TEXT = 120;
const MAX_LIMIT = 100;
const SUMMARY_CACHE_TTL_MS = 60_000;
const summaryCache = new WeakMap();

const TAGS = Object.freeze({
  type: new Set([
    'all', 'road', 'bridge', 'flood_control', 'multipurpose_building', 'school',
    'health_facility', 'water_system', 'evacuation_center', 'port_harbor',
    'public_building',
  ]),
  purpose: new Set([
    'all', 'farm_to_market', 'transport', 'flood_protection', 'education', 'health',
    'disaster_response', 'water_access',
  ]),
  work: new Set([
    'all', 'construction', 'later_phase', 'completion', 'rehabilitation', 'repair',
    'improvement', 'maintenance', 'replacement', 'retrofitting', 'restoration',
  ]),
  program: new Set([
    'all', 'da_fmr', 'deped_beff', 'doh_hfep', 'ssp', 'locally_funded',
    'foreign_assisted', 'pamana', 'unprogrammed', 'trust_fund',
  ]),
});

const DIMENSIONS = Object.freeze({
  type: 'project_type',
  purpose: 'purpose',
  work: 'work_type',
  program: 'funding_program',
});

const SORTS = Object.freeze({
  budget_desc: ['delivery.budget_centavos', 'DESC'],
  year_desc: ['delivery.fiscal_year', 'DESC'],
  progress_desc: ['CAST(detail.progress AS REAL)', 'DESC'],
  contract_asc: ['delivery.contract_id', 'ASC'],
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
  query.q, query.type, query.purpose, query.work, query.program, query.year,
  query.region, query.province, query.status, query.sort,
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
      || payload.fingerprint !== fingerprint(query)) throw new Error('invalid cursor');
    return payload.offset;
  } catch {
    throw new QueryError('cursor is invalid for this query');
  }
};

export const parseProjectTypeQuery = (url) => {
  const params = url.searchParams;
  const q = boundedText(params, 'q', MAX_TEXT);
  const type = params.get('type') || 'all';
  const purpose = params.get('purpose') || 'all';
  const work = params.get('work') || 'all';
  const program = params.get('program') || 'all';
  const year = parseInteger(params.get('year'), null, 2000, 2100, 'year');
  const region = boundedText(params, 'region');
  const province = boundedText(params, 'province');
  const status = boundedText(params, 'status');
  const sort = params.get('sort') || 'budget_desc';
  const limit = parseInteger(params.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  for (const [name, value] of Object.entries({ type, purpose, work, program })) {
    if (!TAGS[name].has(value)) throw new QueryError(`${name} is invalid`);
  }
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = {
    q, type, purpose, work, program, year, region, province, status,
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
    clauses.push(`(
      INSTR(LOWER(delivery.contract_id), LOWER(?)) > 0
      OR INSTR(LOWER(delivery.description), LOWER(?)) > 0
      OR INSTR(LOWER(delivery.location), LOWER(?)) > 0
      OR INSTR(LOWER(detail.contractor_name), LOWER(?)) > 0
    )`);
    bindings.push(query.q, query.q, query.q, query.q);
  }
  if (query.year !== null) {
    clauses.push('delivery.fiscal_year = ?');
    bindings.push(query.year);
  }
  for (const [value, field] of [
    [query.region, 'detail.region'],
    [query.province, 'detail.province'],
    [query.status, 'detail.status'],
  ]) {
    if (value) {
      clauses.push(`${field} = ?`);
      bindings.push(value);
    }
  }
  for (const [name, dimension] of Object.entries(DIMENSIONS)) {
    const value = query[name];
    if (value !== 'all') {
      clauses.push(`EXISTS (
        SELECT 1 FROM project_classification_tags filter_tag
        WHERE filter_tag.contract_id = delivery.contract_id
          AND filter_tag.dimension = ? AND filter_tag.tag = ?
      )`);
      bindings.push(dimension, value);
    }
  }
  return { clauses, bindings };
};

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
  classifications: safeArray(row.classifications_json),
  classifications_json: undefined,
  reader_url: `/contracts/${encodeURIComponent(row.contract_id)}/`,
});

export const queryProjectTypes = async (database, query) => {
  const { clauses, bindings } = filters(query);
  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : '';
  const [sortField, sortDirection] = SORTS[query.sort];
  const [count, result] = await Promise.all([
    database.prepare(`
      SELECT COUNT(*) AS total
      FROM delivery_items delivery
      JOIN delivery_project_details detail ON detail.contract_id = delivery.contract_id
      ${where}
    `).bind(...bindings).first(),
    database.prepare(`
      SELECT delivery.contract_id, delivery.fiscal_year, delivery.description,
        delivery.budget_centavos, delivery.location, delivery.source_of_funds,
        detail.category, detail.status, detail.progress, detail.contractor_name,
        detail.province, detail.region,
        COALESCE((
          SELECT json_group_array(json_object(
            'dimension', ordered.dimension, 'tag', ordered.tag, 'label', ordered.label,
            'evidence_kind', ordered.evidence_kind, 'rule_id', ordered.rule_id,
            'rule_version', ordered.rule_version
          )) FROM (
            SELECT dimension, tag, label, evidence_kind, rule_id, rule_version
            FROM project_classification_tags classification
            WHERE classification.contract_id = delivery.contract_id
            ORDER BY dimension, tag
          ) ordered
        ), '[]') AS classifications_json
      FROM delivery_items delivery
      JOIN delivery_project_details detail ON detail.contract_id = delivery.contract_id
      ${where}
      ORDER BY ${sortField} ${sortDirection}, delivery.contract_id ASC
      LIMIT ? OFFSET ?
    `).bind(...bindings, query.limit, query.offset).all(),
  ]);
  const records = (result.results || []).map(mapRecord);
  const total = Number(count.total);
  const nextOffset = query.offset + records.length;
  return Object.freeze({
    records,
    total,
    nextCursor: nextOffset < total ? encodeCursor(query, nextOffset) : null,
  });
};

const metadata = async (database) => {
  const result = await database.prepare(
    'SELECT key, value FROM project_classification_metadata ORDER BY key',
  ).all();
  return Object.fromEntries((result.results || []).map((item) => [item.key, item.value]));
};

const tagSummary = async (database) => {
  const result = await database.prepare(`
    SELECT tag.dimension, tag.tag, tag.label, COUNT(*) AS project_count,
      SUM(delivery.budget_centavos) AS recorded_budget_centavos
    FROM project_classification_tags tag
    JOIN delivery_items delivery ON delivery.contract_id = tag.contract_id
    GROUP BY tag.dimension, tag.tag, tag.label
    ORDER BY tag.dimension, project_count DESC, tag.label ASC
  `).all();
  return result.results || [];
};

const facet = async (database, field) => {
  const result = await database.prepare(`
    SELECT ${field} AS value, COUNT(*) AS count
    FROM delivery_project_details
    WHERE TRIM(${field}) <> ''
    GROUP BY ${field} ORDER BY count DESC, value ASC LIMIT 250
  `).all();
  return result.results || [];
};

const loadProjectTypeSummary = async (database) => {
  const [values, tags, regions, provinces, statuses, years] = await Promise.all([
    metadata(database),
    tagSummary(database),
    facet(database, 'region'),
    facet(database, 'province'),
    facet(database, 'status'),
    database.prepare(`
      SELECT fiscal_year AS value, COUNT(*) AS count
      FROM delivery_project_details GROUP BY fiscal_year ORDER BY fiscal_year DESC
    `).all(),
  ]);
  const dimensions = Object.fromEntries(
    ['project_type', 'purpose', 'work_type', 'funding_program'].map((dimension) => [
      dimension,
      tags.filter((item) => item.dimension === dimension),
    ]),
  );
  return Object.freeze({
    coverage: {
      source_records: Number(values.source_records || 0),
      classified_records: Number(values.classified_records || 0),
      unclassified_records: Number(values.unclassified_records || 0),
      classification_tags: Number(values.classification_tags || 0),
      rule_version: Number(values.rule_version || 0),
    },
    dimensions,
    facets: { regions, provinces, statuses, years: years.results || [] },
    boundary: 'Tags describe source text. One project can have several tags.',
  });
};

export const getProjectTypeSummary = async (database) => {
  const now = Date.now();
  const cached = summaryCache.get(database);
  if (cached && cached.expiresAt > now) return cached.value;
  const pending = loadProjectTypeSummary(database);
  summaryCache.set(database, { expiresAt: now + SUMMARY_CACHE_TTL_MS, value: pending });
  try {
    return await pending;
  } catch (error) {
    summaryCache.delete(database);
    throw error;
  }
};
