CREATE TABLE acquisition_universe_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE acquisition_universe_breakdowns (
    dimension TEXT NOT NULL CHECK (dimension IN ('fiscal_year', 'category', 'match_state')),
    value TEXT NOT NULL,
    total_contracts INTEGER NOT NULL CHECK (total_contracts >= 0),
    structured_exact INTEGER NOT NULL CHECK (structured_exact >= 0),
    title_exact INTEGER NOT NULL CHECK (title_exact >= 0),
    multiple_exact_rows INTEGER NOT NULL CHECK (multiple_exact_rows >= 0),
    conflict_review INTEGER NOT NULL CHECK (conflict_review >= 0),
    no_exact_row INTEGER NOT NULL CHECK (no_exact_row >= 0),
    invalid_identifier INTEGER NOT NULL CHECK (invalid_identifier >= 0),
    PRIMARY KEY (dimension, value),
    CHECK (
        total_contracts = structured_exact + title_exact + multiple_exact_rows
        + conflict_review + no_exact_row + invalid_identifier
    )
);

CREATE INDEX acquisition_universe_breakdown_dimension
ON acquisition_universe_breakdowns (dimension, total_contracts DESC, value);
