CREATE TABLE integrity_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE integrity_signal_items (
    signal_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    code TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (
        classification IN ('source_conflict', 'amount_review', 'identity_review', 'coverage_gap')
    ),
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    pcab_id TEXT NOT NULL,
    budget_centavos INTEGER NOT NULL,
    status TEXT NOT NULL,
    progress TEXT NOT NULL,
    province TEXT NOT NULL,
    region TEXT NOT NULL,
    latitude TEXT NOT NULL,
    longitude TEXT NOT NULL,
    evidence TEXT NOT NULL,
    limitations TEXT NOT NULL,
    source_artifact_sha256 TEXT NOT NULL
);

CREATE INDEX integrity_signal_code
ON integrity_signal_items (code, budget_centavos DESC, signal_id);

CREATE INDEX integrity_signal_classification
ON integrity_signal_items (classification, budget_centavos DESC, signal_id);

CREATE INDEX integrity_signal_year
ON integrity_signal_items (fiscal_year, budget_centavos DESC, signal_id);

CREATE INDEX integrity_signal_contractor
ON integrity_signal_items (contractor_name, signal_id);

CREATE TABLE contractor_rankings (
    contractor_key TEXT PRIMARY KEY,
    contractor_name TEXT NOT NULL,
    pcab_id TEXT NOT NULL,
    project_count INTEGER NOT NULL CHECK (project_count > 0),
    total_budget_centavos INTEGER NOT NULL CHECK (total_budget_centavos >= 0),
    completed_count INTEGER NOT NULL CHECK (completed_count >= 0),
    ongoing_count INTEGER NOT NULL CHECK (ongoing_count >= 0),
    terminated_count INTEGER NOT NULL CHECK (terminated_count >= 0),
    first_year INTEGER NOT NULL,
    last_year INTEGER NOT NULL
);

CREATE INDEX contractor_project_count
ON contractor_rankings (project_count DESC, total_budget_centavos DESC, contractor_key);

CREATE INDEX contractor_budget
ON contractor_rankings (total_budget_centavos DESC, project_count DESC, contractor_key);

CREATE INDEX contractor_name
ON contractor_rankings (contractor_name, contractor_key);
