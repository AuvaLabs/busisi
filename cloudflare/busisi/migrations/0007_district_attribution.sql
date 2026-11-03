CREATE TABLE district_office_attributions (
    office_key TEXT PRIMARY KEY,
    office_name TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (
        classification IN ('single_district', 'shared_office')
    ),
    district_count INTEGER NOT NULL CHECK (district_count > 0),
    districts_json TEXT NOT NULL CHECK (json_valid(districts_json)),
    source_commit TEXT NOT NULL,
    source_built_at TEXT NOT NULL,
    source_retrieved_on TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL
);

CREATE INDEX district_office_name
ON district_office_attributions (office_name, office_key);
