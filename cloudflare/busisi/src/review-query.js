import { QueryError } from './query.js';
import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';

const MAX_LIMIT = 100;
const MAX_EXPORT_ROWS = 10_000;
const MAX_GROUP_LENGTH = 200;
const DATASETS = Object.freeze(['all', 'dpwh', 'fmr', 'hfep', 'nia']);
const SIGNALS = Object.freeze([
  'house_only', 'increased', 'decreased', 'nep_only', 'repeat_family', 'similar_family',
]);
const DIMENSIONS = Object.freeze({
  region: 'c.region',
  office: 'c.office',
  program: 'c.program',
  dataset: 'c.dataset',
});
const CHANGE_SIGNALS = new Set(['house_only', 'increased', 'decreased', 'nep_only']);
const FAMILY_QUALITY = `LENGTH(TRIM(c.family_label)) BETWEEN 16 AND 240
  AND LENGTH(c.family_label) - LENGTH(REPLACE(c.family_label, ' ', '')) >= 3`;

const parseInteger = (value, fallback, minimum, maximum, name) => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) throw new QueryError(`${name} is invalid`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new QueryError(`${name} is outside the supported range`);
  }
  return parsed;
};

export const parseReviewQuery = (url) => {
  const signal = url.searchParams.get('signal') || 'house_only';
  const dataset = url.searchParams.get('dataset') || 'all';
  const dimension = url.searchParams.get('dimension') || 'region';
  const group = (url.searchParams.get('group') || '').trim();
  const limit = parseInteger(url.searchParams.get('limit'), 25, 1, MAX_LIMIT, 'limit');
  if (!SIGNALS.includes(signal)) throw new QueryError('signal is invalid');
  if (!DATASETS.includes(dataset)) throw new QueryError('dataset is invalid');
  if (!Object.hasOwn(DIMENSIONS, dimension)) throw new QueryError('dimension is invalid');
  if (group.length > MAX_GROUP_LENGTH) throw new QueryError('group is too long');
  return Object.freeze({ signal, dataset, dimension, group, limit });
};

const signalFilter = (signal) => {
  if (CHANGE_SIGNALS.has(signal)) return { clause: 'c.change_type = ?', bindings: [signal] };
  if (signal === 'repeat_family') {
    return {
      clause: `${FAMILY_QUALITY} AND EXISTS (
        SELECT 1 FROM budget_items b
        WHERE b.family_label = c.family_label AND b.fiscal_year < c.fiscal_year
          AND b.amount_centavos > 0
      )`,
      bindings: [],
    };
  }
  return {
    clause: `${FAMILY_QUALITY} AND EXISTS (
      SELECT 1 FROM stage_change_items peer
      WHERE peer.dataset = c.dataset AND peer.family_label = c.family_label
        AND peer.record_id <> c.record_id
    )`,
    bindings: [],
  };
};

const reviewWhere = (query) => {
  const signal = signalFilter(query.signal);
  const clauses = [signal.clause];
  const bindings = [...signal.bindings];
  if (query.dataset !== 'all') {
    clauses.push('c.dataset = ?');
    bindings.push(query.dataset);
  }
  if (query.group) {
    const field = DIMENSIONS[query.dimension];
    clauses.push(`COALESCE(NULLIF(TRIM(${field}), ''), 'Not stated') = ?`);
    bindings.push(query.group);
  }
  return { where: `WHERE ${clauses.join(' AND ')}`, bindings };
};

const enrichment = (signal) => {
  if (signal === 'repeat_family') {
    return `,
      (SELECT COUNT(DISTINCT b.fiscal_year) FROM budget_items b
        WHERE b.family_label = c.family_label AND b.fiscal_year < c.fiscal_year
          AND b.amount_centavos > 0) AS prior_year_count,
      (SELECT GROUP_CONCAT(DISTINCT b.fiscal_year) FROM budget_items b
        WHERE b.family_label = c.family_label AND b.fiscal_year < c.fiscal_year
          AND b.amount_centavos > 0) AS prior_years,
      (SELECT SUM(b.amount_centavos) FROM budget_items b
        WHERE b.family_label = c.family_label AND b.fiscal_year < c.fiscal_year
          AND b.amount_centavos > 0) AS prior_total_centavos`;
  }
  if (signal === 'similar_family') {
    return `,
      (SELECT COUNT(*) FROM stage_change_items peer
        WHERE peer.dataset = c.dataset AND peer.family_label = c.family_label) AS family_count`;
  }
  return '';
};

