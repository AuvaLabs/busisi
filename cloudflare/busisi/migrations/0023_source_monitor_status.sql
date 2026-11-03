CREATE TABLE source_monitor_status (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  checked_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'unchanged', 'drift_detected', 'acquisition_or_validation_failure'
  )),
  differences_json TEXT NOT NULL CHECK (json_valid(differences_json)),
  limitations_json TEXT NOT NULL CHECK (json_valid(limitations_json)),
  observations_sha256 TEXT NOT NULL CHECK (length(observations_sha256) = 64)
);
