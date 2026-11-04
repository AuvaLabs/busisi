import { getAcquisitionCoverage } from './acquisition-coverage-query.js';
import { getAgencyBudgetSummary } from './agency-budget-query.js';
import { getAllotmentReleaseSummary } from './allotment-release-query.js';
import { getBudgetCycleSummary } from './budget-cycle-query.js';
import { getChangeStats } from './change-query.js';
import { getCoaSummary } from './coa-query.js';
import { getContractIntelligenceSummary } from './contract-intelligence-query.js';
import { getCoverageStatus } from './coverage-status-query.js';
import { getIntegritySummary } from './integrity-query.js';
import { getProcurementSummary } from './procurement-query.js';
import { getPublicValueSummary } from './public-value-query.js';
import { getPublicServicesSummary } from './public-services-query.js';
import { getReviewSummary } from './review-query.js';
import { getSourceMonitorStatus } from './source-monitor-query.js';
import { getAccountabilitySummary } from './accountability-query.js';

const STATE_LABELS = Object.freeze({
  answerable: 'Busisi can answer this',
  partially_answerable: 'Busisi can answer part of this',
  not_supported: 'Busisi cannot answer this yet',
});

const count = (value) => Number(value || 0);
const integer = (value) => count(value).toLocaleString('en-PH');
const item = (record) => Object.freeze({
  ...record,
  state_label: STATE_LABELS[record.state],
  scope_count: count(record.scope_count),
});

const changeQuestions = ({ change, review, agency }) => {
  const changes = Object.fromEntries(
    (review.changes || []).map((row) => [row.change_type, count(row.record_count)]),
  );
  const compared = count(change.record_count);
  const heads = count(agency.appropriation_heads);
  const congress = count(agency.congress_institutions);
  const fiscalYear = count(change.fiscal_year) || count(agency.fiscal_year) || 2027;
  return [
    item({
      id: 'fy2027-project-stage-changes', category: 'Budget', state: 'answerable',
      question: `Which project rows changed between the FY${fiscalYear} NEP and House bill?`,
      scope_label: `${integer(compared)} compared project rows`, scope_count: compared,
      as_of: `FY${fiscalYear}`, evidence_level: 'deterministic_comparison',
      answer_summary: `${integer(changes.house_only)} House-only, ${integer(changes.nep_only)} NEP-only, ${integer(changes.increased)} increased, ${integer(changes.decreased)} decreased, and ${integer(changes.unchanged)} unchanged rows are separately classified.`,
      answer_url: '/changes/', source_label: 'Acquired FY2027 NEP and House bill pages',
      limitation: 'The comparison covers four acquired programs and is not the final GAA or proof of an insertion.',
    }),
    item({
      id: 'appropriation-head-movements', category: 'Budget', state: 'answerable',
      question: 'Which national appropriation heads and Congress institutions gained or lost funding in the House bill?',
      scope_label: `${integer(heads)} appropriation heads and ${integer(congress)} Congress institutions`,
      scope_count: heads + congress, as_of: `FY${fiscalYear}`, evidence_level: 'reconciled_control_total',
      answer_summary: `${integer(count(agency.compared_records))} records have comparable NEP and House totals; ${integer(count(agency.unavailable_records))} is explicitly unavailable.`,
      answer_url: '/agencies/', source_label: 'DBM NEP and acquired House bill volumes',
      limitation: 'This is not a complete directory of every attached agency, program, or final enacted appropriation.',
    }),
  ];
};

const releaseQuestions = (release) => [item({
  id: 'dbm-allotment-releases', category: 'Releases', state: 'answerable',
  question: 'How much allotment had DBM officially released by department, attached agency, subunit, or Special Purpose Fund?',
  scope_label: `${integer(release.record_count)} official DBM release rows`,
  scope_count: release.record_count, as_of: release.as_of_date || null,
  evidence_level: 'official_source_reconciled',
  answer_summary: `${integer(release.department_count)} departments, ${integer(release.attached_agency_count)} attached-agency or subunit rows, and ${integer(release.special_purpose_fund_count)} Special Purpose Funds are searchable.`,
  answer_url: '/releases/', source_label: 'DBM Status of Allotment Releases workbook',
  limitation: 'An allotment release is authority made available to an agency, not payment or spending and not a project-level receipt.',
})];

