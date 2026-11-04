const rows = (result) => result.results || [];

const readerUrl = (record) => {
  if (record.source_type === 'delivery') {
    return `/contracts/${encodeURIComponent(record.record_id)}/`;
  }
  if (record.record_kind === 'stage_change') {
    return `/records/change/${encodeURIComponent(record.record_id)}/`;
  }
  return `/records/budget/${encodeURIComponent(record.record_id)}/`;
};

export const getFacility = async (database, facilityId) => {
  const record = await database.prepare(`
    SELECT identity.*, detail.division, detail.source_row,
      detail.demolition_required, detail.geotechnical_report,
      detail.site_development_plan, detail.ownership_documents,
      source.publisher, source.dataset_name, source.source_url,
      source.artifact_sha256, source.acquired_at, source.scope_note, source.status AS source_status
    FROM facility_identities identity
    JOIN facility_registry_sources source ON source.source_id = identity.source_id
    LEFT JOIN facility_identity_details detail ON detail.facility_id = identity.facility_id
    WHERE identity.facility_id = ?
  `).bind(facilityId).first();
  if (!record) return null;
  const result = await database.prepare(`
    SELECT link.source_type, link.record_id, link.match_state, link.match_method,
      link.confidence, link.signals_json, link.limitation, link.reviewed_at,
      'stage_change' AS record_kind, change.fiscal_year, change.title,
      CASE WHEN change.house_centavos > 0 THEN change.house_centavos ELSE change.nep_centavos END
        AS amount_centavos,
      change.region AS location, change.office, change.change_label AS status
    FROM facility_record_links link
    JOIN stage_change_items change ON change.record_id = link.record_id
    WHERE link.facility_id = ? AND link.source_type = 'budget'
    UNION ALL
    SELECT link.source_type, link.record_id, link.match_state, link.match_method,
      link.confidence, link.signals_json, link.limitation, link.reviewed_at,
      'budget' AS record_kind, budget.fiscal_year, budget.description AS title,
      budget.amount_centavos, '' AS location, '' AS office, '' AS status
    FROM facility_record_links link
    JOIN budget_items budget ON budget.record_id = link.record_id
    WHERE link.facility_id = ? AND link.source_type = 'budget'
      AND NOT EXISTS (SELECT 1 FROM stage_change_items change WHERE change.record_id = link.record_id)
    UNION ALL
    SELECT link.source_type, link.record_id, link.match_state, link.match_method,
      link.confidence, link.signals_json, link.limitation, link.reviewed_at,
      'delivery' AS record_kind, delivery.fiscal_year, delivery.description AS title,
      delivery.budget_centavos AS amount_centavos, delivery.location,
      COALESCE(detail.province, '') AS office, COALESCE(detail.status, '') AS status
    FROM facility_record_links link
    JOIN delivery_items delivery ON delivery.contract_id = link.record_id
    LEFT JOIN delivery_project_details detail ON detail.contract_id = delivery.contract_id
    WHERE link.facility_id = ? AND link.source_type = 'delivery'
    ORDER BY fiscal_year DESC, record_id ASC
  `).bind(facilityId, facilityId, facilityId).all();
  const links = rows(result).map((item) => ({
    ...item,
    signals: (() => {
      try {
        const parsed = JSON.parse(item.signals_json);
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return [];
      }
    })(),
    signals_json: undefined,
    reader_url: readerUrl(item),
  }));
  const budget = links.filter(({ source_type }) => source_type === 'budget');
  const delivery = links.filter(({ source_type }) => source_type === 'delivery');
  return Object.freeze({
    record,
    links,
    summary: Object.freeze({
      record_count: links.length,
      budget_records: budget.length,
      delivery_records: delivery.length,
      budget_amount_centavos: budget.reduce((sum, item) => sum + Number(item.amount_centavos), 0),
      delivery_amount_centavos: delivery.reduce((sum, item) => sum + Number(item.amount_centavos), 0),
      first_year: links.length ? Math.min(...links.map(({ fiscal_year }) => fiscal_year)) : null,
      last_year: links.length ? Math.max(...links.map(({ fiscal_year }) => fiscal_year)) : null,
    }),
  });
};
