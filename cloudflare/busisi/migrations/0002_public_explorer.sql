CREATE TABLE public_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE budget_items (
    record_id TEXT PRIMARY KEY,
    budget_line_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount_centavos INTEGER NOT NULL,
    project_family_id TEXT NOT NULL,
    family_label TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL
);

CREATE INDEX budget_items_year ON budget_items (fiscal_year);
CREATE INDEX budget_items_amount ON budget_items (amount_centavos DESC, record_id);

CREATE TABLE delivery_items (
    contract_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    description TEXT NOT NULL,
    budget_centavos INTEGER NOT NULL,
    location TEXT NOT NULL,
    source_of_funds TEXT NOT NULL,
    project_family_id TEXT NOT NULL,
    family_label TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL
);

CREATE INDEX delivery_items_year ON delivery_items (fiscal_year);
CREATE INDEX delivery_items_budget ON delivery_items (budget_centavos DESC, contract_id);

CREATE TABLE candidate_links (
    candidate_id TEXT PRIMARY KEY,
    fiscal_year INTEGER NOT NULL,
    budget_line_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    confidence TEXT NOT NULL,
    score INTEGER NOT NULL,
    signals_json TEXT NOT NULL,
    budget_description TEXT NOT NULL,
    delivery_description TEXT NOT NULL,
    budget_amount_centavos INTEGER NOT NULL,
    delivery_budget_centavos INTEGER NOT NULL,
    difference_centavos INTEGER NOT NULL,
    budget_evidence_url TEXT NOT NULL,
    delivery_evidence_url TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN ('candidate', 'reviewed', 'quarantine'))
);

CREATE INDEX candidate_links_year ON candidate_links (fiscal_year);
CREATE INDEX candidate_links_score ON candidate_links (score DESC, candidate_id);
CREATE INDEX candidate_links_difference ON candidate_links (difference_centavos DESC, candidate_id);
CREATE INDEX candidate_links_zero_budget ON candidate_links (delivery_budget_centavos, candidate_id);
