import { DISTRICT_SELECT, districtContext, districtOfficeJoin } from './district-context.js';
import { getProject } from './query.js';
import { getProjectCoaEvidence } from './coa-query.js';
import { getProjectProcurementEvidence } from './procurement-query.js';
import { buildContractOutcome } from './contract-outcome.js';
import { getContractAwardMirror } from './outcome-query.js';
import { getProjectContractEvidence } from './contract-evidence-query.js';
import { getProjectImageEvidence } from './project-image-query.js';
import { getContractorAssociationSummary } from './contractor-activity-query.js';
import { getContractorAccountability } from './accountability-query.js';

const rows = (result) => result.results || [];

const safeJson = (value, fallback = []) => {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
};

const safeArray = (value) => {
  const parsed = safeJson(value);
  return Array.isArray(parsed) ? parsed : [];
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
  signals: safeArray(row.signals_json),
  signals_json: undefined,
});

const contractorRecord = (row) => row && ({
  ...row,
  pcab_url: 'https://www.pcab.construction.gov.ph/verify/',
});

const contractorParties = (record) => safeArray(record?.contractor_parties_json);

const contractorsForDelivery = async (database, record) => {
  const parties = contractorParties(record);
  const found = await Promise.all(parties.map((party) => database.prepare(
    'SELECT * FROM contractor_rankings WHERE contractor_key = ?',
  ).bind(party.contractor_key).first()));
  return parties.map((party) => ({
    ...party,
    profile: contractorRecord(found.find((item) => item?.contractor_key === party.contractor_key)),
  }));
};

const budgetById = (database, recordId) => database
  .prepare('SELECT * FROM budget_items WHERE record_id = ?')
  .bind(recordId)
  .first();

const deliveryById = (database, contractId) => database.prepare(`
  SELECT d.*, detail.category, detail.status, detail.progress, detail.contractor_name,
    detail.contractor_parties_json, detail.start_date, detail.completion_date,
    detail.province, detail.region, detail.latitude, detail.longitude,
    detail.has_satellite_image, detail.source_artifact_sha256 AS detail_artifact_sha256,
    ${DISTRICT_SELECT}
  FROM delivery_items d
  LEFT JOIN delivery_project_details detail ON detail.contract_id = d.contract_id
  ${districtOfficeJoin("CASE WHEN INSTR(d.location, ',') > 0 THEN SUBSTR(d.location, 1, INSTR(d.location, ',') - 1) ELSE d.location END")}
  WHERE d.contract_id = ?
`).bind(contractId).first();

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
  const [related, budgets, candidates, projects, signals, imageEvidence] = await Promise.all([
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
    getProjectImageEvidence(database, contractId),
  ]);
  const signalRows = rows(signals);
  const contractors = await contractorsForDelivery(database, record);
  return {
    record,
    related: rows(related),
    budgets: rows(budgets),
    candidates: rows(candidates).map(candidateRecord),
    projects: rows(projects),
    signals: signalRows,
    contractors,
    imageEvidence,
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
  const [delivery, related] = await Promise.all([
    deliveryById(database, record.contract_id),
    database.prepare(`
      SELECT signal_id, code, label, classification, description, evidence, limitations
      FROM integrity_signal_items
      WHERE contract_id = ? AND signal_id <> ? ORDER BY classification ASC, code ASC
    `).bind(record.contract_id, signalId).all(),
  ]);
  const contractors = await contractorsForDelivery(database, delivery);
  return {
    record,
    delivery: withDistrict(delivery),
    contractors,
    related: rows(related),
  };
};

