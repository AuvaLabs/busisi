export const getFacilityRegistryStatus = async (database) => {
  const record = await database.prepare(`
    SELECT checked_at, source_url, source_state, release_state, http_status,
      source_artifact_sha256, expected_facilities, validated_facilities,
      candidate_links, reviewed_cases, precision_bps, agreement_bps,
      critical_failures, status_note, status_sha256, failure_kind,
      last_success_at, consecutive_failures, next_check_at, freshness_state,
      response_sha256, source_version, candidate_source_url, candidate_state
    FROM facility_registry_status WHERE singleton_id = 1
  `).first();
  return record || null;
};
