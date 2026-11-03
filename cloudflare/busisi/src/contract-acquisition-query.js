import { getDeliveryRecord } from './record-query.js';

const rows = (result) => result.results || [];

const metadataObject = (records) => Object.fromEntries(
  rows(records).map((item) => [item.key, item.value]),
);

const quarantineRows = (records) => {
  const grouped = new Map();
  for (const row of rows(records)) {
    const item = grouped.get(row.source_row_id) || {
      source_row_id: row.source_row_id,
      reason: row.reason,
      row_sha256: row.row_sha256,
      reference_id: row.reference_id,
      contract_no: row.contract_no,
      award_title: row.award_title,
      notice_title: row.notice_title,
      candidates: [],
    };
    item.candidates.push({
      contract_id: row.candidate_contract_id,
      fiscal_year: row.candidate_fiscal_year,
      description: row.candidate_description,
      budget_centavos: row.candidate_budget_centavos,
      location: row.candidate_location,
    });
    grouped.set(row.source_row_id, item);
  }
  return [...grouped.values()];
};

export const getContractAcquisition = async (database, contractId) => {
  const acquisition = await database.prepare(`
    SELECT * FROM contract_acquisition_details WHERE contract_id = ?
  `).bind(contractId).first();
  if (!acquisition) return null;

  const [delivery, metadata, matches, quarantine] = await Promise.all([
    getDeliveryRecord(database, contractId),
    database.prepare(`
      SELECT key, value FROM contract_acquisition_metadata ORDER BY key
    `).all(),
    database.prepare(`
      SELECT * FROM contract_award_matches
      WHERE contract_id = ? ORDER BY award_date ASC, source_row_id ASC
    `).bind(contractId).all(),
    database.prepare(`
      SELECT q.*, candidate.contract_id AS candidate_contract_id,
        delivery.fiscal_year AS candidate_fiscal_year,
        delivery.description AS candidate_description,
        delivery.budget_centavos AS candidate_budget_centavos,
        delivery.location AS candidate_location
      FROM contract_quarantine_rows q
      JOIN contract_quarantine_candidates affected
        ON affected.source_row_id = q.source_row_id AND affected.contract_id = ?
      JOIN contract_quarantine_candidates candidate
        ON candidate.source_row_id = q.source_row_id
      LEFT JOIN delivery_items delivery ON delivery.contract_id = candidate.contract_id
      ORDER BY q.source_row_id ASC, candidate.contract_id ASC
    `).bind(contractId).all(),
  ]);

  return {
    ...(delivery || { record: { contract_id: contractId, fiscal_year: acquisition.fiscal_year } }),
    acquisition,
    metadata: metadataObject(metadata),
    award_matches: rows(matches),
    quarantine: quarantineRows(quarantine),
  };
};
