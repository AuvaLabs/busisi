CREATE TABLE contractor_project_associations (
    contractor_key TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    party_position INTEGER NOT NULL CHECK (party_position > 0),
    party_count INTEGER NOT NULL CHECK (party_count > 0 AND party_position <= party_count),
    relationship TEXT NOT NULL CHECK (relationship IN ('sole', 'joint')),
    PRIMARY KEY (contractor_key, contract_id),
    FOREIGN KEY (contractor_key) REFERENCES contractor_rankings (contractor_key),
    FOREIGN KEY (contract_id) REFERENCES delivery_project_details (contract_id)
);

CREATE INDEX contractor_association_contract
ON contractor_project_associations (contract_id, contractor_key);

CREATE INDEX contractor_association_relationship
ON contractor_project_associations (contractor_key, relationship, contract_id);

INSERT INTO contractor_project_associations (
    contractor_key, contract_id, party_position, party_count, relationship
)
SELECT
    json_extract(party.value, '$.contractor_key'),
    detail.contract_id,
    CAST(party.key AS INTEGER) + 1,
    json_array_length(detail.contractor_parties_json),
    CASE
        WHEN json_array_length(detail.contractor_parties_json) > 1 THEN 'joint'
        ELSE 'sole'
    END
FROM delivery_project_details detail, json_each(detail.contractor_parties_json) party
WHERE json_type(party.value, '$.contractor_key') = 'text'
  AND json_extract(party.value, '$.contractor_key') <> '';
