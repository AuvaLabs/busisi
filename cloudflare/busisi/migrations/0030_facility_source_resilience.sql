ALTER TABLE facility_registry_status ADD COLUMN failure_kind TEXT CHECK (
    failure_kind IS NULL OR failure_kind IN (
        'publisher_maintenance', 'bot_challenge', 'rate_limited', 'server_error',
        'access_denied', 'not_found', 'transport_error', 'unexpected_response',
        'validation_error'
    )
);
ALTER TABLE facility_registry_status ADD COLUMN last_success_at TEXT;
ALTER TABLE facility_registry_status ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0
    CHECK (consecutive_failures >= 0);
ALTER TABLE facility_registry_status ADD COLUMN next_check_at TEXT;
ALTER TABLE facility_registry_status ADD COLUMN freshness_state TEXT NOT NULL DEFAULT 'unknown'
    CHECK (freshness_state IN ('fresh', 'degraded', 'stale', 'unknown'));
ALTER TABLE facility_registry_status ADD COLUMN response_sha256 TEXT CHECK (
    response_sha256 IS NULL OR length(response_sha256) = 64
);
ALTER TABLE facility_registry_status ADD COLUMN source_version TEXT;
ALTER TABLE facility_registry_status ADD COLUMN candidate_source_url TEXT;
ALTER TABLE facility_registry_status ADD COLUMN candidate_state TEXT CHECK (
    candidate_state IS NULL OR candidate_state IN (
        'discovered_unarchived', 'archived_unvalidated', 'validated'
    )
);
