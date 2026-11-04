INSERT OR REPLACE INTO integrity_metadata (key, value)
VALUES (
    'contractor_associations',
    CAST((SELECT COUNT(*) FROM contractor_project_associations) AS TEXT)
);

INSERT OR REPLACE INTO integrity_metadata (key, value)
VALUES ('schema_version', '4');
