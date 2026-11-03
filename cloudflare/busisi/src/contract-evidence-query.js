const rows = (result) => result.results || [];

const evidenceItem = (row) => ({
  ...row,
  retry_eligible: Boolean(row.retry_eligible),
});

export const getContractEvidenceSummary = async (database) => {
  const result = await database.prepare(
    'SELECT key, value FROM contract_evidence_metadata ORDER BY key',
  ).all();
  const metadata = {};
  const statuses = {};
  for (const item of rows(result)) {
    if (item.key.startsWith('status:')) statuses[item.key.slice(7)] = Number(item.value);
    else metadata[item.key] = item.value;
  }
  return { metadata, statuses };
};

export const queryContractEvidenceItems = async (database) => {
  const result = await database.prepare(`
    SELECT * FROM contract_evidence_items
    ORDER BY fiscal_year DESC, contract_id, stage_order
  `).all();
  return rows(result).map(evidenceItem);
};

export const getProjectContractEvidence = async (database, contractId) => {
  const result = await database.prepare(`
    SELECT * FROM contract_evidence_items
    WHERE contract_id = ? ORDER BY stage_order
  `).bind(contractId).all();
  return rows(result).map(evidenceItem);
};
