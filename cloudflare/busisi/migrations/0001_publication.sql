CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE projects (
    slug TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    location TEXT NOT NULL,
    appropriation_centavos INTEGER NOT NULL,
    contract_budget_centavos INTEGER NOT NULL,
    variance_centavos INTEGER NOT NULL,
    contract_id TEXT NOT NULL,
    delivery_title TEXT NOT NULL,
    implementing_office TEXT NOT NULL,
    source_of_funds TEXT NOT NULL,
    confidence TEXT NOT NULL,
    confidence_score INTEGER NOT NULL,
    match_signals_json TEXT NOT NULL,
    match_limitations TEXT NOT NULL,
    evidence_urls_json TEXT NOT NULL,
    family_id TEXT NOT NULL,
    family_label TEXT NOT NULL,
    status_label TEXT NOT NULL,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('reviewed', 'quarantine')),
    is_confirmed_link INTEGER NOT NULL CHECK (is_confirmed_link IN (0, 1))
);

CREATE INDEX projects_year ON projects (fiscal_year);
CREATE INDEX projects_status ON projects (publication_status);
CREATE INDEX projects_appropriation ON projects (appropriation_centavos DESC, slug);
CREATE INDEX projects_variance ON projects (variance_centavos DESC, slug);

CREATE VIRTUAL TABLE project_search USING fts5(
    slug UNINDEXED,
    title,
    location,
    contract_id,
    delivery_title,
    implementing_office,
    tokenize='unicode61 remove_diacritics 2'
);
