CREATE TABLE contract_acquisition_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE contract_acquisition_details (
    contract_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    identifier_status TEXT NOT NULL CHECK (identifier_status IN ('valid', 'invalid')),
    year_alignment TEXT NOT NULL CHECK (year_alignment IN ('aligned', 'conflict')),
    match_state TEXT NOT NULL CHECK (match_state IN (
        'structured_exact', 'title_exact', 'multiple_exact_rows',
        'conflict_review', 'no_exact_row', 'invalid_identifier'
    )),
    accepted_match_rows INTEGER NOT NULL CHECK (accepted_match_rows >= 0),
    quarantined_match_rows INTEGER NOT NULL CHECK (quarantined_match_rows >= 0)
);

CREATE TABLE contract_award_matches (
    source_row_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    match_basis TEXT NOT NULL CHECK (match_basis IN ('structured_exact', 'title_exact')),
    reference_id TEXT,
    contract_no TEXT,
    award_title TEXT,
    notice_title TEXT NOT NULL,
    awardee_name TEXT NOT NULL,
    organization_name TEXT NOT NULL,
    area_of_delivery TEXT NOT NULL,
    business_category TEXT NOT NULL,
    contract_amount_centavos INTEGER NOT NULL CHECK (contract_amount_centavos >= 0),
    award_date TEXT NOT NULL,
    award_status TEXT NOT NULL,
    row_sha256 TEXT NOT NULL CHECK (length(row_sha256) = 64),
    FOREIGN KEY (contract_id) REFERENCES contract_acquisition_details(contract_id)
);

CREATE TABLE contract_quarantine_rows (
    source_row_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    row_sha256 TEXT NOT NULL CHECK (length(row_sha256) = 64),
    reference_id TEXT,
    contract_no TEXT,
    award_title TEXT,
    notice_title TEXT NOT NULL
);

CREATE TABLE contract_quarantine_candidates (
    source_row_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    PRIMARY KEY (source_row_id, contract_id),
    FOREIGN KEY (source_row_id) REFERENCES contract_quarantine_rows(source_row_id),
    FOREIGN KEY (contract_id) REFERENCES contract_acquisition_details(contract_id)
);

CREATE INDEX contract_acquisition_state
ON contract_acquisition_details (match_state, fiscal_year, contract_id);
CREATE INDEX contract_award_match_contract
ON contract_award_matches (contract_id, award_date, source_row_id);
CREATE INDEX contract_quarantine_candidate_contract
ON contract_quarantine_candidates (contract_id, source_row_id);