const deliveryQuestions = ({ integrity, contracts }) => [
  item({
    id: 'dpwh-recorded-delivery-status', category: 'Projects', state: 'answerable',
    question: 'What status, progress, place, category, contractor, and budget does the archived DPWH record report?',
    scope_label: `${integer(contracts.total_contracts)} archived DPWH contracts`,
    scope_count: contracts.total_contracts, as_of: 'FY2024 to FY2026',
    evidence_level: 'archived_source_record',
    answer_summary: 'The contract explorer exposes the source-reported project fields and evidence state without converting them into a completion finding.',
    answer_url: '/contracts/', source_label: 'Archived DPWH project and contract records',
    limitation: 'Agency-reported status and progress do not independently prove physical completion, quality, acceptance, or payment.',
  }),
  item({
    id: 'deterministic-integrity-signals', category: 'Investigate', state: 'answerable',
    question: 'Which DPWH records contain deterministic contradictions, reused coordinates, or missing fields?',
    scope_label: `${integer(integrity.integrity_signals)} review signals across ${integer(integrity.source_records)} records`,
    scope_count: integrity.integrity_signals, as_of: integrity.source_as_of || 'FY2024 to FY2026',
    evidence_level: 'deterministic_source_review',
    answer_summary: `${integer((integrity.signals || []).length)} published signal types retain the source field, rule, evidence, and limitation.`,
    answer_url: '/integrity/', source_label: 'Archived DPWH delivery records',
    limitation: 'A review signal is a question for verification, not proof of a ghost project, fraud, corruption, or wrongdoing.',
  }),
  item({
    id: 'recorded-contractor-activity', category: 'Contractors', state: 'answerable',
    question: 'Which recorded contractor identities are associated with the most projects and project budget?',
    scope_label: `${integer(integrity.contractors)} recorded contractor identities`,
    scope_count: integrity.contractors, as_of: integrity.source_as_of || 'FY2024 to FY2026',
    evidence_level: 'deterministic_aggregation',
    answer_summary: `${integer(integrity.contractor_associations)} contractor-project associations can be ranked and grouped by region, province, and category.`,
    answer_url: '/integrity/#contractors', source_label: 'DPWH contractor fields with PCAB snapshot context',
    limitation: 'For joint records, the full project budget is associated with every named party because the source does not publish each party share.',
  }),
  item({
    id: 'congressional-district-context', category: 'Places', state: 'answerable',
    question: 'Which congressional district context is associated with a recorded DPWH district-office label?',
    scope_label: `${integer(integrity.district_offices)} mapped office labels covering ${integer(integrity.district_count)} districts`,
    scope_count: integrity.district_offices, as_of: integrity.district_source_retrieved_on || null,
    evidence_level: 'deterministic_office_mapping',
    answer_summary: 'Single-district, shared-office, and unassigned records remain separate so ambiguous office coverage is visible.',
    answer_url: '/integrity/', source_label: 'Official district roster and deterministic office-label map',
    limitation: 'Office context is not a coordinate boundary determination and does not establish a legislator as project author or sponsor.',
  }),
];

const accountabilityQuestions = (accountability = {}) => [item({
  id: 'contractor-accountability-events', category: 'Contractors', state: 'answerable',
  question: 'Which contractor identities have strongly matched official restriction or low performance-rating records?',
  scope_label: `${integer(accountability.blacklist_events)} restriction records and ${integer(accountability.cpes_events)} low CPES ratings`,
  scope_count: count(accountability.blacklist_events) + count(accountability.cpes_events),
  as_of: accountability.checked_on || null,
  evidence_level: 'strong_identity_official_event_match',
  answer_summary: `${integer(accountability.award_signals)} exact archived award rows create a timing question linked to an official event.`,
  answer_url: '/accountability/',
  source_label: 'GPPB blacklisting portal, official CPES reports, PCAB, and archived award mirror',
  limitation: 'A restriction, rating, or date overlap is not proof of corruption, political connection, or an improper award.',
})];

