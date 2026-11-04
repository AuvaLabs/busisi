CREATE TABLE accountability_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE contractor_blacklist_events (
    order_id TEXT PRIMARY KEY,
    contractor_key TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    pcab_id TEXT NOT NULL,
    reported_name TEXT NOT NULL,
    identity_state TEXT NOT NULL CHECK (identity_state = 'pcab_name_exact'),
    procuring_entity TEXT NOT NULL,
    project_title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'expired', 'scheduled')),
    source_sha256 TEXT NOT NULL
);

CREATE INDEX contractor_blacklist_identity
ON contractor_blacklist_events (contractor_key, start_date DESC, order_id);

CREATE INDEX contractor_blacklist_status
ON contractor_blacklist_events (status, start_date DESC, order_id);

CREATE TABLE contractor_cpes_events (
    rating_id TEXT PRIMARY KEY,
    contractor_key TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    pcab_id TEXT NOT NULL,
    reported_name TEXT NOT NULL,
    identity_state TEXT NOT NULL CHECK (identity_state = 'pcab_id_exact'),
    project_title TEXT NOT NULL,
    evaluation_date TEXT NOT NULL,
    implementing_agency TEXT NOT NULL,
    visit_rating_bps INTEGER NOT NULL CHECK (visit_rating_bps BETWEEN 0 AND 10000),
    final_rating_bps INTEGER NOT NULL CHECK (final_rating_bps BETWEEN 0 AND 10000),
    qualitative_rating TEXT NOT NULL CHECK (qualitative_rating IN ('Poor', 'Unsatisfactory')),
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    release_label TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL
);

CREATE INDEX contractor_cpes_identity
ON contractor_cpes_events (contractor_key, evaluation_date DESC, rating_id);

CREATE TABLE contractor_award_timing_signals (
    signal_id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL CHECK (
        signal_type IN ('award_during_blacklist', 'award_after_low_cpes')
    ),
    contractor_key TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    pcab_id TEXT NOT NULL,
    evidence_event_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    relationship TEXT NOT NULL CHECK (relationship IN ('sole', 'joint')),
    match_basis TEXT NOT NULL CHECK (match_basis IN ('structured_exact', 'title_exact')),
    awardee_name TEXT NOT NULL,
    award_date TEXT NOT NULL,
    contract_amount_centavos INTEGER NOT NULL CHECK (contract_amount_centavos >= 0),
    award_row_sha256 TEXT NOT NULL
);

CREATE INDEX contractor_award_timing_identity
ON contractor_award_timing_signals (contractor_key, award_date DESC, signal_id);

CREATE INDEX contractor_award_timing_type
ON contractor_award_timing_signals (signal_type, award_date DESC, signal_id);
