CREATE TABLE allotment_release_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE allotment_release_items (
    record_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year = 2026),
    as_of_date TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    level TEXT NOT NULL CHECK (
        level IN ('department', 'attached_agency', 'subunit', 'special_purpose_fund')
    ),
    parent_id TEXT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    program_centavos INTEGER NOT NULL CHECK (program_centavos >= 0),
    adjustment_centavos INTEGER NOT NULL,
    adjusted_program_centavos INTEGER NOT NULL CHECK (adjusted_program_centavos >= 0),
    release_centavos INTEGER NOT NULL CHECK (release_centavos >= 0),
    balance_centavos INTEGER NOT NULL,
    release_bps INTEGER CHECK (release_bps IS NULL OR release_bps >= 0),
    source_url TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    source_note TEXT NOT NULL,
    CHECK (adjusted_program_centavos - release_centavos = balance_centavos),
    CHECK (
        (level IN ('attached_agency', 'subunit') AND parent_id IS NOT NULL)
        OR (level IN ('department', 'special_purpose_fund') AND parent_id IS NULL)
    )
);

CREATE INDEX allotment_release_level ON allotment_release_items (
    level, release_centavos DESC, record_id
);
CREATE INDEX allotment_release_balance ON allotment_release_items (
    balance_centavos DESC, record_id
);
CREATE INDEX allotment_release_rate ON allotment_release_items (
    release_bps ASC, record_id
);
CREATE INDEX allotment_release_name ON allotment_release_items (name, record_id);
