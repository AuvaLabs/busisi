export const getFacilityRegistryStatus = async (database) => {
  const record = await database.prepare(`
    SELECT checked_at, source_url, source_state, release_state, http_status,
      source_artifact_sha256, expected_facilities, validated_facilities,
      candidate_links, reviewed_cases, precision_bps, agreement_bps,
      critical_failures, status_note, status_sha256
    FROM facility_registry_status WHERE singleton_id = 1
  `).first();
  return record || null;
};