const contextQuestions = ({ cycle, publicValue, source }) => {
  const metadata = cycle.metadata || {};
  return [
    item({
      id: 'budget-cycle-document-availability', category: 'Sources', state: 'answerable',
      question: 'Which FY2027 budget-stage documents have been acquired, verified, discovered, or remain unavailable?',
      scope_label: `${integer(metadata.document_count)} catalogued documents across six legislative stages`,
      scope_count: metadata.document_count, as_of: metadata.retrieved_at || null,
      evidence_level: 'source_separated_catalogue',
      answer_summary: `${integer(metadata.verified_document_count)} documents are verified and ${integer(metadata.discovered_document_count)} remain discovery records.`,
      answer_url: '/budget-trail/', source_label: 'Official budget publishers and the Senate transparency portal',
      limitation: 'A document is classified from its title and contents, not from the website hosting it; missing stages are not inferred.',
    }),
    item({
      id: 'fiscal-program-direction', category: 'Public value', state: 'answerable',
      question: 'What do official FY2027 fiscal indicators say about growth, revenue coverage, debt pressure, and expenditure composition?',
      scope_label: `${integer(publicValue.indicator_count)} official fiscal indicators`,
      scope_count: publicValue.indicator_count, as_of: `FY${count(publicValue.fiscal_year) || 2027}`,
      evidence_level: 'official_fiscal_program',
      answer_summary: `${integer(publicValue.improving_count)} indicators improve, ${integer(publicValue.pressure_count)} show pressure, and ${integer(publicValue.context_count)} provide context under published rules.`,
      answer_url: '/sulit/', source_label: publicValue.source_scope || 'DBM BESF fiscal tables',
      limitation: 'Forecasts and fiscal-program values are not enacted appropriations, delivered projects, or measured public outcomes.',
    }),
    item({
      id: 'monitored-source-revisions', category: 'Coverage', state: 'answerable',
      question: 'Have the monitored official source catalogues changed since the latest automated check?',
      scope_label: source ? `${integer((source.differences || []).length)} detected source differences` : 'No monitor release available',
      scope_count: source ? (source.differences || []).length : 0,
      as_of: source?.checked_at || null, evidence_level: 'automated_source_monitor',
      answer_summary: source?.status === 'unchanged'
        ? 'The latest monitor found no source drift in its configured catalogue checks.'
        : 'The latest monitor requires source review or is not yet available.',
      answer_url: '/coverage/', source_label: 'Deterministic source catalogue monitor',
      limitation: 'The monitor covers configured catalogues and checksums only; it does not guarantee every government publication has been discovered.',
    }),
  ];
};

const partialQuestions = ({ acquisition, coverage, procurement, coa, publicServices }) => {
  const acquisitionCount = count(acquisition.summary?.examined_contracts);
  const procurementCount = count(procurement.metadata?.checked_projects);
  const coaCount = count(coa.metadata?.checked_projects);
  const serviceRecords = publicServices?.records || {};
  const facilities = publicServices?.facilities || {};
  const workTypes = publicServices?.work_types || {};
  return [
    item({
      id: 'school-hospital-counts', category: 'Public services', state: 'partially_answerable',
      question: 'How many acquired records explicitly describe schools, hospitals, or health facilities, including new-build wording?',
      scope_label: `${integer(serviceRecords.total)} records matched by project title`,
      scope_count: serviceRecords.total, as_of: 'FY2024 to FY2027',
      evidence_level: 'deterministic_title_classification',
      answer_summary: `${integer(facilities.school)} school, ${integer(facilities.hospital)} hospital, and ${integer(facilities.health_center)} health-center records are classified; ${integer(workTypes.new_build)} explicitly use new-build wording.`,
      answer_url: '/public-services/', source_label: 'Acquired budget-stage rows and DPWH delivery contracts',
      limitation: 'These are records, not unique facilities. Titles do not prove physical construction, completion, payment, quality, readiness, or public benefit.',
    }),
    item({
      id: 'secondary-contract-evidence', category: 'Procurement', state: 'partially_answerable',
      question: 'Which contracts have an exact row in the archived secondary award mirror?',
      scope_label: `${integer(acquisitionCount)} contracts examined`, scope_count: acquisitionCount,
      as_of: acquisition.summary?.checked_on || null, evidence_level: 'secondary_source_coverage',
      answer_summary: `${integer(acquisition.states?.structured_exact)} structured exact and ${integer(acquisition.states?.title_exact)} title-exact states are separated from conflicts and missing rows.`,
      answer_url: '/contracts/', source_label: 'Archived BetterGov contract-award mirror',
      limitation: 'The mirror is secondary discovery evidence, not an official award notice, contract, payment record, or universal procurement source.',
    }),
    item({
      id: 'project-image-coverage', category: 'Projects', state: 'partially_answerable',
      question: 'Which contracts have source-supplied project images that passed the publication gate?',
      scope_label: coverage ? `${integer(coverage.universe_contracts)} contracts in the latest coverage release` : 'No coverage release available',
      scope_count: coverage?.universe_contracts || 0, as_of: coverage?.released_at || null,
      evidence_level: 'growing_gated_coverage',
      answer_summary: coverage ? `${integer(coverage.verified_exact_contracts)} contracts have exact reconciled image coverage; ${integer(coverage.pending_contracts)} remain pending.` : 'No gated coverage release is available.',
      answer_url: '/coverage/', source_label: 'DPWH project image endpoints and archived image bytes',
      limitation: 'Published source images do not independently prove capture time, exact location, physical completion, quality, or public benefit.',
    }),
    item({
      id: 'official-procurement-evidence', category: 'Procurement', state: 'partially_answerable',
      question: 'Did a reviewed contract appear in an acquired official plan, bid notice, or procurement monitoring report?',
      scope_label: `${integer(procurementCount)} projects in the reviewed pilot`, scope_count: procurementCount,
      as_of: procurement.metadata?.checked_at || null, evidence_level: 'reviewed_pilot',
      answer_summary: `${integer(procurement.metadata?.projects_with_evidence)} reviewed projects have exact official procurement evidence in the current pilot.`,
      answer_url: '/procurement/', source_label: 'PhilGEPS and official agency procurement documents',
      limitation: 'This answer is limited to the reviewed pilot and must not be generalized to the full contract universe.',
    }),
    item({
      id: 'coa-project-observations', category: 'Audit', state: 'partially_answerable',
      question: 'Did a reviewed project appear in an acquired COA report or cited observation?',
      scope_label: `${integer(coaCount)} projects checked in the reviewed pilot`, scope_count: coaCount,
      as_of: coa.metadata?.checked_at || null, evidence_level: 'reviewed_pilot',
      answer_summary: `${integer(coa.metadata?.project_matches)} reviewed project matches and ${integer(coa.metadata?.archived_reports)} archived reports are currently published.`,
      answer_url: '/audit/', source_label: 'Commission on Audit report catalogues and acquired reports',
      limitation: 'This answer is limited to the reviewed pilot. No match does not mean COA clearance, no observation, or no future audit evidence.',
    }),
  ];
};

