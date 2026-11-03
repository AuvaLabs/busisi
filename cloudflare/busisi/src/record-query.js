import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';
import { getProject } from './query.js';

const rows = (result) => result.results || [];

const safeJson = (value, fallback = []) => {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
};

const withDistrict = (row) => row && ({
  ...row,
  district_context: districtContext(row),
  district_classification: undefined,
  district_office_name: undefined,
  districts_json: undefined,
});

const candidateRecord = (row) => row && ({
  ...row,
  signals: safeJson(row.signals_json),
  signals_json: undefined,
});

const contractorRecord = (row) => row && ({
  ...row,
  pcab_url: 'https://www.pcab.construction.gov.ph/verify/',
});

const budgetById = (database, recordId) => database
  .prepare('SELECT * FROM budget_items WHERE record_id = ?')
  .bind(recordId)
  .first();

const deliveryById = (database, contractId) => database.prepare(`
  SELECT d.*, ${DISTRICT_SELECT}
  FROM delivery_items d
  ${districtOfficeJoin("CASE WHEN INSTR(d.location, ',') > 0 THEN SUBSTR(d.location, 1, INSTR(d.location, ',') - 1) ELSE d.location END")}
  WHERE d.contract_id = ?
`).bind(contractId).first();

const contractorForIdentity = (database, pcabId, name) => database.prepare(`
  SELECT * FROM contractor_rankings
  WHERE (? <> '' AND pcab_id = ?) OR LOWER(contractor_name) = LOWER(?)
  ORDER BY CASE WHEN pcab_id = ? THEN 0 ELSE 1 END, project_count DESC
  LIMIT 1
`).bind(pcabId || '', pcabId || '', name || '', pcabId || '').first();

export const getBudgetRecord = async (database, recordId) => {
  const record = await budgetById(database, recordId);
  if (!record) return null;
  const [related, candidates, projects] = await Promise.all([
    database.prepare(`
      SELECT record_id, fiscal_year, description, amount_centavos
      FROM budget_items WHERE project_family_id = ? AND record_id <> ?
      ORDER BY fiscal_year DESC, amount_centavos DESC LIMIT 20
    `).bind(record.project_family_id, recordId).all(),
    database.prepare(`
      SELECT * FROM candidate_links WHERE budget_line_id = ? AND fiscal_year = ?
      ORDER BY score DESC, candidate_id ASC LIMIT 20
    `).bind(record.budget_line_id, record.fiscal_year).all(),
    database.prepare(`
      SELECT slug, title, fiscal_year, contract_id, status_label, is_confirmed_link
      FROM projects WHERE family_id = ? ORDER BY fiscal_year DESC, slug ASC
    `).bind(record.project_family_id).all(),
  ]);
  return {
    record,
    related: rows(related),
    candidates: rows(candidates).map(candidateRecord),
    projects: rows(projects),
  };
};

export const getDeliveryRecord = async (database, contractId) => {
  const record = withDistrict(await deliveryById(database, contractId));
  if (!record) return null;
  const [related, budgets, candidates, projects, signals] = await Promise.all([
    database.prepare(`
      SELECT contract_id, fiscal_year, description, budget_centavos, location
      FROM delivery_items WHERE project_family_id = ? AND contract_id <> ?
      ORDER BY fiscal_year DESC, budget_centavos DESC LIMIT 20
    `).bind(record.project_family_id, contractId).all(),
    database.prepare(`
      SELECT record_id, fiscal_year, description, amount_centavos
      FROM budget_items WHERE project_family_id = ?
      ORDER BY fiscal_year DESC, amount_centavos DESC LIMIT 20
    `).bind(record.project_family_id).all(),
    database.prepare('SELECT * FROM candidate_links WHERE contract_id = ? ORDER BY score DESC LIMIT 20')
      .bind(contractId).all(),
    database.prepare(`
      SELECT slug, title, fiscal_year, status_label, is_confirmed_link
      FROM projects WHERE contract_id = ? ORDER BY slug ASC
    `).bind(contractId).all(),
    database.prepare(`
      SELECT * FROM integrity_signal_items WHERE contract_id = ?
      ORDER BY classification ASC, code ASC
    `).bind(contractId).all(),
  ]);
  const signalRows = rows(signals);
  const identity = signalRows[0] || {};
  const contractor = contractorRecord(await contractorForIdentity(
    database,
    identity.pcab_id,
    identity.contractor_name,
  ));
  return {
    record,
    related: rows(related),
    budgets: rows(budgets),
    candidates: rows(candidates).map(candidateRecord),
    projects: rows(projects),
    signals: signalRows,
    contractor,
  };
};

export const getCandidateRecord = async (database, candidateId) => {
  const row = await database.prepare('SELECT * FROM candidate_links WHERE candidate_id = ?')
    .bind(candidateId).first();
  if (!row) return null;
  const record = candidateRecord(row);
  const [budgets, delivery, projects] = await Promise.all([
    database.prepare(`
      SELECT * FROM budget_items WHERE budget_line_id = ? AND fiscal_year = ?
      ORDER BY amount_centavos DESC, record_id ASC
    `).bind(record.budget_line_id, record.fiscal_year).all(),
    deliveryById(database, record.contract_id),
    database.prepare(`
      SELECT slug, title, status_label, is_confirmed_link FROM projects
      WHERE contract_id = ? ORDER BY slug ASC
    `).bind(record.contract_id).all(),
  ]);
  return { record, budgets: rows(budgets), delivery: withDistrict(delivery), projects: rows(projects) };
};

