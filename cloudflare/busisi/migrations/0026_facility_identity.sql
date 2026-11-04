CREATE TABLE facility_registry_sources (
    source_id TEXT PRIMARY KEY,
    publisher TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256) = 64),
    acquired_at TEXT NOT NULL,
    scope_note TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'partial', 'superseded'))
);

CREATE TABLE facility_identities (
    facility_id TEXT PRIMARY KEY,
    facility_type TEXT NOT NULL CHECK (facility_type IN ('school', 'hospital', 'health_center')),
    official_id TEXT NOT NULL,
    official_name TEXT NOT NULL,
    municipality TEXT NOT NULL,
    province TEXT NOT NULL,
    region TEXT NOT NULL,
    latitude_e6 INTEGER,
    longitude_e6 INTEGER,
    source_id TEXT NOT NULL REFERENCES facility_registry_sources(source_id),
    UNIQUE (source_id, official_id)
);

CREATE INDEX facility_identities_name ON facility_identities (facility_type, official_name);
CREATE INDEX facility_identities_place ON facility_identities (province, municipality, official_name);

CREATE TABLE facility_record_links (
    source_type TEXT NOT NULL CHECK (source_type IN ('budget', 'delivery')),
    record_id TEXT NOT NULL,
    match_state TEXT NOT NULL CHECK (
        match_state IN ('official_exact', 'group_only', 'ambiguous', 'unlinked')
    ),
    facility_id TEXT REFERENCES facility_identities(facility_id),
    record_group_key TEXT,
    record_group_label TEXT NOT NULL,
    match_method TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
    signals_json TEXT NOT NULL CHECK (json_valid(signals_json)),
    limitation TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    PRIMARY KEY (source_type, record_id),
    CHECK (match_state <> 'official_exact' OR facility_id IS NOT NULL),
    CHECK (match_state <> 'group_only' OR record_group_key IS NOT NULL)
);

CREATE INDEX facility_record_links_state ON facility_record_links (match_state, source_type, record_id);
CREATE INDEX facility_record_links_identity ON facility_record_links (facility_id, source_type, record_id);
CREATE INDEX facility_record_links_group ON facility_record_links (record_group_key, source_type, record_id);
