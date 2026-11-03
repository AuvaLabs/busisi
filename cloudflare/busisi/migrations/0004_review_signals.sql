ALTER TABLE stage_change_items
ADD COLUMN family_label TEXT NOT NULL DEFAULT '';

CREATE INDEX stage_changes_family
ON stage_change_items (family_label, dataset, record_id);

CREATE INDEX budget_items_family
ON budget_items (family_label, fiscal_year, record_id);
