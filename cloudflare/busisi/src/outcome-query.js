import { buildContractOutcome } from './contract-outcome.js';

const rows = (result) => result.results || [];

const safeArray = (value) => {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const procurementRecord = (row) => ({
  ...row,
  events: safeArray(row.events_json),
  events_json: undefined,
});

const groupRecords = (records) => records.reduce((grouped, record) => {
  const existing = grouped.get(record.contract_id) || [];
  grouped.set(record.contract_id, [...existing, procurementRecord(record)]);
  return grouped;
}, new Map());

const queryCoverage = async (database) => rows(await database.prepare(`
  SELECT case_id, contract_id, fiscal_year, status, record_count, review_note, reviewed_at
  FROM procurement_project_coverage
  WHERE status IN ('exact_evidence', 'partial_evidence')
  ORDER BY fiscal_year DESC, contract_id
`).all());

const queryRecords = async (database) => rows(await database.prepare(`
  SELECT r.* FROM procurement_records r
  JOIN procurement_project_coverage c ON c.contract_id = r.contract_id
  WHERE c.status IN ('exact_evidence', 'partial_evidence')
  ORDER BY r.contract_id, r.evidence_type, r.evidence_id
`).all());

const queryDeliveries = async (database) => rows(await database.prepare(`
  SELECT d.contract_id, d.fiscal_year, d.description, d.budget_centavos,
    detail.status, detail.progress, detail.contractor_name, detail.start_date,
    detail.completion_date, detail.source_artifact_sha256
  FROM delivery_items d
  JOIN procurement_project_coverage c ON c.contract_id = d.contract_id
  LEFT JOIN delivery_project_details detail ON detail.contract_id = d.contract_id
  WHERE c.status IN ('exact_evidence', 'partial_evidence')
  ORDER BY d.contract_id
`).all());

const queryAwards = async (database) => rows(await database.prepare(`
  SELECT a.* FROM contract_award_mirror_records a
  JOIN procurement_project_coverage c ON c.contract_id = a.contract_id
  WHERE c.status IN ('exact_evidence', 'partial_evidence')
  ORDER BY a.contract_id
`).all());

export const getContractAwardMirror = (database, contractId) => database.prepare(`
  SELECT * FROM contract_award_mirror_records WHERE contract_id = ?
`).bind(contractId).first();

export const queryContractOutcomes = async (database) => {
  const [coverage, records, deliveries, awards] = await Promise.all([
    queryCoverage(database),
    queryRecords(database),
    queryDeliveries(database),
    queryAwards(database),
  ]);
  const recordsByContract = groupRecords(records);
  const deliveryByContract = new Map(deliveries.map((item) => [item.contract_id, item]));
  const awardByContract = new Map(awards.map((item) => [item.contract_id, item]));
  return coverage.map((item) => buildContractOutcome({
    coverage: item,
    procurementRecords: recordsByContract.get(item.contract_id) || [],
    delivery: deliveryByContract.get(item.contract_id) || null,
    awardMirror: awardByContract.get(item.contract_id) || null,
  }));
};
