CREATE TABLE community_poverty_estimates (
    psgc_code TEXT PRIMARY KEY CHECK (
        length(psgc_code) = 10 AND psgc_code NOT GLOB '*[^0-9]*'
    ),
    name TEXT NOT NULL,
    estimate_year INTEGER NOT NULL CHECK (estimate_year = 2023),
    poverty_incidence_bps INTEGER NOT NULL CHECK (
        poverty_incidence_bps BETWEEN 0 AND 10000
    ),
    standard_error_bps INTEGER NOT NULL CHECK (standard_error_bps BETWEEN 0 AND 10000),
    coefficient_variation_bps INTEGER NOT NULL CHECK (
        coefficient_variation_bps BETWEEN 0 AND 10000
    ),
    confidence_lower_bps INTEGER NOT NULL CHECK (
        confidence_lower_bps BETWEEN 0 AND poverty_incidence_bps
    ),
    confidence_upper_bps INTEGER NOT NULL CHECK (
        confidence_upper_bps BETWEEN poverty_incidence_bps AND 10000
    ),
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    source_url TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);
CREATE INDEX community_poverty_incidence
ON community_poverty_estimates (poverty_incidence_bps DESC, psgc_code);

CREATE TABLE community_poverty_status (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    checked_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_state TEXT NOT NULL CHECK (source_state IN (
        'blocked', 'acquisition_failure', 'validation_failure', 'validated'
    )),
    publication_state TEXT NOT NULL CHECK (publication_state IN (
        'not_published', 'ready_for_review', 'published'
    )),
    http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
    source_sha256 TEXT CHECK (source_sha256 IS NULL OR length(source_sha256) = 64),
    expected_records INTEGER NOT NULL CHECK (expected_records > 0),
    validated_records INTEGER NOT NULL CHECK (
        validated_records >= 0 AND validated_records <= expected_records
    ),
    failure_kind TEXT,
    last_success_at TEXT,
    consecutive_failures INTEGER NOT NULL CHECK (consecutive_failures >= 0),
    next_check_at TEXT,
    freshness_state TEXT NOT NULL CHECK (
        freshness_state IN ('fresh', 'degraded', 'stale', 'unknown')
    ),
    response_sha256 TEXT CHECK (response_sha256 IS NULL OR length(response_sha256) = 64),
    status_note TEXT NOT NULL,
    status_sha256 TEXT NOT NULL CHECK (length(status_sha256) = 64)
);
