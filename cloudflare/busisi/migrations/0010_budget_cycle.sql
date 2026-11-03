CREATE TABLE budget_cycle_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE budget_cycle_stages (
    stage TEXT PRIMARY KEY CHECK (stage IN (
        'nep', 'house_gab', 'senate_committee', 'senate_amendment', 'bicam', 'gaa'
    )),
    sequence INTEGER NOT NULL UNIQUE CHECK (sequence BETWEEN 1 AND 6),
    status TEXT NOT NULL CHECK (status IN (
        'available', 'available_elsewhere', 'partial', 'unavailable'
    )),
    document_count INTEGER NOT NULL CHECK (document_count >= 0)
);

CREATE TABLE budget_cycle_documents (
    document_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    source_record_id TEXT NOT NULL,
    title TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN (
        'nep', 'house_gab', 'senate_committee', 'senate_amendment',
        'bicam', 'gaa', 'supporting', 'unknown'
    )),
    stage_label TEXT NOT NULL,
    publisher TEXT NOT NULL,
    volume TEXT,
    publication_date TEXT,
    source_url TEXT NOT NULL,
    viewer_url TEXT NOT NULL,
    acquisition_status TEXT NOT NULL CHECK (acquisition_status IN (
        'discovered', 'verified_archived', 'unavailable'
    )),
    artifact_sha256 TEXT CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size > 0),
    mirror_url TEXT,
    evidence_note TEXT NOT NULL,
    CHECK (
        acquisition_status != 'verified_archived'
        OR (artifact_sha256 IS NOT NULL AND byte_size IS NOT NULL AND mirror_url IS NOT NULL)
    ),
    CHECK (
        acquisition_status = 'verified_archived'
        OR (artifact_sha256 IS NULL AND byte_size IS NULL AND mirror_url IS NULL)
    )
);

CREATE INDEX budget_cycle_document_stage
    ON budget_cycle_documents (fiscal_year, stage, publication_date, document_id);
CREATE INDEX budget_cycle_document_status
    ON budget_cycle_documents (acquisition_status, stage, document_id);
