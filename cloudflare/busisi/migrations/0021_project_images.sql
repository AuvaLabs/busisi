CREATE TABLE project_image_coverage (
  contract_id TEXT PRIMARY KEY,
  summary_count INTEGER NOT NULL CHECK (summary_count >= 0),
  endpoint_count INTEGER NOT NULL CHECK (endpoint_count >= 0),
  has_images INTEGER NOT NULL CHECK (has_images IN (0, 1)),
  state TEXT NOT NULL CHECK (state IN ('verified_exact', 'no_images', 'count_conflict', 'acquisition_failed')),
  detail_sha256 TEXT NOT NULL CHECK (length(detail_sha256) = 64),
  list_sha256 TEXT NOT NULL CHECK (length(list_sha256) = 64),
  retrieved_at TEXT NOT NULL,
  note TEXT NOT NULL
);

CREATE TABLE project_images (
  image_id TEXT PRIMARY KEY CHECK (length(image_id) = 64),
  contract_id TEXT NOT NULL REFERENCES project_image_coverage(contract_id),
  component_id TEXT NOT NULL,
  photo_number INTEGER NOT NULL CHECK (photo_number > 0),
  purpose TEXT NOT NULL,
  source_status TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  fiscal_year TEXT NOT NULL,
  latitude REAL,
  longitude REAL,
  coordinate_status TEXT NOT NULL CHECK (coordinate_status IN ('not_reported', 'incomplete', 'within_broad_philippine_bounds', 'outside_broad_philippine_bounds')),
  source_url TEXT NOT NULL,
  thumbnail_source_url TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL CHECK (length(artifact_sha256) = 64),
  content_type TEXT NOT NULL CHECK (content_type = 'image/jpeg'),
  byte_size INTEGER NOT NULL CHECK (byte_size > 0),
  width INTEGER NOT NULL CHECK (width > 0),
  height INTEGER NOT NULL CHECK (height > 0),
  archive_key TEXT NOT NULL UNIQUE,
  publication_status TEXT NOT NULL CHECK (publication_status IN ('verified', 'quarantine')),
  UNIQUE (contract_id, source_url)
);

CREATE INDEX project_images_contract_status_idx
  ON project_images(contract_id, publication_status, photo_number, image_id);
