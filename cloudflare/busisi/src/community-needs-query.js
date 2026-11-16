import { QueryError } from './query.js';

const LEVELS = new Set([
  'all',
  'region',
  'province_or_huc',
  'city_or_municipality',
  'submunicipality',
  'barangay',
]);

const parseLimit = (value) => {
  if (value === null) return 50;
  if (!/^\d+$/.test(value)) throw new QueryError('limit is invalid');
  const limit = Number(value);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
    throw new QueryError('limit is outside the supported range');
  }
  return limit;
};

export const parseCommunityNeedsQuery = (url) => {
  const level = url.searchParams.get('level') || 'city_or_municipality';
  const q = (url.searchParams.get('q') || '').trim();
  if (!LEVELS.has(level)) throw new QueryError('level is invalid');
  if (q.length > 200) throw new QueryError('q is too long');
  return Object.freeze({ level, q, limit: parseLimit(url.searchParams.get('limit')) });
};

const results = (result) => result.results || [];

const readablePsaTableUrl = (sourceUrl) => {
  const tablePath = sourceUrl.split('/PXWeb/api/v1/en/DB/')[1];
  const parts = tablePath.split('/');
  const table = parts.pop();
  return `https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__${parts.join('__')}/${table}/`;
};

export const queryCommunityNeeds = async (database, query) => {
  const filters = [];
  const bindings = [];
  if (query.level !== 'all') {
    filters.push('place.geographic_level = ?');
    bindings.push(query.level);
  }
  if (query.q) {
    filters.push('INSTR(LOWER(place.name), LOWER(?)) > 0');
    bindings.push(query.q);
  }
  const where = filters.length ? `WHERE ${filters.join(' AND ')}` : '';
  const rows = await database.prepare(`
    SELECT place.psgc_code, place.parent_psgc_code, place.name,
      place.geographic_level, place.census_date, place.total_population,
      place.household_population, place.households, place.source_url,
      parent.name AS parent_name,
      gap.unallocated_population, gap.unallocated_household_population,
      gap.unallocated_households
    FROM community_need_places place
    LEFT JOIN community_need_places parent ON parent.psgc_code = place.parent_psgc_code
    LEFT JOIN community_need_hierarchy_gaps gap ON gap.parent_psgc_code = place.psgc_code
    ${where}
    ORDER BY place.total_population DESC, LOWER(place.name), place.psgc_code
    LIMIT ?
  `).bind(...bindings, query.limit).all();
  return results(rows).map((row) => ({
    ...row,
    source_page_url: readablePsaTableUrl(row.source_url),
    child_coverage_complete: row.unallocated_population === null,
  }));
};

export const getCommunityNeedsSummary = async (database) => {
  const response = await database.prepare(
    'SELECT key, value FROM community_needs_metadata ORDER BY key',
  ).all();
  const metadata = Object.fromEntries(results(response).map((row) => [row.key, row.value]));
  const integer = (key) => Number.parseInt(metadata[key] || '0', 10);
  return {
    census_date: metadata.census_date || null,
    checked_at: metadata.checked_at || null,
    national_population: integer('national_population'),
    national_households: integer('national_households'),
    place_count: integer('place_count'),
    region_count: integer('region_count'),
    barangay_count: integer('barangay_count'),
    excluded_out_of_region: integer('excluded_out_of_region'),
    hierarchy_gap_count: integer('hierarchy_gap_count'),
    national_unallocated_population: integer('national_unallocated_population'),
  };
};
