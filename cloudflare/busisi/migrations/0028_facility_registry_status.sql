CREATE TABLE facility_registry_status (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    checked_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_state TEXT NOT NULL CHECK (source_state IN (
        'blocked', 'unavailable', 'acquisition_failure', 'validation_failure', 'validated'
    )),
    release_state TEXT NOT NULL CHECK (release_state IN (
        'source_blocked', 'source_unavailable', 'acquisition_failed', 'validation_failed',
        'awaiting_review', 'gate_failed', 'ready_for_publication', 'published'
    )),
    http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
    source_artifact_sha256 TEXT CHECK (
        source_artifact_sha256 IS NULL OR length(source_artifact_sha256) = 64
    ),
    expected_facilities INTEGER NOT NULL CHECK (expected_facilities > 0),
    validated_facilities INTEGER NOT NULL CHECK (
        validated_facilities >= 0 AND validated_facilities <= expected_facilities
    ),
    candidate_links INTEGER NOT NULL CHECK (candidate_links >= 0),
    reviewed_cases INTEGER NOT NULL CHECK (reviewed_cases >= 0),
    precision_bps INTEGER CHECK (precision_bps BETWEEN 0 AND 10000),
    agreement_bps INTEGER CHECK (agreement_bps BETWEEN 0 AND 10000),
    critical_failures INTEGER NOT NULL CHECK (critical_failures >= 0),
    status_note TEXT NOT NULL,
    status_sha256 TEXT NOT NULL CHECK (length(status_sha256) = 64)
);
