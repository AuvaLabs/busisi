CREATE TABLE coverage_releases (
  release_id TEXT PRIMARY KEY CHECK (length(release_id) = 64),
  released_at TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
  universe_contracts INTEGER NOT NULL CHECK (universe_contracts >= 0),
  completed_contracts INTEGER NOT NULL CHECK (completed_contracts >= 0),
  verified_exact_contracts INTEGER NOT NULL CHECK (verified_exact_contracts >= 0),
  no_image_contracts INTEGER NOT NULL CHECK (no_image_contracts >= 0),
  conflict_contracts INTEGER NOT NULL CHECK (conflict_contracts >= 0),
  retry_contracts INTEGER NOT NULL CHECK (retry_contracts >= 0),
  blocked_contracts INTEGER NOT NULL CHECK (blocked_contracts >= 0),
  pending_contracts INTEGER NOT NULL CHECK (pending_contracts >= 0),
  verified_images INTEGER NOT NULL CHECK (verified_images >= 0),
  quarantined_images INTEGER NOT NULL CHECK (quarantined_images >= 0),
  CHECK (completed_contracts = verified_exact_contracts + no_image_contracts + conflict_contracts),
  CHECK (universe_contracts = completed_contracts + retry_contracts + blocked_contracts + pending_contracts)
);

CREATE INDEX coverage_releases_latest_idx ON coverage_releases(released_at DESC, release_id);
