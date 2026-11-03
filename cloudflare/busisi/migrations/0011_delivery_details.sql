CREATE TABLE delivery_project_details (
    contract_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    progress TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    contractor_parties_json TEXT NOT NULL CHECK (json_valid(contractor_parties_json)),
    start_date TEXT NOT NULL,
    completion_date TEXT NOT NULL,
    province TEXT NOT NULL,
    region TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    has_satellite_image INTEGER NOT NULL CHECK (has_satellite_image IN (0, 1)),
    source_artifact_sha256 TEXT NOT NULL
);

CREATE INDEX delivery_details_year
ON delivery_project_details (fiscal_year, contract_id);

CREATE INDEX delivery_details_status
ON delivery_project_details (status, progress, contract_id);
