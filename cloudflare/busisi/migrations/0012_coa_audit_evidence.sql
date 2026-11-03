CREATE TABLE coa_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE coa_source_catalogs (
    catalog_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    checked_status TEXT NOT NULL CHECK (checked_status IN (
        'reachable', 'reachable_by_index', 'blocked', 'unavailable'
    )),
    evidence_note TEXT NOT NULL
);

CREATE TABLE coa_reports (
    report_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type IN (
        'annual_audit_report', 'compliance_audit', 'performance_audit',
        'citizen_participatory_audit', 'special_audit', 'oda_consolidated_audit'
    )),
    audited_entity TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    publication_date TEXT,
    source_url TEXT NOT NULL,
    landing_url TEXT NOT NULL,
    acquisition_status TEXT NOT NULL CHECK (acquisition_status IN (
        'discovered', 'verified_archived', 'unavailable'
    )),
    artifact_sha256 TEXT CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size > 0),
    page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
    scope_note TEXT NOT NULL,
    evidence_note TEXT NOT NULL,
    CHECK (
        acquisition_status != 'verified_archived'
        OR (artifact_sha256 IS NOT NULL AND byte_size IS NOT NULL AND page_count IS NOT NULL)
    ),
    CHECK (
        acquisition_status = 'verified_archived'
        OR (artifact_sha256 IS NULL AND byte_size IS NULL AND page_count IS NULL)
    )
);

CREATE TABLE coa_project_coverage (
    case_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL UNIQUE,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    status TEXT NOT NULL CHECK (status IN (
        'not_covered', 'agency_report_available', 'program_audit_available',
        'candidate_observation_match', 'reviewed_observation_match',
        'resolved_or_implemented'
    )),
    report_id TEXT REFERENCES coa_reports(report_id),
    match_confidence TEXT NOT NULL CHECK (match_confidence IN ('none', 'candidate', 'high', 'exact')),
    match_basis_json TEXT NOT NULL CHECK (json_valid(match_basis_json)),
    page_start INTEGER CHECK (page_start IS NULL OR page_start > 0),
    page_end INTEGER CHECK (page_end IS NULL OR page_end >= page_start),
    observation_summary TEXT NOT NULL,
    recommendation_summary TEXT NOT NULL,
    management_response TEXT NOT NULL,
    implementation_status TEXT NOT NULL CHECK (implementation_status IN (
        'not_applicable', 'not_stated', 'pending', 'in_progress', 'implemented', 'unresolved'
    )),
    review_note TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    CHECK ((page_start IS NULL) = (page_end IS NULL)),
    CHECK (status != 'not_covered' OR (report_id IS NULL AND match_confidence = 'none')),
    CHECK (status = 'not_covered' OR report_id IS NOT NULL)
);

CREATE INDEX coa_reports_year_type
    ON coa_reports (fiscal_year DESC, report_type, report_id);
CREATE INDEX coa_coverage_contract
    ON coa_project_coverage (contract_id, status);
