CREATE TABLE project_classification_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE project_classification_tags (
    contract_id TEXT NOT NULL,
    dimension TEXT NOT NULL CHECK (
        dimension IN ('project_type', 'purpose', 'work_type', 'funding_program')
    ),
    tag TEXT NOT NULL,
    label TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (
        evidence_kind IN ('source_category', 'project_title', 'source_category_and_title')
    ),
    rule_id TEXT NOT NULL,
    rule_version INTEGER NOT NULL CHECK (rule_version > 0),
    PRIMARY KEY (contract_id, dimension, tag)
);

CREATE INDEX project_classification_dimension_tag
ON project_classification_tags (dimension, tag, contract_id);

CREATE INDEX project_classification_contract
ON project_classification_tags (contract_id, dimension, tag);
