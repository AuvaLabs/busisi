import { queryContractOutcomes } from './outcome-query.js';
import {
  getContractEvidenceSummary,
  queryContractEvidenceItems,
} from './contract-evidence-query.js';
import { getAcquisitionCoverage } from './acquisition-coverage-query.js';

const resultRows = (result) => result.results || [];

const safeArray = (value) => {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const procurementRecord = (row) => row && ({
  ...row,
  observers: safeArray(row.observers_json),
  events: safeArray(row.events_json),
  observers_json: undefined,
  events_json: undefined,
});

const metadata = async (database) => {
  const result = await database.prepare(
    'SELECT key, value FROM procurement_metadata ORDER BY key',
  ).all();
  return Object.fromEntries(resultRows(result).map(({ key, value }) => [key, value]));
};

export const getProcurementSummary = async (database) => {
  const [meta, statuses] = await Promise.all([
    metadata(database),
    database.prepare(`
      SELECT status, COUNT(*) AS record_count
      FROM procurement_project_coverage GROUP BY status ORDER BY status
    `).all(),
  ]);
  return {
    metadata: meta,
    statuses: Object.fromEntries(
      resultRows(statuses).map(({ status, record_count: count }) => [status, count]),
    ),
  };
};

export const queryProcurementSources = async (database) => {
  const result = await database.prepare(`
    SELECT source_id, title, publisher, document_type, fiscal_year, reporting_cutoff,
      source_url, acquisition_status, artifact_sha256, byte_size, page_count, evidence_note
    FROM procurement_sources ORDER BY fiscal_year DESC, document_type, source_id
  `).all();
  return resultRows(result);
};

export const queryProcurementRecords = async (database) => {
  const result = await database.prepare(`
    SELECT r.*, s.title AS source_title, s.publisher, s.source_url,
      s.acquisition_status, s.artifact_sha256, s.byte_size
    FROM procurement_records r
    JOIN procurement_sources s ON s.source_id = r.source_id
    ORDER BY r.fiscal_year DESC, r.contract_id, r.evidence_type, r.evidence_id
  `).all();
  return resultRows(result).map(procurementRecord);
};

const queryCoverage = async (database) => {
  const result = await database.prepare(`
    SELECT case_id, contract_id, fiscal_year, status, record_count, review_note, reviewed_at
    FROM procurement_project_coverage ORDER BY fiscal_year DESC, contract_id
  `).all();
  return resultRows(result);
};

export const getProjectProcurementEvidence = async (database, contractId) => {
  const [coverage, records] = await Promise.all([
    database.prepare(`
      SELECT case_id, contract_id, fiscal_year, status, record_count, review_note, reviewed_at
      FROM procurement_project_coverage WHERE contract_id = ?
    `).bind(contractId).first(),
    database.prepare(`
      SELECT r.*, s.title AS source_title, s.publisher, s.source_url,
        s.acquisition_status, s.artifact_sha256, s.byte_size
      FROM procurement_records r
      JOIN procurement_sources s ON s.source_id = r.source_id
      WHERE r.contract_id = ?
      ORDER BY r.evidence_type, r.evidence_id
    `).bind(contractId).all(),
  ]);
  if (!coverage) return null;
  return { coverage, records: resultRows(records).map(procurementRecord) };
};

export const getProcurementDesk = async (database) => {
  const [
    summary, sources, coverage, outcomes, evidenceSummary, evidenceItems, acquisitionCoverage,
  ] = await Promise.all([
    getProcurementSummary(database),
    queryProcurementSources(database),
    queryCoverage(database),
    queryContractOutcomes(database),
    getContractEvidenceSummary(database),
    queryContractEvidenceItems(database),
    getAcquisitionCoverage(database),
  ]);
  return {
    summary, sources, coverage, outcomes, evidenceSummary, evidenceItems, acquisitionCoverage,
  };
};
