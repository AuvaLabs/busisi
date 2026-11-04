import { QueryError } from './query.js';
import { reviewClassLanguage } from './reader-language.js';

const MAX_TEXT = 200;
const MAX_LIMIT = 100;
const SUMMARY_CACHE_TTL_MS = 60_000;
const summaryCache = new WeakMap();
const SOURCES = new Set(['all', 'budget', 'delivery']);
const FACILITIES = new Set(['all', 'school', 'hospital', 'health_center']);
const IDENTITY_STATES = new Set([
  'all', 'official_exact', 'group_only', 'ambiguous', 'unlinked',
]);
const WORK_TYPES = new Set([
  'all', 'new_build', 'rehabilitation', 'expansion', 'equipment', 'continuation', 'unspecified',
]);
const FLAG_FILTERS = new Set([
  'all', 'with_flags', 'without_flags', 'stage_change', 'record_contradiction',
  'location_review', 'identity_conflict', 'coverage_gap', 'repeat_family',
]);
const SORTS = Object.freeze({
  amount_desc: ['amount_centavos', 'DESC'],
  year_desc: ['fiscal_year', 'DESC'],
  flags_desc: ['flag_count', 'DESC'],
  title_asc: ['LOWER(title)', 'ASC'],
});

const FLAG_DEFINITIONS = Object.freeze({
  contract_identifier_conflict: ['Contract identifier conflict', 'identity_conflict', 'The archived secondary mirror contains conflicting exact identifier evidence.'],
  no_exact_secondary_row: ['No exact secondary row', 'coverage_gap', 'No exact row was located in the archived secondary award mirror.'],
  invalid_contract_identifier: ['Invalid contract identifier', 'coverage_gap', 'The recorded identifier could not be used for an exact secondary-source lookup.'],
  source_image_conflict: ['Source image count conflict', 'coverage_gap', 'The source image representations did not reconcile or acquisition failed.'],
  source_image_gap: ['No source images', 'coverage_gap', 'Both source representations reported no project images.'],
  repeat_previous_year_family: ['Prior-year family candidate', 'repeat_family', 'A normalized family label also appears in an earlier archived budget year; phases may still differ.'],
});

