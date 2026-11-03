DROP INDEX contract_award_mirror_year;

CREATE TABLE contract_award_mirror_records_v2 (
    source_row_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL UNIQUE,
    fiscal_year INTEGER NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    reference_id TEXT NOT NULL,
    award_title TEXT NOT NULL,
    notice_title TEXT NOT NULL,
    awardee_name TEXT NOT NULL,
    organization_name TEXT NOT NULL,
    area_of_delivery TEXT NOT NULL,
    business_category TEXT NOT NULL,
    contract_amount_centavos INTEGER NOT NULL CHECK (contract_amount_centavos >= 0),
    award_date TEXT NOT NULL,
    award_status TEXT NOT NULL,
    row_sha256 TEXT NOT NULL CHECK (length(row_sha256) = 64),
    source_title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    dataset_url TEXT NOT NULL,
    file_url TEXT NOT NULL,
    dataset_file TEXT NOT NULL,
    source_revision TEXT NOT NULL CHECK (length(source_revision) = 40),
    source_last_modified TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_license TEXT NOT NULL,
    acquisition_status TEXT NOT NULL CHECK (
        acquisition_status IN (
            'row_extract_source_file_unarchived',
            'source_file_archived_secondary'
        )
    ),
    evidence_note TEXT NOT NULL
);

INSERT INTO contract_award_mirror_records_v2
SELECT * FROM contract_award_mirror_records;

DROP TABLE contract_award_mirror_records;
ALTER TABLE contract_award_mirror_records_v2 RENAME TO contract_award_mirror_records;

CREATE INDEX contract_award_mirror_year
ON contract_award_mirror_records (fiscal_year, contract_id);