export const getChangeRecord = async (database, recordId) => {
  const record = withDistrict(await database.prepare(`
    SELECT c.*, ${DISTRICT_SELECT}
    FROM stage_change_items c ${districtOfficeJoin('c.office')}
    WHERE c.record_id = ?
  `).bind(recordId).first());
  if (!record) return null;
  const [related, prior] = await Promise.all([
    database.prepare(`
      SELECT record_id, title, dataset, change_type, nep_centavos, house_centavos,
        difference_centavos, review_status
      FROM stage_change_items WHERE family_label = ? AND record_id <> ?
      ORDER BY ABS(difference_centavos) DESC, record_id ASC LIMIT 20
    `).bind(record.family_label, recordId).all(),
    database.prepare(`
      SELECT record_id, fiscal_year, description, amount_centavos
      FROM budget_items WHERE family_label = ? ORDER BY fiscal_year DESC, amount_centavos DESC LIMIT 20
    `).bind(record.family_label).all(),
  ]);
  return { record, related: rows(related), prior: rows(prior) };
};

export const getIntegrityRecord = async (database, signalId) => {
  const record = withDistrict(await database.prepare(`
    SELECT i.*, ${DISTRICT_SELECT}
    FROM integrity_signal_items i ${districtOfficeJoin('i.province')}
    WHERE i.signal_id = ?
  `).bind(signalId).first());
  if (!record) return null;
  const [delivery, contractor, related] = await Promise.all([
    deliveryById(database, record.contract_id),
    contractorForIdentity(database, record.pcab_id, record.contractor_name),
    database.prepare(`
      SELECT signal_id, code, label, classification FROM integrity_signal_items
      WHERE contract_id = ? AND signal_id <> ? ORDER BY classification ASC, code ASC
    `).bind(record.contract_id, signalId).all(),
  ]);
  return {
    record,
    delivery: withDistrict(delivery),
    contractor: contractorRecord(contractor),
    related: rows(related),
  };
};

export const getContractorRecord = async (database, contractorKey) => {
  const record = contractorRecord(await database.prepare(
    'SELECT * FROM contractor_rankings WHERE contractor_key = ?',
  ).bind(contractorKey).first());
  if (!record) return null;
  const [signals, concentrations] = await Promise.all([
    database.prepare(`
      SELECT signal_id, contract_id, fiscal_year, code, classification, label, description,
        budget_centavos, status, progress, province, region
      FROM integrity_signal_items
      WHERE (? <> '' AND pcab_id = ?) OR LOWER(contractor_name) = LOWER(?)
      ORDER BY fiscal_year DESC, budget_centavos DESC, signal_id ASC LIMIT 100
    `).bind(record.pcab_id, record.pcab_id, record.contractor_name).all(),
    database.prepare(`
      SELECT * FROM contractor_concentrations WHERE top_contractor_key = ?
      ORDER BY fiscal_year DESC, top_share_basis_points DESC LIMIT 50
    `).bind(contractorKey).all(),
  ]);
  return { record, signals: rows(signals), concentrations: rows(concentrations) };
};

export const getEnhancedProject = async (database, slug) => {
  const record = await getProject(database, slug);
  if (!record) return null;
  const [delivery, signals, related, budgets, deliveries] = await Promise.all([
    deliveryById(database, record.contract_id),
    database.prepare('SELECT * FROM integrity_signal_items WHERE contract_id = ? ORDER BY code ASC')
      .bind(record.contract_id).all(),
    database.prepare(`
      SELECT slug, title, fiscal_year, contract_id, status_label, is_confirmed_link
      FROM projects WHERE family_id = ? AND slug <> ? ORDER BY fiscal_year ASC, slug ASC
    `).bind(record.family_id, slug).all(),
    database.prepare(`
      SELECT record_id, fiscal_year, description, amount_centavos FROM budget_items
      WHERE project_family_id = ? ORDER BY fiscal_year DESC, amount_centavos DESC LIMIT 20
    `).bind(record.family_id).all(),
    database.prepare(`
      SELECT contract_id, fiscal_year, description, budget_centavos, location FROM delivery_items
      WHERE project_family_id = ? ORDER BY fiscal_year DESC, budget_centavos DESC LIMIT 20
    `).bind(record.family_id).all(),
  ]);
  const signalRows = rows(signals);
  const identity = signalRows[0] || {};
  const contractor = contractorRecord(await contractorForIdentity(
    database,
    identity.pcab_id,
    identity.contractor_name,
  ));
  return {
    record,
    delivery: withDistrict(delivery),
    signals: signalRows,
    related: rows(related),
    budgets: rows(budgets),
    deliveries: rows(deliveries),
    contractor,
  };
};
