CREATE TABLE procurement_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE procurement_sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN (
        'annual_procurement_plan', 'bid_notice', 'procurement_monitoring_report'
    )),
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    reporting_cutoff TEXT,
    source_url TEXT NOT NULL,
    acquisition_status TEXT NOT NULL CHECK (acquisition_status IN (
        'discovered', 'verified_archived', 'blocked', 'not_located'
    )),
    artifact_sha256 TEXT CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size > 0),
    page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
    evidence_note TEXT NOT NULL,
    CHECK (
        acquisition_status != 'verified_archived'
        OR (artifact_sha256 IS NOT NULL AND byte_size IS NOT NULL)
    ),
    CHECK (
        acquisition_status = 'verified_archived'
        OR (artifact_sha256 IS NULL AND byte_size IS NULL AND page_count IS NULL)
    )
);

CREATE TABLE procurement_records (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    source_id TEXT NOT NULL REFERENCES procurement_sources(source_id),
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('plan', 'bid_notice', 'monitoring_report')),
    match_basis TEXT NOT NULL CHECK (match_basis IN ('exact_contract_id', 'exact_solicitation_number')),
    project_title TEXT NOT NULL,
    procuring_entity TEXT NOT NULL,
    procurement_mode TEXT NOT NULL,
    procurement_status TEXT NOT NULL,
    page_number INTEGER CHECK (page_number IS NULL OR page_number > 0),
    reference_number TEXT,
    abc_centavos INTEGER CHECK (abc_centavos IS NULL OR abc_centavos >= 0),
    contract_cost_centavos INTEGER CHECK (contract_cost_centavos IS NULL OR contract_cost_centavos >= 0),
    savings_centavos INTEGER CHECK (savings_centavos IS NULL OR savings_centavos >= 0),
    observers_json TEXT NOT NULL CHECK (json_valid(observers_json)),
    events_json TEXT NOT NULL CHECK (json_valid(events_json)),
    reviewed_at TEXT NOT NULL,
    boundary_note TEXT NOT NULL,
    CHECK (
        contract_cost_centavos IS NULL
        OR (abc_centavos IS NOT NULL AND contract_cost_centavos <= abc_centavos)
    ),
    CHECK (
        savings_centavos IS NULL
        OR savings_centavos = abc_centavos - contract_cost_centavos
    )
);

CREATE TABLE procurement_project_coverage (
    case_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL UNIQUE,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    status TEXT NOT NULL CHECK (status IN (
        'exact_evidence', 'partial_evidence', 'not_located',
        'current_year_not_yet_located', 'quarantined'
    )),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    review_note TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    CHECK (
        (status IN ('exact_evidence', 'partial_evidence') AND record_count > 0)
        OR (status IN ('not_located', 'current_year_not_yet_located', 'quarantined') AND record_count = 0)
    )
);

CREATE INDEX procurement_records_contract
    ON procurement_records (contract_id, fiscal_year, evidence_type);
CREATE INDEX procurement_coverage_status
    ON procurement_project_coverage (status, fiscal_year, contract_id);
