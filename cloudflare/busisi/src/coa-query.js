const resultRows = (result) => result.results || [];

const metadata = async (database) => {
  const result = await database.prepare('SELECT key, value FROM coa_metadata ORDER BY key').all();
  return Object.fromEntries(resultRows(result).map(({ key, value }) => [key, value]));
};

const safeArray = (value) => {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const coverageRecord = (row) => row && ({
  ...row,
  match_basis: safeArray(row.match_basis_json),
  match_basis_json: undefined,
});

export const getCoaSummary = async (database) => {
  const [meta, statuses, catalogs] = await Promise.all([
    metadata(database),
    database.prepare(`
      SELECT status, COUNT(*) AS record_count
      FROM coa_project_coverage GROUP BY status ORDER BY status
    `).all(),
    database.prepare(`
      SELECT catalog_id, title, source_url, checked_status, evidence_note
      FROM coa_source_catalogs ORDER BY catalog_id
    `).all(),
  ]);
  return {
    metadata: meta,
    statuses: Object.fromEntries(
      resultRows(statuses).map(({ status, record_count: count }) => [status, count]),
    ),
    catalogs: resultRows(catalogs),
  };
};

export const queryCoaReports = async (database) => {
  const result = await database.prepare(`
    SELECT report_id, title, report_type, audited_entity, fiscal_year, publication_date,
      source_url, landing_url, acquisition_status, artifact_sha256, byte_size, page_count,
      scope_note, evidence_note
    FROM coa_reports ORDER BY fiscal_year DESC, report_type, report_id
  `).all();
  return resultRows(result);
};

export const getCoaReport = (database, reportId) => database.prepare(`
  SELECT report_id, title, report_type, audited_entity, fiscal_year, publication_date,
    source_url, landing_url, acquisition_status, artifact_sha256, byte_size, page_count,
    scope_note, evidence_note
  FROM coa_reports WHERE report_id = ?
`).bind(reportId).first();

export const getProjectCoaEvidence = async (database, contractId) => {
  const row = await database.prepare(`
    SELECT c.*, r.title AS report_title, r.report_type, r.audited_entity,
      r.publication_date, r.source_url, r.landing_url, r.acquisition_status,
      r.artifact_sha256, r.scope_note, r.evidence_note
    FROM coa_project_coverage c
    LEFT JOIN coa_reports r ON r.report_id = c.report_id
    WHERE c.contract_id = ?
  `).bind(contractId).first();
  return coverageRecord(row);
};

export const getCoaDesk = async (database) => {
  const [summary, reports] = await Promise.all([
    getCoaSummary(database),
    queryCoaReports(database),
  ]);
  return { summary, reports };
};
