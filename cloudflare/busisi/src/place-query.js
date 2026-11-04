import { QueryError } from './query.js';

const LEVELS = Object.freeze({
  province: 'detail.province',
  region: 'detail.region',
});

const parseLimit = (value) => {
  if (value === null) return 50;
  if (!/^\d+$/.test(value)) throw new QueryError('limit is invalid');
  const limit = Number(value);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
    throw new QueryError('limit is outside the supported range');
  }
  return limit;
};

export const parsePlaceQuery = (url) => {
  const level = url.searchParams.get('level') || 'province';
  const q = (url.searchParams.get('q') || '').trim();
  if (!Object.hasOwn(LEVELS, level)) throw new QueryError('level is invalid');
  if (q.length > 200) throw new QueryError('q is too long');
  return Object.freeze({ level, q, limit: parseLimit(url.searchParams.get('limit')) });
};

const resultRows = (result) => result.results || [];

export const queryPlaces = async (database, query) => {
  const placeColumn = LEVELS[query.level];
  const filters = [`TRIM(COALESCE(${placeColumn}, '')) <> ''`];
  const bindings = [];
  if (query.q) {
    filters.push(`INSTR(LOWER(${placeColumn}), LOWER(?)) > 0`);
    bindings.push(query.q);
  }
  const result = await database.prepare(`
    WITH signal_contracts AS (
      SELECT DISTINCT contract_id FROM integrity_signal_items
    ), project_rows AS (
      SELECT ${placeColumn} AS place_name, delivery.contract_id,
        delivery.budget_centavos, detail.contractor_parties_json,
        CASE WHEN signal.contract_id IS NULL THEN 0 ELSE 1 END AS needs_check
      FROM delivery_items delivery
      JOIN delivery_project_details detail ON detail.contract_id = delivery.contract_id
      LEFT JOIN signal_contracts signal ON signal.contract_id = delivery.contract_id
      WHERE ${filters.join(' AND ')}
    ), place_totals AS (
      SELECT place_name, COUNT(*) AS project_count,
        SUM(budget_centavos) AS total_budget_centavos,
        SUM(needs_check) AS projects_needing_check
      FROM project_rows GROUP BY place_name
    ), contractor_totals AS (
      SELECT project.place_name,
        COUNT(DISTINCT json_extract(party.value, '$.contractor_key')) AS contractor_count
      FROM project_rows project, json_each(project.contractor_parties_json) party
      WHERE json_type(party.value, '$.contractor_key') = 'text'
        AND json_extract(party.value, '$.contractor_key') <> ''
      GROUP BY project.place_name
    )
    SELECT place.place_name, place.project_count, place.total_budget_centavos,
      COALESCE(contractor.contractor_count, 0) AS contractor_count,
      place.projects_needing_check
    FROM place_totals place
    LEFT JOIN contractor_totals contractor ON contractor.place_name = place.place_name
    ORDER BY place.project_count DESC, LOWER(place.place_name) ASC
    LIMIT ?
  `).bind(...bindings, query.limit).all();
  return resultRows(result).map((record) => ({
    ...record,
    reader_url: `/contracts/?${new URLSearchParams({ [query.level]: record.place_name })}`,
  }));
};
