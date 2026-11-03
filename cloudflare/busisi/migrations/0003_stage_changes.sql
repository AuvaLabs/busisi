CREATE TABLE stage_change_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE stage_change_items (
    record_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    dataset TEXT NOT NULL CHECK (dataset IN ('dpwh', 'fmr', 'hfep', 'nia')),
    title TEXT NOT NULL,
    program TEXT NOT NULL,
    pap TEXT NOT NULL,
    region TEXT NOT NULL,
    office TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (
        change_type IN ('house_only', 'nep_only', 'unchanged', 'increased', 'decreased', 'scope_review')
    ),
    change_label TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN ('candidate', 'quarantine')),
    held INTEGER NOT NULL CHECK (held IN (0, 1)),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    nep_centavos INTEGER NOT NULL CHECK (nep_centavos >= 0),
    house_centavos INTEGER NOT NULL CHECK (house_centavos >= 0),
    difference_centavos INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    nep_pdf_url TEXT NOT NULL,
    house_pdf_url TEXT NOT NULL,
    nep_page INTEGER,
    house_page INTEGER,
    source_commit TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL
);

CREATE INDEX stage_changes_type ON stage_change_items (change_type, difference_centavos DESC, record_id);
CREATE INDEX stage_changes_dataset ON stage_change_items (dataset, difference_centavos DESC, record_id);
CREATE INDEX stage_changes_region ON stage_change_items (region, record_id);
CREATE INDEX stage_changes_review ON stage_change_items (review_status, record_id);
