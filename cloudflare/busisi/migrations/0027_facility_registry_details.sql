CREATE TABLE facility_identity_details (
    facility_id TEXT PRIMARY KEY REFERENCES facility_identities(facility_id),
    division TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    demolition_required INTEGER NOT NULL CHECK (demolition_required IN (0, 1)),
    geotechnical_report INTEGER NOT NULL CHECK (geotechnical_report IN (0, 1)),
    site_development_plan INTEGER NOT NULL CHECK (site_development_plan IN (0, 1)),
    ownership_documents INTEGER NOT NULL CHECK (ownership_documents IN (0, 1))
);

CREATE INDEX facility_identity_details_division ON facility_identity_details (division, facility_id);