const unsupported = Object.freeze([
  ['actual-project-payment', 'Payments', 'Was this project actually paid, and is there a voucher, receipt, or payment confirmation?', 'Busisi has not acquired project-level vouchers, receipts, disbursement records, or bank/payment confirmations.'],
  ['physical-project-verification', 'Projects', 'Does the project physically exist, and was it completed to the required quality?', 'Source records and images are not an independent site inspection, engineering acceptance, material test, or quality certification.'],
  ['wrongdoing-determination', 'Accountability', 'Is this a ghost project, fraud, corruption, or other wrongdoing?', 'A lawful finding requires corroborated evidence and competent investigation. Busisi publishes review leads, never a wrongdoing verdict.'],
  ['political-authorship', 'Budget', 'Who inserted, sponsored, or politically motivated a line item?', 'Budget documents show text and amounts, not authorship or motive. Attribution requires authenticated amendment and legislative records.'],
  ['measured-public-benefit', 'Public value', 'Did the project produce its promised public benefit or economic outcome?', 'Appropriations and implementation records do not measure service use, beneficiaries, causal impact, or durable economic outcomes.'],
  ['project-cost-reasonableness', 'Value for money', 'Is this project price reasonable compared with equivalent work?', 'A defensible comparison needs quantities, specifications, location adjustments, market references, and comparable completed projects not yet acquired.'],
].map(([id, category, question, limitation]) => item({
  id, category, question, limitation, state: 'not_supported',
  scope_label: 'No qualifying evidence acquired', scope_count: 0, as_of: null,
  evidence_level: 'unsupported', answer_summary: 'Busisi cannot establish this from current evidence.',
  answer_url: null, source_label: 'Evidence gap',
})));

const loadEvidence = async (database) => {
  const publicServices = await getPublicServicesSummary(database);
  const values = await Promise.all([
    getChangeStats(database), getReviewSummary(database), getAgencyBudgetSummary(database),
    getAllotmentReleaseSummary(database), getIntegritySummary(database),
    getContractIntelligenceSummary(database), getBudgetCycleSummary(database),
    getPublicValueSummary(database), getSourceMonitorStatus(database),
    getAcquisitionCoverage(database), getCoverageStatus(database),
    getProcurementSummary(database), getCoaSummary(database), getAccountabilitySummary(database),
  ]);
  const keys = ['change', 'review', 'agency', 'release', 'integrity', 'contracts', 'cycle',
    'publicValue', 'source', 'acquisition', 'coverage', 'procurement', 'coa', 'accountability'];
  return {
    ...Object.fromEntries(keys.map((key, index) => [key, values[index]])),
    publicServices,
  };
};

export const buildQuestionCatalogue = (evidence) => Object.freeze([
  ...changeQuestions(evidence),
  ...releaseQuestions(evidence.release),
  ...deliveryQuestions(evidence),
  ...accountabilityQuestions(evidence.accountability),
  ...contextQuestions(evidence),
  ...partialQuestions(evidence),
  ...unsupported,
]);

export const getQuestionCatalogue = async (database) => buildQuestionCatalogue(
  await loadEvidence(database),
);

export const summarizeQuestionStates = (records) => records.reduce((states, record) => ({
  ...states,
  [record.state]: count(states[record.state]) + 1,
}), { answerable: 0, partially_answerable: 0, not_supported: 0 });
