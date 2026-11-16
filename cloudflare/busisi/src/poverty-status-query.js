export const getPovertyStatus = async (database) => {
  const record = await database.prepare(`
    SELECT checked_at, source_url, source_state, publication_state, http_status,
      source_sha256, expected_records, validated_records, failure_kind,
      last_success_at, consecutive_failures, next_check_at, freshness_state,
      response_sha256, status_note, status_sha256
    FROM community_poverty_status WHERE singleton_id = 1
  `).first();
  return record || null;
};
