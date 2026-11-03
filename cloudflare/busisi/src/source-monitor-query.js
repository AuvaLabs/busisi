export const getSourceMonitorStatus = async (database) => {
  const record = await database.prepare(`
    SELECT checked_at, status, differences_json, limitations_json, observations_sha256
    FROM source_monitor_status WHERE singleton_id = 1
  `).first();
  if (!record) return null;
  return {
    ...record,
    differences: JSON.parse(record.differences_json),
    limitations: JSON.parse(record.limitations_json),
    differences_json: undefined,
    limitations_json: undefined,
  };
};
