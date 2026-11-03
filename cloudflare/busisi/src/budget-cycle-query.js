export const getBudgetCycleSummary = async (database) => {
  const [metadataResult, stageResult] = await Promise.all([
    database.prepare('SELECT key, value FROM budget_cycle_metadata ORDER BY key').all(),
    database.prepare(`
      SELECT stage, sequence, status, document_count
      FROM budget_cycle_stages ORDER BY sequence
    `).all(),
  ]);
  return {
    metadata: Object.fromEntries(metadataResult.results.map(({ key, value }) => [key, value])),
    stages: stageResult.results,
  };
};

export const queryBudgetCycleDocuments = async (database) => {
  const result = await database.prepare(`
    SELECT document_id, fiscal_year, source_record_id, title, stage, stage_label,
      publisher, volume, publication_date, source_url, viewer_url,
      acquisition_status, artifact_sha256, byte_size, mirror_url, evidence_note
    FROM budget_cycle_documents
    ORDER BY
      CASE stage
        WHEN 'nep' THEN 1 WHEN 'house_gab' THEN 2 WHEN 'senate_committee' THEN 3
        WHEN 'senate_amendment' THEN 4 WHEN 'bicam' THEN 5 WHEN 'gaa' THEN 6
        WHEN 'supporting' THEN 7 ELSE 8
      END,
      publication_date, document_id
  `).all();
  return result.results;
};
