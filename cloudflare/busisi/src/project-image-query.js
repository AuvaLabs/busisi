const rows = (result) => result.results || [];

export const getProjectImageEvidence = async (database, contractId) => {
  const [coverage, images] = await Promise.all([
    database.prepare(`
      SELECT contract_id, summary_count, endpoint_count, has_images, state,
        detail_sha256, list_sha256, retrieved_at, note
      FROM project_image_coverage WHERE contract_id = ?
    `).bind(contractId).first(),
    database.prepare(`
      SELECT image_id, contract_id, component_id, photo_number, purpose, source_status,
        captured_at, fiscal_year, latitude, longitude, coordinate_status, source_url,
        artifact_sha256, content_type, byte_size, width, height
      FROM project_images
      WHERE contract_id = ? AND publication_status = 'verified'
      ORDER BY photo_number ASC, image_id ASC
    `).bind(contractId).all(),
  ]);
  return { coverage, images: rows(images) };
};
