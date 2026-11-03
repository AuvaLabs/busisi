ALTER TABLE contractor_rankings ADD COLUMN joint_project_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE contractor_rankings ADD COLUMN pcab_status TEXT NOT NULL DEFAULT 'not_checked';
ALTER TABLE contractor_rankings ADD COLUMN pcab_name TEXT NOT NULL DEFAULT '';
ALTER TABLE contractor_rankings ADD COLUMN pcab_category TEXT NOT NULL DEFAULT '';
ALTER TABLE contractor_rankings ADD COLUMN pcab_valid_to TEXT NOT NULL DEFAULT '';
ALTER TABLE contractor_rankings ADD COLUMN pcab_gov_infra INTEGER NOT NULL DEFAULT -1;
ALTER TABLE contractor_rankings ADD COLUMN pcab_snapshot_sha256 TEXT NOT NULL DEFAULT '';

CREATE INDEX contractor_pcab_status
ON contractor_rankings (pcab_status, project_count DESC, contractor_key);

CREATE TABLE contractor_concentrations (
    dimension TEXT NOT NULL CHECK (dimension IN ('region', 'province', 'category')),
    group_label TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    project_count INTEGER NOT NULL CHECK (project_count > 0),
    named_project_count INTEGER NOT NULL CHECK (named_project_count >= 0),
    party_association_count INTEGER NOT NULL CHECK (party_association_count > 0),
    contractor_count INTEGER NOT NULL CHECK (contractor_count > 0),
    top_contractor_key TEXT NOT NULL,
    top_contractor_name TEXT NOT NULL,
    top_pcab_id TEXT NOT NULL,
    top_project_count INTEGER NOT NULL CHECK (top_project_count > 0),
    top_share_basis_points INTEGER NOT NULL CHECK (
        top_share_basis_points BETWEEN 0 AND 10000
    ),
    top_associated_budget_centavos INTEGER NOT NULL CHECK (
        top_associated_budget_centavos >= 0
    ),
    PRIMARY KEY (dimension, group_label, fiscal_year)
);

CREATE INDEX contractor_concentration_share
ON contractor_concentrations (
    dimension, fiscal_year, top_share_basis_points DESC, party_association_count DESC
);
