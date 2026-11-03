CREATE TABLE agency_budget_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE agency_budget_items (
    record_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    baseline_year INTEGER NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('appropriation_head', 'congress_institution')),
    parent_id TEXT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    base_centavos INTEGER NOT NULL CHECK (base_centavos >= 0),
    nep_centavos INTEGER NOT NULL CHECK (nep_centavos >= 0),
    house_centavos INTEGER CHECK (house_centavos >= 0),
    difference_centavos INTEGER,
    change_bps INTEGER,
    stage_status TEXT NOT NULL CHECK (stage_status IN ('compared', 'not_applicable')),
    house_document_key TEXT,
    house_pages_json TEXT NOT NULL,
    house_source_url TEXT,
    nep_source_url TEXT NOT NULL,
    nep_artifact_sha256 TEXT NOT NULL,
    house_artifact_sha256 TEXT,
    source_note TEXT NOT NULL,
    CHECK (
        (stage_status = 'compared' AND house_centavos IS NOT NULL AND difference_centavos IS NOT NULL)
        OR
        (stage_status = 'not_applicable' AND house_centavos IS NULL AND difference_centavos IS NULL)
    )
);

CREATE INDEX agency_budget_amount ON agency_budget_items (level, house_centavos DESC, record_id);
CREATE INDEX agency_budget_change ON agency_budget_items (level, difference_centavos DESC, record_id);
CREATE INDEX agency_budget_name ON agency_budget_items (name, record_id);
