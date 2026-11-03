export const getCoverageStatus = async (database) => {
  const record = await database.prepare(`
    SELECT release_id, released_at, source_sha256, universe_contracts,
      completed_contracts, verified_exact_contracts, no_image_contracts,
      conflict_contracts, retry_contracts, blocked_contracts, pending_contracts,
      verified_images, quarantined_images
    FROM coverage_releases
    ORDER BY released_at DESC, release_id DESC LIMIT 1
  `).first();
  return record || null;
};
