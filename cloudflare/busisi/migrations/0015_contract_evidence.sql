CREATE TABLE contract_evidence_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE contract_evidence_items (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    stage TEXT NOT NULL CHECK (stage IN (
        'procurement_plan', 'bid_notice', 'procurement_monitoring_report',
        'award_notice', 'signed_contract', 'notice_to_proceed',
        'completion_certificate', 'inspection_acceptance', 'payment_record'
    )),
    stage_order INTEGER NOT NULL CHECK (stage_order BETWEEN 0 AND 8),
    status TEXT NOT NULL CHECK (status IN (
        'verified_archived', 'indexed_unarchived', 'blocked', 'secondary', 'not_located'
    )),
    evidence_class TEXT NOT NULL CHECK (evidence_class IN (
        'official_artifact', 'official_report', 'secondary_mirror', 'unavailable'
    )),
    title TEXT NOT NULL,
    reported_date TEXT,
    date_kind TEXT CHECK (date_kind IS NULL OR date_kind IN ('planned', 'actual')),
    source_title TEXT,
    source_url TEXT,
    source_row_id TEXT,
    artifact_sha256 TEXT CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
    source_revision TEXT CHECK (source_revision IS NULL OR length(source_revision) = 40),
    last_checked_at TEXT NOT NULL,
    http_status INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    retry_eligible INTEGER NOT NULL CHECK (retry_eligible IN (0, 1)),
    limitation TEXT NOT NULL,
    UNIQUE (contract_id, stage),
    CHECK ((reported_date IS NULL) = (date_kind IS NULL)),
    CHECK ((source_title IS NULL) = (source_url IS NULL))
);

CREATE INDEX contract_evidence_contract
ON contract_evidence_items (contract_id, stage_order);

CREATE INDEX contract_evidence_status
ON contract_evidence_items (status, retry_eligible, fiscal_year, contract_id);