const integer = (value, fallback, minimum, maximum, name) => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${name} is invalid`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new QueryError(`${name} is outside the supported range`);
  }
  return parsed;
};

const fingerprint = (query) => [
  query.q, query.source, query.facility, query.work, query.identity,
  query.flag, query.year, query.sort,
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

export const parsePublicServicesQuery = (url) => {
  const params = url.searchParams;
  const q = (params.get('q') || '').trim();
  const source = params.get('source') || 'all';
  const facility = params.get('facility') || 'all';
  const work = params.get('work') || 'all';
  const identity = params.get('identity') || 'all';
  const flag = params.get('flag') || 'all';
  const year = integer(params.get('year'), null, 2000, 2100, 'year');
  const sort = params.get('sort') || 'amount_desc';
  const limit = integer(params.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (q.length > MAX_TEXT) throw new QueryError('q is too long');
  if (!SOURCES.has(source)) throw new QueryError('source is invalid');
  if (!FACILITIES.has(facility)) throw new QueryError('facility is invalid');
  if (!WORK_TYPES.has(work)) throw new QueryError('work is invalid');
  if (!IDENTITY_STATES.has(identity)) throw new QueryError('identity is invalid');
  if (!FLAG_FILTERS.has(flag)) throw new QueryError('flag is invalid');
  if (!Object.hasOwn(SORTS, sort)) throw new QueryError('sort is invalid');
  const query = {
    q, source, facility, work, identity, flag, year, sort, limit, offset: 0,
  };
  const cursor = params.get('cursor');
  if (cursor) query.offset = decodeCursor(cursor, query);
  return Object.freeze(query);
};

const FACILITY_CASE = `CASE
  WHEN LOWER(title) LIKE '%school%' OR LOWER(title) LIKE '%classroom%' THEN 'school'
  WHEN LOWER(title) LIKE '%hospital%' OR LOWER(title) LIKE '%medical center%'
    OR LOWER(title) LIKE '%medical centre%' THEN 'hospital'
  WHEN LOWER(title) LIKE '%health center%' OR LOWER(title) LIKE '%health centre%'
    OR LOWER(title) LIKE '%rural health unit%' OR LOWER(title) LIKE '%barangay health station%'
    OR LOWER(title) LIKE '%infirmary%' OR LOWER(title) LIKE '%birthing facilit%'
    OR LOWER(title) LIKE '%construction%health facilit%'
    OR LOWER(title) LIKE '%rehab%health facilit%'
    OR LOWER(title) LIKE '%repair%health facilit%'
    OR LOWER(title) LIKE '%improvement%health facilit%' THEN 'health_center'
  ELSE '' END`;

const WORK_CASE = `CASE
  WHEN LOWER(title) LIKE '%rehabilitation%' OR LOWER(title) LIKE '%rehab%'
    OR LOWER(title) LIKE '%repair%' OR LOWER(title) LIKE '%renovation%'
    OR LOWER(title) LIKE '%retrofitting%' OR LOWER(title) LIKE '%improvement%' THEN 'rehabilitation'
  WHEN LOWER(title) LIKE '%expansion%' OR LOWER(title) LIKE '%extension%'
    OR LOWER(title) LIKE '%additional%' THEN 'expansion'
  WHEN LOWER(title) LIKE '%equipment%' OR LOWER(title) LIKE '%equipage%' THEN 'equipment'
  WHEN LOWER(title) LIKE '%completion%' OR LOWER(title) LIKE '%continuation%'
    OR LOWER(title) LIKE '% phase %' OR LOWER(title) LIKE '%phase i%'
    OR LOWER(title) LIKE '%phase 1%' OR LOWER(title) LIKE '%phase 2%' THEN 'continuation'
  WHEN LOWER(title) LIKE '%construction%' OR LOWER(title) LIKE '%establishment%'
    OR LOWER(title) LIKE '%building of%' THEN 'new_build'
  ELSE 'unspecified' END`;

const NORMALIZED_CTE = `WITH raw AS (
  SELECT c.record_id, 'budget' AS source_type, c.fiscal_year, c.title,
    CASE WHEN c.house_centavos > 0 THEN c.house_centavos ELSE c.nep_centavos END AS amount_centavos,
    c.region AS location, c.office AS office, c.program AS program, c.change_label AS status,
    c.change_type, c.family_label,
    CASE WHEN c.change_type <> 'unchanged' THEN 1 ELSE 0 END AS stage_change,
    0 AS record_contradiction, 0 AS location_review, 0 AS identity_conflict,
    0 AS coverage_gap,
    CASE WHEN EXISTS (
      SELECT 1 FROM budget_items prior
      WHERE prior.family_label = c.family_label AND prior.fiscal_year < c.fiscal_year
    ) THEN 1 ELSE 0 END AS repeat_family,
    0 AS source_signal_count, 0 AS generated_flag_count,
    '' AS acquisition_state, '' AS image_state
  FROM stage_change_items c
  UNION ALL
  SELECT d.contract_id AS record_id, 'delivery' AS source_type, d.fiscal_year,
    d.description AS title, d.budget_centavos AS amount_centavos, d.location,
    COALESCE(detail.province, '') AS office, d.source_of_funds AS program,
    COALESCE(detail.status, '') AS status, '' AS change_type, d.family_label,
    0 AS stage_change,
    CASE WHEN EXISTS (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = d.contract_id
        AND signal.classification IN ('source_conflict', 'amount_review')
        AND signal.code NOT LIKE '%coordinate%'
        AND signal.code <> 'same_site_repeat_family'
    ) THEN 1 ELSE 0 END AS record_contradiction,
    CASE WHEN EXISTS (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = d.contract_id AND signal.code LIKE '%coordinate%'
    ) THEN 1 ELSE 0 END AS location_review,
    CASE WHEN acquisition.match_state = 'conflict_review' OR EXISTS (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = d.contract_id AND signal.classification = 'identity_review'
        AND signal.code NOT LIKE '%coordinate%'
        AND signal.code <> 'same_site_repeat_family'
    ) THEN 1 ELSE 0 END AS identity_conflict,
    CASE WHEN acquisition.match_state IN ('no_exact_row', 'invalid_identifier')
      OR images.state IN ('no_images', 'count_conflict', 'acquisition_failed')
      OR EXISTS (
        SELECT 1 FROM integrity_signal_items signal
        WHERE signal.contract_id = d.contract_id AND signal.classification = 'coverage_gap'
          AND signal.code NOT LIKE '%coordinate%'
      ) THEN 1 ELSE 0 END AS coverage_gap,
    CASE WHEN EXISTS (
      SELECT 1 FROM integrity_signal_items signal
      WHERE signal.contract_id = d.contract_id AND signal.code = 'same_site_repeat_family'
    ) THEN 1 ELSE 0 END AS repeat_family,
    (SELECT COUNT(*) FROM integrity_signal_items signal
      WHERE signal.contract_id = d.contract_id) AS source_signal_count,
    CASE WHEN acquisition.match_state IN ('conflict_review', 'no_exact_row', 'invalid_identifier') THEN 1 ELSE 0 END
      + CASE WHEN images.state IN ('no_images', 'count_conflict', 'acquisition_failed')
        THEN 1 ELSE 0 END AS generated_flag_count,
    COALESCE(acquisition.match_state, '') AS acquisition_state,
    COALESCE(images.state, '') AS image_state
  FROM delivery_items d
  LEFT JOIN delivery_project_details detail ON detail.contract_id = d.contract_id
  LEFT JOIN contract_acquisition_details acquisition ON acquisition.contract_id = d.contract_id
  LEFT JOIN project_image_coverage images ON images.contract_id = d.contract_id
), classified AS (
  SELECT raw.*, ${FACILITY_CASE} AS facility_type, ${WORK_CASE} AS work_type,
    COALESCE(link.match_state, 'unlinked') AS identity_state,
    link.record_group_key, link.record_group_label, link.match_method,
    link.confidence AS identity_confidence, link.signals_json AS identity_signals_json,
    link.limitation AS identity_limitation, link.reviewed_at AS identity_reviewed_at,
    registry.facility_id, registry.official_id, registry.official_name,
    registry.municipality AS identity_municipality,
    registry.province AS identity_province, registry.region AS identity_region,
    source.source_id AS registry_source_id, source.publisher AS registry_publisher,
    source.dataset_name AS registry_dataset, source.source_url AS registry_source_url,
    source.scope_note AS registry_scope_note, source.status AS registry_status
  FROM raw
  LEFT JOIN facility_record_links link
    ON link.source_type = raw.source_type AND link.record_id = raw.record_id
  LEFT JOIN facility_identities registry ON registry.facility_id = link.facility_id
  LEFT JOIN facility_registry_sources source ON source.source_id = registry.source_id
), eligible AS MATERIALIZED (
  SELECT *, (stage_change + CASE WHEN source_type = 'budget' THEN repeat_family ELSE 0 END
    + source_signal_count + generated_flag_count) AS flag_count
  FROM classified WHERE facility_type <> ''
)`;

const FILTERED_CTE = NORMALIZED_CTE.replace('eligible AS MATERIALIZED', 'eligible AS');

const filters = (query) => {
  const clauses = [];
  const bindings = [];
  if (query.q) {
    clauses.push(`(INSTR(LOWER(title), LOWER(?)) > 0 OR INSTR(LOWER(location), LOWER(?)) > 0
      OR INSTR(LOWER(office), LOWER(?)) > 0 OR INSTR(LOWER(program), LOWER(?)) > 0)`);
    bindings.push(query.q, query.q, query.q, query.q);
  }
  for (const [value, field] of [
    [query.source, 'source_type'], [query.facility, 'facility_type'],
    [query.work, 'work_type'], [query.identity, 'identity_state'],
  ]) {
    if (value !== 'all') {
      clauses.push(`${field} = ?`);
      bindings.push(value);
    }
  }
  if (query.year !== null) {
    clauses.push('fiscal_year = ?');
    bindings.push(query.year);
  }
  if (query.flag === 'with_flags') clauses.push('flag_count > 0');
  else if (query.flag === 'without_flags') clauses.push('flag_count = 0');
  else if (query.flag !== 'all') clauses.push(`${query.flag} = 1`);
  return { where: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '', bindings };
};

const signalClass = (row) => {
  if (row.code === 'same_site_repeat_family') return 'repeat_family';
  if (row.code.includes('coordinate')) return 'location_review';
  if (row.classification === 'identity_review') return 'identity_conflict';
  if (row.classification === 'coverage_gap') return 'coverage_gap';
  return 'record_contradiction';
};

const stageFlag = (record) => ({
  code: `budget_${record.change_type}`,
  label: record.status || record.change_type.replaceAll('_', ' '),
  classification: 'stage_change',
  limitation: 'A document-stage change is a review lead, not proof of authorship, motive, or wrongdoing.',
});

const definedFlag = (code) => {
  const [label, classification, limitation] = FLAG_DEFINITIONS[code];
  return { code, label, classification, limitation };
};

const flagsFor = (record, signals) => {
  const flags = [];
  if (record.source_type === 'budget' && record.stage_change) flags.push(stageFlag(record));
  if (record.source_type === 'budget' && record.repeat_family) {
    flags.push(definedFlag('repeat_previous_year_family'));
  }
  if (record.source_type === 'delivery') {
    for (const signal of signals) flags.push({
      code: signal.code,
      label: signal.label,
      classification: signalClass(signal),
      limitation: signal.limitations,
    });
    if (record.acquisition_state === 'conflict_review') {
      flags.push(definedFlag('contract_identifier_conflict'));
    } else if (record.acquisition_state === 'no_exact_row') {
      flags.push(definedFlag('no_exact_secondary_row'));
    } else if (record.acquisition_state === 'invalid_identifier') {
      flags.push(definedFlag('invalid_contract_identifier'));
    }
    if (['count_conflict', 'acquisition_failed'].includes(record.image_state)) {
      flags.push(definedFlag('source_image_conflict'));
    } else if (record.image_state === 'no_images') {
      flags.push(definedFlag('source_image_gap'));
    }
  }
  return flags.map((flag) => Object.freeze({
    ...flag,
    plain_language: reviewClassLanguage(flag.classification),
  }));
};

const signalMap = async (database, records) => {
  const ids = records.filter(({ source_type }) => source_type === 'delivery')
    .map(({ record_id }) => record_id);
  if (!ids.length) return new Map();
  const placeholders = ids.map(() => '?').join(',');
  const result = await database.prepare(`
    SELECT contract_id, code, classification, label, limitations
    FROM integrity_signal_items WHERE contract_id IN (${placeholders})
    ORDER BY contract_id, code
  `).bind(...ids).all();
  const mapped = new Map();
  for (const signal of result.results || []) {
    const current = mapped.get(signal.contract_id) || [];
    mapped.set(signal.contract_id, [...current, signal]);
  }
  return mapped;
};

const mapRecord = (record, signals) => {
  const flags = flagsFor(record, signals.get(record.record_id) || []);
  const identity = (() => {
    if (record.identity_state === 'official_exact') return {
      state: record.identity_state,
      name: record.official_name,
      official_id: record.official_id,
      source: record.registry_dataset,
      source_url: record.registry_source_url,
      explanation: `Linked to official ${record.facility_type === 'school' ? 'school' : 'facility'} ID ${record.official_id} in ${record.registry_dataset}, published by ${record.registry_publisher}.`,
      limitation: record.identity_limitation || record.registry_scope_note,
    };
    if (record.identity_state === 'group_only') return {
      state: record.identity_state,
      name: record.record_group_label,
      official_id: null,
      source: null,
      source_url: null,
      explanation: 'Similar record labels were grouped by normalized facility name and place. This is not an official identity or a count of buildings.',
      limitation: record.identity_limitation,
    };
    if (record.identity_state === 'ambiguous') return {
      state: record.identity_state,
      name: record.record_group_label || null,
      official_id: null,
      source: null,
      source_url: null,
      explanation: record.identity_limitation || 'More than one facility could fit this record, so Busisi did not select one.',
      limitation: record.identity_limitation,
    };
    return {
      state: 'unlinked',
      name: null,
      official_id: null,
      source: null,
      source_url: null,
      explanation: 'No official facility identity or reliable record group has been linked to this record yet.',
      limitation: 'An unlinked record is not evidence that the named facility does not exist.',
    };
  })();
  return Object.freeze({
    record_id: record.record_id,
    source_type: record.source_type,
    fiscal_year: Number(record.fiscal_year),
    title: record.title,
    facility_type: record.facility_type,
    work_type: record.work_type,
    amount_centavos: Number(record.amount_centavos),
    location: record.location,
    office: record.office,
    program: record.program,
    status: record.status,
    facility_identity: Object.freeze(identity),
    flags,
    flag_count: flags.length,
    reader_url: record.source_type === 'budget'
      ? `/records/change/${encodeURIComponent(record.record_id)}/`
      : `/contracts/${encodeURIComponent(record.record_id)}/`,
  });
};

export const queryPublicServices = async (database, query) => {
  const { where, bindings } = filters(query);
  const [field, direction] = SORTS[query.sort];
  const result = await database.prepare(`${FILTERED_CTE}
    SELECT *, COUNT(*) OVER () AS filtered_total FROM eligible ${where}
    ORDER BY ${field} ${direction}, record_id ASC LIMIT ? OFFSET ?`)
    .bind(...bindings, query.limit, query.offset).all();
  const raw = result.results || [];
  const signals = await signalMap(database, raw);
  const records = raw.map((record) => mapRecord(record, signals));
  let total = Number(raw[0]?.filtered_total || 0);
  if (!raw.length && query.offset > 0) {
    const countRow = await database.prepare(
      `${FILTERED_CTE} SELECT COUNT(*) AS total FROM eligible ${where}`,
    ).bind(...bindings).first();
    total = Number(countRow.total || 0);
  }
  const nextOffset = query.offset + records.length;
  return Object.freeze({
    records,
    total,
    nextCursor: nextOffset < total ? encodeCursor(query, nextOffset) : null,
  });
};

const loadPublicServicesSummary = async (database) => {
  const row = await database.prepare(`${NORMALIZED_CTE} SELECT COUNT(*) AS total,
    SUM(source_type = 'budget') AS budget, SUM(source_type = 'delivery') AS delivery,
    SUM(flag_count > 0) AS flagged,
    SUM(facility_type = 'school') AS school,
    SUM(facility_type = 'hospital') AS hospital,
    SUM(facility_type = 'health_center') AS health_center,
    SUM(work_type = 'new_build') AS new_build,
    SUM(work_type = 'rehabilitation') AS rehabilitation,
    SUM(work_type = 'expansion') AS expansion,
    SUM(work_type = 'equipment') AS equipment,
    SUM(work_type = 'continuation') AS continuation,
    SUM(work_type = 'unspecified') AS unspecified,
    SUM(stage_change) AS stage_change, SUM(record_contradiction) AS record_contradiction,
    SUM(location_review) AS location_review, SUM(identity_conflict) AS identity_conflict,
    SUM(coverage_gap) AS coverage_gap, SUM(repeat_family) AS repeat_family,
    COUNT(DISTINCT CASE WHEN identity_state = 'official_exact' THEN facility_id END)
      AS official_facilities,
    SUM(identity_state = 'official_exact') AS official_linked_records,
    COUNT(DISTINCT CASE WHEN identity_state = 'group_only' THEN record_group_key END)
      AS record_groups,
    SUM(identity_state = 'group_only') AS grouped_records,
    SUM(identity_state = 'ambiguous') AS ambiguous_records,
    SUM(identity_state = 'unlinked') AS unlinked_records
    FROM eligible`).first();
  return Object.freeze({
    records: {
      total: Number(row.total || 0),
      budget: Number(row.budget || 0),
      delivery: Number(row.delivery || 0),
      flagged: Number(row.flagged || 0),
    },
    facilities: Object.fromEntries(['school', 'hospital', 'health_center'].map((key) => (
      [key, Number(row[key] || 0)]
    ))),
    work_types: Object.fromEntries([
      'new_build', 'rehabilitation', 'expansion', 'equipment', 'continuation', 'unspecified',
    ].map((key) => [key, Number(row[key] || 0)])),
    identity_coverage: Object.fromEntries([
      'official_facilities', 'official_linked_records', 'record_groups', 'grouped_records',
      'ambiguous_records', 'unlinked_records',
    ].map((key) => [key, Number(row[key] || 0)])),
    flag_counts: [
      'stage_change', 'record_contradiction', 'location_review', 'identity_conflict',
      'coverage_gap', 'repeat_family',
    ].map((classification) => ({ classification, count: Number(row[classification] || 0) })),
    classification_version: 'public-services-v2',
    identity_method_version: 'facility-identity-v1',
    limitation: 'Counts are records matched by words in the project title, not unique facilities. Budget rows and delivery contracts remain separate and do not prove physical construction, completion, payment, quality, or public benefit.',
  });
};

export const getPublicServicesSummary = async (database) => {
  const now = Date.now();
  const cached = summaryCache.get(database);
  if (cached && cached.expiresAt > now) return cached.value;
  const pending = loadPublicServicesSummary(database);
  summaryCache.set(database, { expiresAt: now + SUMMARY_CACHE_TTL_MS, value: pending });
  try {
    return await pending;
  } catch (error) {
    summaryCache.delete(database);
    throw error;
  }
};
