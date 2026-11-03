CREATE TABLE public_value_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE public_value_indicators (
    indicator_id TEXT PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('economy', 'fiscal_space', 'composition', 'context')),
    label TEXT NOT NULL,
    unit TEXT NOT NULL CHECK (unit IN ('centavos', 'basis_points', 'people', 'range_basis_points')),
    value_2026 INTEGER NOT NULL CHECK (value_2026 >= 0),
    value_2027 INTEGER NOT NULL CHECK (value_2027 >= 0),
    lower_2026 INTEGER,
    upper_2026 INTEGER,
    lower_2027 INTEGER,
    upper_2027 INTEGER,
    change_value INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('improving', 'pressure', 'context')),
    direction_rule TEXT NOT NULL,
    source_document TEXT NOT NULL CHECK (source_document IN ('besf-a1', 'besf-a2')),
    source_page INTEGER NOT NULL CHECK (source_page IN (1, 2)),
    source_url TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256) = 64),
    source_note TEXT NOT NULL,
    CHECK (
        (unit = 'range_basis_points' AND lower_2026 IS NOT NULL AND upper_2026 IS NOT NULL AND lower_2027 IS NOT NULL AND upper_2027 IS NOT NULL)
        OR
        (unit != 'range_basis_points' AND lower_2026 IS NULL AND upper_2026 IS NULL AND lower_2027 IS NULL AND upper_2027 IS NULL)
    )
);

CREATE INDEX public_value_direction ON public_value_indicators (direction, category, indicator_id);
CREATE INDEX public_value_category ON public_value_indicators (category, indicator_id);
