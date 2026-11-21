export const getSenateCommitteeRelease = async (database) => {
  const release = await database.prepare(`
    SELECT release_id, fiscal_year, report_number, related_bill, state, checked_at,
      source_url, publication_date, artifact_sha256, byte_size, item_count,
      total_previous_centavos, total_senate_centavos, total_change_centavos, public_note
    FROM senate_committee_releases
    ORDER BY checked_at DESC, release_id DESC
    LIMIT 1
  `).first();
  if (!release) return { release: null, controls: [], changes: [] };
  const [controlResult, changeResult] = await Promise.all([
    database.prepare(`
      SELECT group_code, label, project_count, previous_centavos,
        senate_centavos, change_centavos
      FROM senate_committee_controls
      WHERE release_id = ?
      ORDER BY group_code
    `).bind(release.release_id).all(),
    database.prepare(`
      SELECT change_id, group_code, origin_stage, source_project_id, title,
        project_type, region, province, city_or_municipality, district,
        previous_centavos, senate_centavos, change_centavos, reason, source_page,
        match_state, linked_project_slug, public_note
      FROM senate_committee_changes
      WHERE release_id = ?
      ORDER BY ABS(change_centavos) DESC, change_id
      LIMIT 100
    `).bind(release.release_id).all(),
  ]);
  return {
    release,
    controls: controlResult.results,
    changes: changeResult.results,
  };
};
