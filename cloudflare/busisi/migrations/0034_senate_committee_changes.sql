CREATE TABLE senate_committee_releases (
    release_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    report_number TEXT NOT NULL,
    related_bill TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('awaiting_official_document', 'verified_changes')),
    checked_at TEXT NOT NULL,
    source_url TEXT,
    publication_date TEXT,
    artifact_sha256 TEXT CHECK (artifact_sha256 IS NULL OR length(artifact_sha256) = 64),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size > 0),
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    total_previous_centavos INTEGER,
    total_senate_centavos INTEGER,
    total_change_centavos INTEGER,
    public_note TEXT NOT NULL,
    CHECK (
        (state = 'awaiting_official_document' AND source_url IS NULL
            AND publication_date IS NULL AND artifact_sha256 IS NULL AND byte_size IS NULL
            AND item_count = 0 AND total_previous_centavos IS NULL
            AND total_senate_centavos IS NULL AND total_change_centavos IS NULL)
        OR
        (state = 'verified_changes' AND source_url IS NOT NULL
            AND publication_date IS NOT NULL AND artifact_sha256 IS NOT NULL AND byte_size IS NOT NULL
            AND item_count > 0 AND total_previous_centavos IS NOT NULL
            AND total_senate_centavos IS NOT NULL AND total_change_centavos IS NOT NULL)
    )
);

CREATE TABLE senate_committee_controls (
    release_id TEXT NOT NULL REFERENCES senate_committee_releases(release_id),
    group_code TEXT NOT NULL,
    label TEXT NOT NULL,
    project_count INTEGER NOT NULL CHECK (project_count >= 0),
    previous_centavos INTEGER NOT NULL,
    senate_centavos INTEGER NOT NULL,
    change_centavos INTEGER NOT NULL,
    PRIMARY KEY (release_id, group_code),
    CHECK (change_centavos = senate_centavos - previous_centavos)
);

CREATE TABLE senate_committee_changes (
    change_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL REFERENCES senate_committee_releases(release_id),
    group_code TEXT NOT NULL,
    origin_stage TEXT NOT NULL CHECK (origin_stage IN ('nep', 'house_gab')),
    source_project_id TEXT,
    title TEXT NOT NULL,
    project_type TEXT,
    region TEXT,
    province TEXT,
    city_or_municipality TEXT,
    district TEXT,
    previous_centavos INTEGER NOT NULL,
    senate_centavos INTEGER NOT NULL,
    change_centavos INTEGER NOT NULL,
    reason TEXT NOT NULL,
    source_page INTEGER NOT NULL CHECK (source_page > 0),
    match_state TEXT NOT NULL CHECK (match_state IN ('exact', 'unmatched')),
    linked_project_slug TEXT,
    public_note TEXT NOT NULL,
    FOREIGN KEY (release_id, group_code)
        REFERENCES senate_committee_controls(release_id, group_code),
    CHECK (change_centavos = senate_centavos - previous_centavos),
    CHECK (
        (match_state = 'exact' AND linked_project_slug IS NOT NULL)
        OR (match_state = 'unmatched' AND linked_project_slug IS NULL)
    )
);

CREATE INDEX senate_committee_change_group
    ON senate_committee_changes (release_id, group_code, change_centavos, change_id);
CREATE INDEX senate_committee_change_place
    ON senate_committee_changes (region, province, city_or_municipality, district, change_id);
