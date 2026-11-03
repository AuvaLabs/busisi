CREATE INDEX contract_award_match_awardee
ON contract_award_matches (awardee_name, contract_id);

CREATE INDEX delivery_detail_category
ON delivery_project_details (category, contract_id);

CREATE INDEX delivery_detail_region
ON delivery_project_details (region, contract_id);

CREATE INDEX delivery_detail_contractor
ON delivery_project_details (contractor_name, contract_id);

CREATE INDEX integrity_signal_contract
ON integrity_signal_items (contract_id, code);