export const getContractorRecord = async (database, contractorKey) => {
  const record = contractorRecord(await database.prepare(
    'SELECT * FROM contractor_rankings WHERE contractor_key = ?',
  ).bind(contractorKey).first());
  if (!record) return null;
  const [signals, concentrations, associationSummary, statuses, years, accountability] = await Promise.all([
    database.prepare(`
      SELECT signal.signal_id, signal.contract_id, signal.fiscal_year, signal.code,
        signal.classification, signal.label, signal.description, signal.budget_centavos,
        signal.status, signal.progress, signal.province, signal.region
      FROM integrity_signal_items signal
      JOIN contractor_project_associations association
        ON association.contract_id = signal.contract_id
      WHERE association.contractor_key = ?
      ORDER BY signal.fiscal_year DESC, signal.budget_centavos DESC, signal.signal_id ASC
      LIMIT 100
    `).bind(contractorKey).all(),
    database.prepare(`
      SELECT * FROM contractor_concentrations WHERE top_contractor_key = ?
      ORDER BY fiscal_year DESC, top_share_basis_points DESC LIMIT 50
    `).bind(contractorKey).all(),
    getContractorAssociationSummary(database, contractorKey),
    database.prepare(`
      SELECT detail.status, COUNT(*) AS count
      FROM contractor_project_associations association
      JOIN delivery_project_details detail ON detail.contract_id = association.contract_id
      WHERE association.contractor_key = ? AND detail.status <> ''
      GROUP BY detail.status ORDER BY count DESC, detail.status ASC
    `).bind(contractorKey).all(),
    database.prepare(`
      SELECT detail.fiscal_year, COUNT(*) AS count
      FROM contractor_project_associations association
      JOIN delivery_project_details detail ON detail.contract_id = association.contract_id
      WHERE association.contractor_key = ?
      GROUP BY detail.fiscal_year ORDER BY detail.fiscal_year DESC
    `).bind(contractorKey).all(),
    getContractorAccountability(database, contractorKey),
  ]);
  return {
    record,
    signals: rows(signals),
    concentrations: rows(concentrations),
    associationSummary,
    statuses: rows(statuses),
    years: rows(years),
    accountability,
  };
};

export const getEnhancedProject = async (database, slug) => {
  const record = await getProject(database, slug);
  if (!record) return null;
  const [delivery, signals, related, budgets, deliveries, candidates, changes, publicMeta, integrityMeta, auditEvidence, procurementEvidence, awardMirror, contractEvidence, imageEvidence] = await Promise.all([
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
    database.prepare(`
      SELECT candidate_id, score, confidence, review_status, budget_description,
        delivery_description, difference_centavos
      FROM candidate_links WHERE contract_id = ? ORDER BY score DESC LIMIT 20
    `).bind(record.contract_id).all(),
    database.prepare(`
      SELECT record_id, title, dataset, change_type, change_label, review_status,
        nep_centavos, house_centavos, difference_centavos
      FROM stage_change_items WHERE family_label = ?
      ORDER BY ABS(difference_centavos) DESC, record_id ASC LIMIT 20
    `).bind(record.family_label).all(),
    database.prepare(`
      SELECT key, value FROM public_metadata
      WHERE key IN ('budget_artifact_sha256', 'delivery_artifact_sha256')
    `).all(),
    database.prepare(`
      SELECT key, value FROM integrity_metadata
      WHERE key IN ('source_as_of', 'source_artifact_sha256', 'pcab_retrieved_on',
        'district_source_retrieved_on')
    `).all(),
    getProjectCoaEvidence(database, record.contract_id),
    getProjectProcurementEvidence(database, record.contract_id),
    getContractAwardMirror(database, record.contract_id),
    getProjectContractEvidence(database, record.contract_id),
    getProjectImageEvidence(database, record.contract_id),
  ]);
  const signalRows = rows(signals);
  const deliveryRecord = withDistrict(delivery);
  const contractors = await contractorsForDelivery(database, deliveryRecord);
  const contractOutcome = procurementEvidence?.records?.length ? buildContractOutcome({
    coverage: procurementEvidence.coverage,
    procurementRecords: procurementEvidence.records,
    delivery: deliveryRecord,
    awardMirror,
  }) : null;
  return {
    record,
    delivery: deliveryRecord,
    signals: signalRows,
    related: rows(related),
    budgets: rows(budgets),
    deliveries: rows(deliveries),
    contractors,
    candidates: rows(candidates),
    changes: rows(changes),
    auditEvidence,
    procurementEvidence,
    contractEvidence,
    contractOutcome,
    imageEvidence,
    provenance: Object.fromEntries(
      [...rows(publicMeta), ...rows(integrityMeta)].map((item) => [item.key, item.value]),
    ),
  };
};