const rankingOrder = (signal) => {
  if (signal === 'decreased') return 'c.difference_centavos ASC';
  if (signal === 'nep_only') return 'c.nep_centavos DESC';
  if (signal === 'increased') return 'c.difference_centavos DESC';
  if (signal === 'repeat_family') {
    return 'ABS(c.difference_centavos) DESC, prior_year_count DESC, prior_total_centavos DESC';
  }
  if (signal === 'similar_family') return 'family_count DESC, ABS(c.difference_centavos) DESC';
  return 'c.house_centavos DESC';
};

const mapReviewRecord = (row, signal) => Object.freeze({
  ...row,
  signal,
  district_context: districtContext(row),
  district_classification: undefined,
  district_office_name: undefined,
  districts_json: undefined,
  prior_year_count: Number(row.prior_year_count || 0),
  prior_years: row.prior_years
    ? row.prior_years.split(',').map(Number).sort((left, right) => left - right)
    : [],
  prior_total_centavos: Number(row.prior_total_centavos || 0),
  family_count: Number(row.family_count || 0),
});

export const queryReviewRankings = async (database, query, exportLimit = null) => {
  const { where, bindings } = reviewWhere(query);
  const count = await database
    .prepare(`SELECT COUNT(*) AS total FROM stage_change_items c ${where}`)
    .bind(...bindings)
    .first();
  const limit = exportLimit || query.limit;
  const districtJoin = districtOfficeJoin('c.office');
  const result = await database.prepare(
    `SELECT c.*, ${DISTRICT_SELECT}${enrichment(query.signal)}
      FROM stage_change_items c ${districtJoin} ${where}
      ORDER BY ${rankingOrder(query.signal)}, c.record_id ASC LIMIT ?`,
  ).bind(...bindings, limit).all();
  const records = (result.results || []).map((row) => mapReviewRecord(row, query.signal));
  return Object.freeze({ records, total: Number(count.total) });
};

export const queryReviewConcentrations = async (database, query) => {
  const { where, bindings } = reviewWhere(query);
  const field = DIMENSIONS[query.dimension];
  const result = await database.prepare(
    `SELECT COALESCE(NULLIF(TRIM(${field}), ''), 'Not stated') AS label,
      COUNT(*) AS record_count, SUM(c.nep_centavos) AS nep_centavos,
      SUM(c.house_centavos) AS house_centavos,
      SUM(ABS(c.difference_centavos)) AS movement_centavos
    FROM stage_change_items c ${where}
    GROUP BY COALESCE(NULLIF(TRIM(${field}), ''), 'Not stated')
    ORDER BY movement_centavos DESC, record_count DESC, label ASC LIMIT ?`,
  ).bind(...bindings, query.limit).all();
  return Object.freeze((result.results || []).map((row) => Object.freeze({
    ...row,
    record_count: Number(row.record_count),
  })));
};

export const getReviewSummary = async (database) => {
  const changes = await database.prepare(
    `SELECT change_type, COUNT(*) AS record_count,
      SUM(nep_centavos) AS nep_centavos, SUM(house_centavos) AS house_centavos,
      SUM(difference_centavos) AS difference_centavos
    FROM stage_change_items GROUP BY change_type ORDER BY change_type`,
  ).all();
  const quarantined = await database.prepare(
    "SELECT COUNT(*) AS total FROM stage_change_items WHERE review_status = 'quarantine'",
  ).first();
  return Object.freeze({
    changes: (changes.results || []).map((row) => ({ ...row, record_count: Number(row.record_count) })),
    quarantine_count: Number(quarantined.total),
  });
};

const safeCsvCell = (value) => {
  const text = String(value ?? '');
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
};

export const exportReviewCsv = async (database, query) => {
  const page = await queryReviewRankings(database, query, MAX_EXPORT_ROWS + 1);
  if (page.records.length > MAX_EXPORT_ROWS) throw new QueryError('export exceeds record limit');
  const header = [
    'signal', 'dataset', 'project', 'program', 'region', 'office', 'change_type',
    'review_status', 'nep_centavos', 'house_centavos', 'difference_centavos',
    'prior_years', 'comparison_record', 'nep_document', 'house_document',
  ];
  const rows = page.records.map((record) => [
    record.signal, record.dataset, record.title, record.program, record.region, record.office,
    record.change_type, record.review_status, record.nep_centavos, record.house_centavos,
    record.difference_centavos, record.prior_years.join('|'), record.source_url,
    record.nep_pdf_url, record.house_pdf_url,
  ]);
  return `${[header, ...rows].map((row) => row.map(safeCsvCell).join(',')).join('\n')}\n`;
};
