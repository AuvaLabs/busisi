import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { parseChangeQuery } from '../src/change-query.js';
import { coaDeskBody, coaReportBody } from '../src/coa-content.js';
import { getProjectCoaEvidence } from '../src/coa-query.js';
import { buildContractOutcome } from '../src/contract-outcome.js';
import { queryContractOutcomes } from '../src/outcome-query.js';
import { procurementDeskBody } from '../src/procurement-content.js';
import { getProjectProcurementEvidence } from '../src/procurement-query.js';
import { getProjectContractEvidence } from '../src/contract-evidence-query.js';
import { getAcquisitionCoverage } from '../src/acquisition-coverage-query.js';
import { parseAgencyQuery } from '../src/agency-budget-query.js';
import { parseExplorerQuery } from '../src/explorer-query.js';
import { parseReviewQuery } from '../src/review-query.js';
import { deliveryRecordBody } from '../src/record-content.js';
import { districtContext } from '../src/district-context.js';
import {
  parseConcentrationQuery,
  parseContractorQuery,
  parseIntegrityQuery,
} from '../src/integrity-query.js';
import worker from '../src/index.js';
import siteWorker from '../src/prelaunch.js';

const migrationPath = fileURLToPath(new URL('../migrations/0001_publication.sql', import.meta.url));
const explorerMigrationPath = fileURLToPath(
  new URL('../migrations/0002_public_explorer.sql', import.meta.url),
);
const changeMigrationPath = fileURLToPath(
  new URL('../migrations/0003_stage_changes.sql', import.meta.url),
);
const reviewMigrationPath = fileURLToPath(
  new URL('../migrations/0004_review_signals.sql', import.meta.url),
);
const integrityMigrationPath = fileURLToPath(
  new URL('../migrations/0005_integrity.sql', import.meta.url),
);
const verificationMigrationPath = fileURLToPath(
  new URL('../migrations/0006_contractor_verification.sql', import.meta.url),
);
const districtMigrationPath = fileURLToPath(
  new URL('../migrations/0007_district_attribution.sql', import.meta.url),
);
const agencyMigrationPath = fileURLToPath(
  new URL('../migrations/0008_agency_budgets.sql', import.meta.url),
);
const publicValueMigrationPath = fileURLToPath(
  new URL('../migrations/0009_public_value.sql', import.meta.url),
);
const budgetCycleMigrationPath = fileURLToPath(
  new URL('../migrations/0010_budget_cycle.sql', import.meta.url),
);
const deliveryDetailsMigrationPath = fileURLToPath(
  new URL('../migrations/0011_delivery_details.sql', import.meta.url),
);
const coaMigrationPath = fileURLToPath(
  new URL('../migrations/0012_coa_audit_evidence.sql', import.meta.url),
);
const procurementMigrationPath = fileURLToPath(
  new URL('../migrations/0013_procurement_evidence.sql', import.meta.url),
);
const awardMirrorMigrationPath = fileURLToPath(
  new URL('../migrations/0014_contract_award_mirror.sql', import.meta.url),
);
const contractEvidenceMigrationPath = fileURLToPath(
  new URL('../migrations/0015_contract_evidence.sql', import.meta.url),
);
const acquisitionUniverseMigrationPath = fileURLToPath(
  new URL('../migrations/0016_acquisition_universe.sql', import.meta.url),
);
const archivedAwardMirrorMigrationPath = fileURLToPath(
  new URL('../migrations/0017_archived_award_mirror.sql', import.meta.url),
);
const contractAcquisitionDetailMigrationPath = fileURLToPath(
  new URL('../migrations/0018_contract_acquisition_detail.sql', import.meta.url),
);
const awardMirrorBundlePath = fileURLToPath(
  new URL('../../../data/budget_watchdog/award-mirror-d1-bundle/contract-award-mirror.sql', import.meta.url),
);
const contractEvidenceBundlePath = fileURLToPath(
  new URL('../../../data/budget_watchdog/contract-evidence-d1-bundle/contract-evidence.sql', import.meta.url),
);
const acquisitionUniverseBundlePath = fileURLToPath(
  new URL('../../../data/budget_watchdog/acquisition-universe-d1-bundle/acquisition-universe.sql', import.meta.url),
);
const seedPath = fileURLToPath(
  new URL('../../../data/budget_watchdog/cloudflare-preview/reviewed-seed.sql', import.meta.url),
);

class LocalStatement {
  constructor(statement) {
    this.statement = statement;
    this.bindings = [];
  }

  bind(...bindings) {
    this.bindings = bindings;
    return this;
  }

  async first(column) {
    const row = this.statement.get(...this.bindings) || null;
    return column && row ? row[column] : row;
  }

  async all() {
    return { results: this.statement.all(...this.bindings) };
  }
}

class LocalD1 {
  constructor() {
    this.database = new DatabaseSync(':memory:');
    this.database.exec(readFileSync(migrationPath, 'utf8'));
    this.database.exec(readFileSync(explorerMigrationPath, 'utf8'));
    this.database.exec(readFileSync(changeMigrationPath, 'utf8'));
    this.database.exec(readFileSync(reviewMigrationPath, 'utf8'));
    this.database.exec(readFileSync(integrityMigrationPath, 'utf8'));
    this.database.exec(readFileSync(verificationMigrationPath, 'utf8'));
    this.database.exec(readFileSync(districtMigrationPath, 'utf8'));
    this.database.exec(readFileSync(agencyMigrationPath, 'utf8'));
    this.database.exec(readFileSync(publicValueMigrationPath, 'utf8'));
    this.database.exec(readFileSync(budgetCycleMigrationPath, 'utf8'));
    this.database.exec(readFileSync(deliveryDetailsMigrationPath, 'utf8'));
    this.database.exec(readFileSync(coaMigrationPath, 'utf8'));
    this.database.exec(readFileSync(procurementMigrationPath, 'utf8'));
    this.database.exec(readFileSync(awardMirrorMigrationPath, 'utf8'));
    this.database.exec(readFileSync(contractEvidenceMigrationPath, 'utf8'));
    this.database.exec(readFileSync(acquisitionUniverseMigrationPath, 'utf8'));
    this.database.exec(readFileSync(archivedAwardMirrorMigrationPath, 'utf8'));
    this.database.exec(readFileSync(contractAcquisitionDetailMigrationPath, 'utf8'));
    this.database.exec(readFileSync(awardMirrorBundlePath, 'utf8'));
    this.database.exec(readFileSync(contractEvidenceBundlePath, 'utf8'));
    this.database.exec(readFileSync(acquisitionUniverseBundlePath, 'utf8'));
    this.database.exec(readFileSync(seedPath, 'utf8'));
    this.database.exec(`
      INSERT INTO public_metadata VALUES ('budget_records', '2'), ('delivery_records', '2'), ('candidate_links', '2');
      INSERT INTO budget_items VALUES
        ('2025:pump', '18-001|pump', 2025, 'Construction of San Andres Pumping Station', 40000000000, 'family:pump', 'san andres pumping station', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        ('2024:road', '18-001|road', 2024, 'Maintenance, Repair and Rehabilitation of Infrastructure Facilities and Other Related Activities - Routine Maintenance of National Roads', 1000000000, 'family:road', 'routine maintenance of national roads', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        ('2026:bridge', '18-001|bridge', 2026, 'Sample public bridge project Phase I', 8000, 'family:bridge', 'sample public bridge project', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
      INSERT INTO delivery_items VALUES
        ('25O00113', 2025, 'Construction of San Andres Pumping Station', 37679270658, 'Manila 1st DEO, NCR', 'GAA 2025', 'family:pump', 'san andres pumping station', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'),
        ('26ZERO01', 2026, 'Construction of Sample Health Center', 0, 'Cebu, Region VII', 'GAA 2026', 'family:health', 'sample health center', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'),
        ('24NO0001', 2024, 'Rehabilitation of Sample Road', 125000000, 'Quezon 1st DEO, Region IV-A', 'GAA 2024', 'family:no-match', 'rehabilitation sample road', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
      INSERT INTO delivery_project_details VALUES
        ('25O00113', 2025, 'Flood Control', 'On-Going', '62.5', 'ACME BUILDERS (12345)',
         '[{"contractor_key":"pcab:12345","contractor_name":"ACME BUILDERS","pcab_id":"12345"}]',
         '2025-01-15', '2025-12-20', 'Manila 1st DEO', 'NCR', '14.5995', '120.9842', 1,
         '${'b'.repeat(64)}'),
        ('26ZERO01', 2026, 'Buildings and Facilities', 'Not Yet Started', '0', '', '[]',
         '', '', 'Cebu', 'Region VII', '', '', 0, '${'b'.repeat(64)}'),
        ('24NO0001', 2024, 'Roads', 'On-Going', '', '', '[]',
         '', '', 'Quezon 1st DEO', 'Region IV-A', '', '', 0, '${'b'.repeat(64)}');
      INSERT INTO coa_metadata VALUES
        ('checked_at', '2026-11-03T12:00:00+04:00'), ('report_count', '1'),
        ('archived_reports', '0'), ('checked_projects', '3'), ('project_matches', '1'),
        ('status:not_covered', '2'), ('status:reviewed_observation_match', '1'),
        ('catalog_sha256', '${'8'.repeat(64)}');
      INSERT INTO coa_source_catalogs VALUES
        ('coa-aar-nga', 'COA NGA Annual Audit Reports',
         'https://www.coa.gov.ph/reports/annual-audit-reports/aar-national-government-agencies/',
         'blocked', 'Official catalogue checked; deterministic acquisition was blocked.');
      INSERT INTO coa_reports VALUES
        ('coa-report-1', 'DPWH reviewed annual audit report', 'annual_audit_report',
         'Department of Public Works and Highways', 2025, '2026-06-01',
         'https://www.coa.gov.ph/wpfd_file/dpwh-reviewed-report/',
         'https://www.coa.gov.ph/reports/', 'discovered', NULL, NULL, NULL,
         'Agency accounts and operations.', 'Official report record discovered.');
      INSERT INTO coa_project_coverage VALUES
        ('pump-reviewed', '25O00113', 2025, 'reviewed_observation_match', 'coa-report-1',
         'exact', '["contract_id"]', 12, 13, 'The report discusses this contract.',
         'Verify delivery records.', 'Management agreed to review the record.', 'in_progress',
         'Contract identifier appears on the cited pages.', '2026-11-03'),
        ('health-uncovered', '26ZERO01', 2026, 'not_covered', NULL, 'none', '[]', NULL, NULL,
         '', '', '', 'not_applicable',
         'No qualifying project-level COA evidence was located.', '2026-11-03'),
        ('corazon-2024-phase-1', '24HI0148', 2024, 'not_covered', NULL, 'none', '[]',
         NULL, NULL, '', '', '', 'not_applicable',
         'No qualifying project-level COA evidence was located.', '2026-11-03');
      INSERT INTO procurement_metadata VALUES
        ('checked_at', '2026-11-03T15:47:02+04:00'), ('source_count', '1'),
        ('archived_sources', '1'), ('record_count', '1'), ('exact_records', '1'),
        ('checked_projects', '2'), ('projects_with_evidence', '1'),
        ('status:exact_evidence', '1'), ('status:not_located', '1'),
        ('catalog_sha256', '${'7'.repeat(64)}');
      INSERT INTO procurement_sources VALUES
        ('philgeps-test', 'PhilGEPS bid notice 123', 'PhilGEPS', 'bid_notice', 2025,
         NULL, 'https://notices.philgeps.gov.ph/test', 'verified_archived',
         '${'6'.repeat(64)}', 1234, NULL, 'Original official HTML archived.'),
        ('dpwh-pmr-test', 'DPWH procurement monitoring report', 'DPWH Cebu 5th DEO',
         'procurement_monitoring_report', 2024, '2024-12-31',
         'https://www.dpwh.gov.ph/test-pmr.pdf', 'blocked', NULL, NULL, NULL,
         'Official source discovered; archive blocked.'),
        ('dpwh-app-test', 'DPWH annual procurement plan', 'DPWH Cebu 5th DEO',
         'annual_procurement_plan', 2025, '2025-01-31',
         'https://www.dpwh.gov.ph/test-app.pdf', 'discovered', NULL, NULL, NULL,
         'Official plan row discovered.');
      INSERT INTO procurement_records VALUES
        ('philgeps-25o00113', 'pump-reviewed', '25O00113', 2025, 'philgeps-test',
         'bid_notice', 'exact_solicitation_number', 'Construction of San Andres Pumping Station',
         'DPWH Test Office', 'Public Bidding', 'Awarded', NULL, '123', 40000000000,
         37679270658, 2320729342, '[]',
         '[{"stage":"advertisement","event_date":"2024-11-06","date_kind":"actual"},{"stage":"bid_opening","event_date":"2024-11-26","date_kind":"actual"},{"stage":"notice_of_award","event_date":"2025-02-04","date_kind":"actual"}]',
         '2026-11-03', 'Bid evidence does not prove payment or completion.'),
        ('pmr-24hi0148', 'corazon-2024-phase-1', '24HI0148', 2024, 'dpwh-pmr-test',
         'monitoring_report', 'exact_contract_id', 'Construction of Multi-Purpose Building',
         'DPWH Cebu 5th DEO', 'Competitive Bidding', 'Completed', 6, NULL, 495000000,
         494467510, 532490, '["COA","PICE"]',
         '[{"stage":"advertisement","event_date":"2024-07-31","date_kind":"actual"},{"stage":"notice_of_award","event_date":"2024-09-02","date_kind":"actual"},{"stage":"notice_to_proceed","event_date":"2024-09-05","date_kind":"actual"}]',
         '2026-11-03', 'PMR status does not prove physical completion.'),
        ('app-25o00113', 'pump-reviewed', '25O00113', 2025, 'dpwh-app-test',
         'plan', 'exact_contract_id', 'Construction of San Andres Pumping Station',
         'DPWH Test Office', 'Competitive Bidding', 'Early procurement activity planned',
         5, NULL, 40000000000, NULL, NULL, '[]',
         '[{"stage":"advertisement","event_date":"2024-11-06","date_kind":"planned"},{"stage":"bid_opening","event_date":"2024-11-26","date_kind":"planned"},{"stage":"contract_signing","event_date":"2025-02-14","date_kind":"planned"}]',
         '2026-11-03', 'Planned dates are not evidence that events occurred.');
      INSERT INTO procurement_project_coverage VALUES
        ('pump-reviewed', '25O00113', 2025, 'exact_evidence', 2,
         'Exact solicitation number located.', '2026-11-03'),
        ('health-uncovered', '26ZERO01', 2026, 'not_located', 0,
         'No exact official procurement artifact was located.', '2026-11-03'),
        ('corazon-2024-phase-1', '24HI0148', 2024, 'exact_evidence', 1,
         'Exact contract ID located on page 6.', '2026-11-03'),
        ('corazon-2026-completion', '26HI0094', 2026, 'quarantined', 0,
         'Underlying relationship and procurement evidence remain quarantined.', '2026-11-03');
      INSERT INTO candidate_links VALUES
        ('2025:pump:25O00113', 2025, '18-001|pump', '25O00113', 'high', 90, '["year_match"]', 'Construction of San Andres Pumping Station', 'Construction of San Andres Pumping Station', 40000000000, 37679270658, 2320729342, 'https://budget.example/pump', 'https://dpwh.example/25O00113', 'candidate'),
        ('2026:health:26ZERO01', 2026, '18-001|health', '26ZERO01', 'candidate', 70, '["year_match"]', 'Construction of Sample Health Center', 'Construction of Sample Health Center', 2500000000, 0, 2500000000, 'https://budget.example/health', 'https://dpwh.example/26ZERO01', 'candidate');
      INSERT INTO stage_change_metadata VALUES
        ('record_count', '4'), ('quarantine_count', '1'), ('source_commit', '${'a'.repeat(40)}');
      INSERT INTO stage_change_items VALUES
        ('dpwh:1', 2027, 'dpwh', 'Sample bridge', 'Network Development', 'Bridge Program', 'Region III', 'Manila 1st DEO', 'increased', 'Higher in the House bill', 'candidate', 0, 1, 10000, 15000, 5000, 'https://budget.example/1', 'https://budget.example/nep.pdf#page=1', 'https://budget.example/house.pdf#page=2', 1, 2, '${'a'.repeat(40)}', '${'b'.repeat(64)}', 'sample public bridge project'),
        ('hfep:2', 2027, 'hfep', 'Sample health center', 'HFEP', '', 'Region VII', 'DOH', 'house_only', 'In the House bill only', 'candidate', 0, 0, 0, 20000, 20000, 'https://budget.example/2', '', 'https://budget.example/house.pdf#page=3', NULL, 3, '${'a'.repeat(40)}', '${'c'.repeat(64)}', 'sample health center'),
        ('dpwh:3', 2027, 'dpwh', 'Held road match', 'Road Program', '', 'NCR', 'Central Office', 'scope_review', 'Different scope', 'quarantine', 1, 0, 30000, 35000, 5000, 'https://budget.example/3', 'https://budget.example/nep.pdf#page=4', 'https://budget.example/house.pdf#page=5', 4, 5, '${'a'.repeat(40)}', '${'d'.repeat(64)}', 'held road match'),
        ('dpwh:4', 2027, 'dpwh', 'Sample bridge Phase II', 'Network Development', 'Bridge Program', 'Region III', 'Quezon 1st DEO', 'house_only', 'In the House bill only', 'candidate', 0, 0, 0, 12000, 12000, 'https://budget.example/4', '', 'https://budget.example/house.pdf#page=6', NULL, 6, '${'a'.repeat(40)}', '${'e'.repeat(64)}', 'sample public bridge project');
      INSERT INTO integrity_metadata VALUES
        ('source_records', '3'), ('delivery_details', '2'), ('integrity_signals', '3'), ('contractors', '2'),
        ('concentrations', '2'), ('pcab_records', '1'),
        ('pcab_retrieved_on', '2026-11-03'),
        ('pcab_source_sha256', '${'e'.repeat(64)}'),
        ('pcab_status:current_regular', '1'),
        ('pcab_status:not_found_current_regular', '1'),
        ('source_artifact_sha256', '${'f'.repeat(64)}'),
        ('district_count', '3'), ('district_offices', '2'),
        ('district_source_commit', '${'d'.repeat(40)}'),
        ('district_source_built_at', '2026-10-26T08:46:14.383Z'),
        ('district_source_retrieved_on', '2026-11-03'),
        ('district_snapshot_sha256', '${'9'.repeat(64)}'),
        ('district_coverage:single_district', '1'),
        ('district_coverage:shared_office', '1'),
        ('district_coverage:unassigned', '1'),
        ('signal:status_progress_conflict', '1'),
        ('signal:missing_coordinate', '1'),
        ('signal:coordinate_location_conflict', '1');
      INSERT INTO integrity_signal_items VALUES
        ('25A:status_progress_conflict', '25A', 2025, 'status_progress_conflict', 'source_conflict', 'Ongoing with 100% progress', 'Construction of public market', 'ACME BUILDERS', '12345', 10000000, 'On-Going', '100', 'Manila 1st DEO', 'NCR', '14.5995', '120.9842', 'Status is On-Going; reported progress is 100%.', 'The status field may update later.', '${'f'.repeat(64)}'),
        ('24B:missing_coordinate', '24B', 2024, 'missing_coordinate', 'coverage_gap', 'Coordinate not available', 'Repair of public hospital', 'ACME BUILDERS', '12345', 20000000, 'Completed', '100', 'Quezon 1st DEO', 'Region IV-A', '', '', 'No usable coordinate.', 'Missing coordinates do not indicate a missing project.', '${'f'.repeat(64)}'),
        ('25C:coordinate_location_conflict', '25C', 2025, 'coordinate_location_conflict', 'source_conflict', 'Shared coordinate has conflicting location labels', 'Construction of road', 'SECOND BUILDERS', '67890', 30000000, 'Completed', '100', 'Cebu 1st DEO', 'Region VII', '10.3157', '123.8854', 'Coordinate appears under multiple labels.', 'Office labels can differ from boundaries.', '${'f'.repeat(64)}');
      INSERT INTO contractor_rankings VALUES
        ('pcab:12345', 'ACME BUILDERS', '12345', 2, 30000000, 1, 1, 0, 2024, 2025, 1, 'current_regular', 'ACME BUILDERS, INC.', 'AAA', '2027-12-31', 1, '${'e'.repeat(64)}'),
        ('pcab:67890', 'SECOND BUILDERS', '67890', 1, 30000000, 1, 0, 0, 2025, 2025, 0, 'not_found_current_regular', '', '', '', -1, '${'e'.repeat(64)}');
      INSERT INTO contractor_concentrations VALUES
        ('region', 'NCR', 0, 10, 9, 10, 4, 'pcab:12345', 'ACME BUILDERS', '12345', 4, 4000, 90000000),
        ('region', 'Region VII', 0, 12, 12, 12, 6, 'pcab:67890', 'SECOND BUILDERS', '67890', 3, 2500, 50000000);
      INSERT INTO district_office_attributions VALUES
        ('manila 1st deo', 'Manila 1st DEO', 'single_district', 1,
          '[{"district_id":"leg:manila:1st","label":"City of Manila, 1st District","representative_name":"Representative One","representative_status":"resolved","representative_status_note":"","representative_profile_url":"https://www.congress.gov.ph/house-members/view/A001"}]',
          '${'d'.repeat(40)}', '2026-10-26T08:46:14.383Z', '2026-11-03', '${'9'.repeat(64)}'),
        ('quezon 1st deo', 'Quezon 1st DEO', 'shared_office', 2,
          '[{"district_id":"leg:quezon:1st","label":"Quezon, 1st District","representative_name":"Representative Two","representative_status":"resolved","representative_status_note":"","representative_profile_url":"https://www.congress.gov.ph/house-members/view/A002"},{"district_id":"leg:quezon:2nd","label":"Quezon, 2nd District","representative_name":"Representative Three; Representative Four","representative_status":"ambiguous","representative_status_note":"Official roster lists multiple current names; no representative was selected.","representative_profile_url":""}]',
          '${'d'.repeat(40)}', '2026-10-26T08:46:14.383Z', '2026-11-03', '${'9'.repeat(64)}');
      INSERT INTO agency_budget_metadata VALUES
        ('record_count', '3'), ('appropriation_heads', '2'), ('congress_institutions', '1'),
        ('compared_records', '2'), ('unavailable_records', '1'),
        ('fiscal_year', '2027'), ('baseline_year', '2026'),
        ('nep_bill_scope_centavos', '300000'), ('house_bill_scope_centavos', '340000'),
        ('house_control_centavos', '340000');
      INSERT INTO agency_budget_items VALUES
        ('head:18', 2027, 2026, 'appropriation_head', NULL, '18', 'Department of Public Works and Highways', 90000, 100000, 130000, 30000, 3000, 'compared', 'house-ib', '[113]', 'https://example.test/ib.pdf', 'https://budget.example/nep', '${'1'.repeat(64)}', '${'2'.repeat(64)}', 'Compared source total.'),
        ('head:AUTO', 2027, 2026, 'appropriation_head', NULL, 'AUTO', 'Automatic Appropriations', 190000, 200000, NULL, NULL, NULL, 'not_applicable', NULL, '[]', NULL, 'https://budget.example/nep', '${'1'.repeat(64)}', NULL, 'Outside House bill comparison.'),
        ('congress:004', 2027, 2026, 'congress_institution', 'head:01', '004', 'House of Representatives', 80000, 100000, 210000, 110000, 11000, 'compared', 'house-ia', '[19]', 'https://example.test/ia.pdf', 'https://budget.example/congress', '${'3'.repeat(64)}', '${'4'.repeat(64)}', 'Compared source total.');
      INSERT INTO public_value_metadata VALUES
        ('reading', 'mixed'), ('indicator_count', '2'), ('improving_count', '1'),
        ('pressure_count', '1'), ('context_count', '0'), ('fiscal_year', '2027'),
        ('baseline_year', '2026'), ('revenue_coverage_bps', '7544'),
        ('expenditure_per_capita_centavos', '6244753'),
        ('source_scope', 'FY2027 BESF Tables A.1 and A.2'),
        ('evidence_boundary', 'DBM projections and fiscal program');
      INSERT INTO public_value_indicators VALUES
        ('real_gdp_growth', 'economy', 'Real GDP growth forecast', 'range_basis_points', 400, 550, 350, 450, 500, 600, 150, 'improving', 'Higher is treated as favorable for this indicator.', 'besf-a1', 1, 'https://www.dbm.gov.ph/A1.pdf', '${'5'.repeat(64)}', 'Forecast range, not an observed outcome.'),
        ('interest_share', 'fiscal_space', 'Interest share of disbursements', 'basis_points', 1540, 1610, NULL, NULL, NULL, NULL, 70, 'pressure', 'Lower is treated as favorable for this indicator.', 'besf-a2', 2, 'https://www.dbm.gov.ph/A2.pdf', '${'6'.repeat(64)}', '');
      INSERT INTO budget_cycle_metadata VALUES
        ('fiscal_year', '2027'), ('document_count', '2'),
        ('verified_document_count', '1'), ('discovered_document_count', '1'),
        ('acquisition_status', 'direct_blocked_secondary_discovery'),
        ('source_url', 'https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027'),
        ('retrieved_at', '2026-11-03T08:58:00+00:00'),
        ('catalog_sha256', '${'7'.repeat(64)}');
      INSERT INTO budget_cycle_stages VALUES
        ('nep', 1, 'available_elsewhere', 0),
        ('house_gab', 2, 'partial', 1),
        ('senate_committee', 3, 'unavailable', 0),
        ('senate_amendment', 4, 'unavailable', 0),
        ('bicam', 5, 'unavailable', 0),
        ('gaa', 6, 'unavailable', 0);
      INSERT INTO budget_cycle_documents VALUES
        ('senate-portal:385', 2027, '385', 'HB 10858 FOR 3RD READING VOL I-B', 'house_gab', 'House bill, third reading', 'Senate Budget Transparency Portal', 'I-B', '2026-10-13', 'https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027', 'https://budget-transparency-portal.senate.gov.ph/file_viewer?id=385&type=Documents', 'verified_archived', '${'4'.repeat(64)}', 15663076, 'https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf', 'Archived copy verified by SHA-256.'),
        ('senate-portal:417', 2027, '417', 'SEPO Budget Notes', 'supporting', 'Supporting fiscal analysis', 'Senate Budget Transparency Portal', NULL, NULL, 'https://budget-transparency-portal.senate.gov.ph/public/Documents?gaa_year=2027', 'https://budget-transparency-portal.senate.gov.ph/file_viewer?id=417&type=Documents', 'discovered', NULL, NULL, NULL, 'Catalogue discovery only.');
      INSERT INTO contract_acquisition_metadata VALUES
        ('award_revision', '${'c'.repeat(40)}'),
        ('award_sha256', '${'a'.repeat(64)}'),
        ('checked_on', '2026-11-03'),
        ('delivery_sha256', '${'b'.repeat(64)}');
      INSERT INTO contract_acquisition_details VALUES
        ('25O00113', 2025, 'valid', 'aligned', 'structured_exact', 1, 0),
        ('26ZERO01', 2026, 'valid', 'aligned', 'conflict_review', 0, 1),
        ('24NO0001', 2024, 'valid', 'aligned', 'no_exact_row', 0, 0);
      INSERT INTO contract_award_matches VALUES
        ('award-row-1', '25O00113', 'structured_exact', '25O00113', '25O00113',
         'Construction of San Andres Pumping Station', 'Award notice 25O00113',
         'ACME BUILDERS', 'DPWH Test Office', 'Manila', 'Civil works', 37679270658,
         '2025-02-04', 'Awarded', '${'1'.repeat(64)}');
      INSERT INTO contract_quarantine_rows VALUES
        ('award-row-conflict', 'conflicting_exact_identifiers', '${'2'.repeat(64)}',
         '26ZERO01', '25O00113', 'Construction of Sample Health Center',
         'Conflicting archived award mirror row');
      INSERT INTO contract_quarantine_candidates VALUES
        ('award-row-conflict', '25O00113'), ('award-row-conflict', '26ZERO01');
    `);
  }

  prepare(sql) {
    return new LocalStatement(this.database.prepare(sql));
  }

  close() {
    this.database.close();
  }
}

const environment = (database, allowed = true) => ({
  DB: database,
  ASSETS: { fetch: async () => new Response('<h1>Busisi</h1>', { headers: { 'Content-Type': 'text/html' } }) },
  PUBLIC_API_RATE_LIMITER: { limit: async () => ({ success: allowed }) },
});

const request = (path, init) => new Request(`https://busisi.test${path}`, init);

const explorerUrl = (query = '') => new URL(`https://busisi.test/api/v1/budgets${query}`);
const changeUrl = (query = '') => new URL(`https://busisi.test/api/v1/changes${query}`);
const reviewUrl = (query = '') => new URL(`https://busisi.test/api/v1/review-rankings${query}`);
const integrityUrl = (query = '') => new URL(`https://busisi.test/api/v1/integrity-signals${query}`);
const contractorUrl = (query = '') => new URL(`https://busisi.test/api/v1/contractors${query}`);
const concentrationUrl = (query = '') => new URL(`https://busisi.test/api/v1/contractor-concentrations${query}`);
const agencyUrl = (query = '') => new URL(`https://busisi.test/api/v1/agency-budgets${query}`);

test('validates appropriation-head query filters and cursor contract', () => {
  for (const [query, message] of [
    ['?level=department', 'level is invalid'],
    ['?direction=corruption', 'direction is invalid'],
    ['?sort=unknown', 'sort is invalid'],
    ['?limit=0', 'limit is outside the supported range'],
    [`?q=${'x'.repeat(201)}`, 'q is too long'],
    ['?cursor=broken', 'cursor is invalid for this query'],
  ]) {
    assert.throws(() => parseAgencyQuery(agencyUrl(query)), { name: 'QueryError', message });
  }
  const fingerprint = ['House', 'congress', 'decrease', 'name_asc'].join('|');
  const cursor = Buffer.from(JSON.stringify({ v: 1, offset: 1, fingerprint })).toString('base64url');
  assert.equal(parseAgencyQuery(agencyUrl(
    `?q=House&level=congress&direction=decrease&sort=name_asc&limit=1&cursor=${cursor}`,
  )).offset, 1);
  for (const payload of [
    { v: 2, offset: 1, fingerprint },
    { v: 1, offset: -1, fingerprint },
    { v: 1, offset: 1, fingerprint: 'wrong' },
  ]) {
    const invalid = Buffer.from(JSON.stringify(payload)).toString('base64url');
    assert.throws(
      () => parseAgencyQuery(agencyUrl(`?q=House&level=congress&direction=decrease&sort=name_asc&limit=1&cursor=${invalid}`)),
      { name: 'QueryError', message: 'cursor is invalid for this query' },
    );
  }
});

test('publishes the source-separated FY2027 budget-cycle catalogue', async () => {
  const database = new LocalD1();
  const summary = await worker.fetch(
    request('/api/v1/budget-cycle'), environment(database),
  );
  const documents = await worker.fetch(
    request('/api/v1/budget-cycle/documents'), environment(database),
  );
  const summaryBody = await summary.json();
  const documentBody = await documents.json();

  assert.equal(summary.status, 200);
  assert.equal(summaryBody.data.metadata.fiscal_year, '2027');
  assert.equal(summaryBody.data.stages.length, 6);
  assert.equal(summaryBody.data.stages.find(({ stage }) => stage === 'gaa').status, 'unavailable');
  assert.equal(documentBody.meta.total, 2);
  assert.equal(documentBody.data[0].stage, 'house_gab');
  assert.equal(documentBody.data[0].acquisition_status, 'verified_archived');
  assert.equal(documentBody.data[1].stage, 'supporting');
  database.close();
});

test('keeps unavailable and malformed district evidence unassigned', () => {
  assert.equal(districtContext({}).classification, 'unassigned');
  assert.equal(districtContext({
    district_classification: 'single_district',
    districts_json: '{broken',
  }).classification, 'unassigned');
  assert.equal(districtContext({
    district_classification: 'shared_office',
    district_office_name: 'Shared DEO',
    districts_json: '{}',
  }).classification, 'unassigned');
});

test('validates every explorer query boundary and cursor contract', () => {
  const invalid = [
    ['unknown', '', 'collection is not available'],
    ['budgets', '?year=not-a-year', 'year is invalid'],
    ['budgets', '?year=1999', 'year is outside the supported range'],
    ['budgets', '?limit=0', 'limit is outside the supported range'],
    ['budgets', '?limit=101', 'limit is outside the supported range'],
    ['budgets', `?q=${'x'.repeat(201)}`, 'q is too long'],
    ['budgets', '?sort=unknown', 'sort is invalid'],
    ['budgets', '?signal=zero_budget', 'signal is invalid'],
    ['candidates', '?signal=unknown', 'signal is invalid'],
    ['budgets', '?cursor=not-base64', 'cursor is invalid for this query'],
  ];
  for (const [kind, query, message] of invalid) {
    assert.throws(() => parseExplorerQuery(explorerUrl(query), kind), { name: 'QueryError', message });
  }

  const fingerprint = ['budgets', '', null, 'amount_desc', 'all'].join('|');
  const cursor = Buffer.from(JSON.stringify({ v: 1, offset: 2, fingerprint })).toString('base64url');
  const parsed = parseExplorerQuery(explorerUrl(`?cursor=${cursor}`), 'budgets');
  assert.equal(parsed.offset, 2);

  const mismatched = Buffer.from(JSON.stringify({ v: 1, offset: 2, fingerprint: 'wrong' }))
    .toString('base64url');
  assert.throws(
    () => parseExplorerQuery(explorerUrl(`?cursor=${mismatched}`), 'budgets'),
    { name: 'QueryError', message: 'cursor is invalid for this query' },
  );
});

test('validates every stage-change query boundary and cursor contract', () => {
  const invalid = [
    ['?limit=none', 'limit is invalid'],
    ['?limit=0', 'limit is outside the supported range'],
    ['?limit=101', 'limit is outside the supported range'],
    [`?q=${'x'.repeat(201)}`, 'q is too long'],
    [`?region=${'x'.repeat(201)}`, 'region is too long'],
    ['?dataset=unknown', 'dataset is invalid'],
    ['?change=unknown', 'change is invalid'],
    ['?review=unknown', 'review is invalid'],
    ['?sort=unknown', 'sort is invalid'],
    ['?cursor=not-base64', 'cursor is invalid for this query'],
  ];
  for (const [query, message] of invalid) {
    assert.throws(() => parseChangeQuery(changeUrl(query)), { name: 'QueryError', message });
  }

  const fingerprint = ['', 'all', 'all', '', 'all', 'absolute_desc'].join('|');
  const cursor = Buffer.from(JSON.stringify({ v: 1, offset: 2, fingerprint })).toString('base64url');
  assert.equal(parseChangeQuery(changeUrl(`?cursor=${cursor}`)).offset, 2);

  for (const payload of [
    { v: 2, offset: 2, fingerprint },
    { v: 1, offset: -1, fingerprint },
    { v: 1, offset: 2, fingerprint: 'wrong' },
  ]) {
    const invalidCursor = Buffer.from(JSON.stringify(payload)).toString('base64url');
    assert.throws(
      () => parseChangeQuery(changeUrl(`?cursor=${invalidCursor}`)),
      { name: 'QueryError', message: 'cursor is invalid for this query' },
    );
  }
});

test('validates deterministic review filters', () => {
  const invalid = [
    ['?signal=corruption', 'signal is invalid'],
    ['?dataset=unknown', 'dataset is invalid'],
    ['?dimension=contractor', 'dimension is invalid'],
    ['?limit=none', 'limit is invalid'],
    ['?limit=0', 'limit is outside the supported range'],
    ['?limit=101', 'limit is outside the supported range'],
  ];
  for (const [query, message] of invalid) {
    assert.throws(() => parseReviewQuery(reviewUrl(query)), { name: 'QueryError', message });
  }
  assert.deepEqual(parseReviewQuery(reviewUrl()), {
    signal: 'house_only', dataset: 'all', dimension: 'region', limit: 25,
  });
  assert.deepEqual(parseReviewQuery(reviewUrl('?dataset=dpwh&dimension=office&limit=1')), {
    signal: 'house_only', dataset: 'dpwh', dimension: 'office', limit: 1,
  });
});

test('validates project-integrity and contractor filters', () => {
  for (const [query, message] of [
    ['?signal=corruption', 'signal is invalid'],
    ['?classification=accusation', 'classification is invalid'],
    ['?year=not-a-year', 'year is invalid'],
    ['?limit=101', 'limit is outside the supported range'],
    [`?q=${'x'.repeat(201)}`, 'q is too long'],
  ]) {
    assert.throws(() => parseIntegrityQuery(integrityUrl(query)), {
      name: 'QueryError', message,
    });
  }
  assert.deepEqual(parseIntegrityQuery(integrityUrl()), {
    q: '', signal: 'all', classification: 'all', year: null,
    sort: 'budget_desc', limit: 25, offset: 0,
  });
  assert.throws(() => parseContractorQuery(contractorUrl('?sort=risk')), {
    name: 'QueryError', message: 'sort is invalid',
  });
  assert.deepEqual(parseContractorQuery(contractorUrl('?sort=budget_desc&limit=10')), {
    q: '', sort: 'budget_desc', limit: 10, offset: 0,
  });
  assert.deepEqual(parseConcentrationQuery(concentrationUrl('?dimension=region&year=0')), {
    dimension: 'region', year: 0,
  });
  assert.deepEqual(parseConcentrationQuery(concentrationUrl()), {
    dimension: 'region', year: 0,
  });
  assert.throws(() => parseConcentrationQuery(concentrationUrl('?dimension=office')), {
    message: 'dimension is invalid',
  });
  assert.throws(() => parseConcentrationQuery(concentrationUrl('?year=1999')), {
    message: 'year is outside the supported range',
  });

  const integrityFingerprint = ['market', 'status_progress_conflict', 'source_conflict', 2025, 'year_desc'].join('|');
  const integrityCursor = Buffer.from(JSON.stringify({
    v: 1, offset: 1, fingerprint: integrityFingerprint,
  })).toString('base64url');
  assert.equal(parseIntegrityQuery(integrityUrl(
    `?q=market&signal=status_progress_conflict&classification=source_conflict&year=2025&sort=year_desc&cursor=${integrityCursor}`,
  )).offset, 1);

  const contractorFingerprint = ['ACME', 'name_asc'].join('|');
  const contractorCursor = Buffer.from(JSON.stringify({
    v: 1, offset: 1, fingerprint: contractorFingerprint,
  })).toString('base64url');
  assert.equal(parseContractorQuery(contractorUrl(
    `?q=ACME&sort=name_asc&cursor=${contractorCursor}`,
  )).offset, 1);

  for (const payload of [
    { v: 2, offset: 1, fingerprint: integrityFingerprint },
    { v: 1, offset: -1, fingerprint: integrityFingerprint },
    { v: 1, offset: 1, fingerprint: 'wrong' },
  ]) {
    const invalidCursor = Buffer.from(JSON.stringify(payload)).toString('base64url');
    assert.throws(
      () => parseIntegrityQuery(integrityUrl(`?q=market&signal=status_progress_conflict&classification=source_conflict&year=2025&sort=year_desc&cursor=${invalidCursor}`)),
      { name: 'QueryError', message: 'cursor is invalid for this query' },
    );
  }
});

test('lists reviewed records with stable cursor pagination', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const first = await worker.fetch(request('/api/v1/projects?q=Catmon&limit=2'), environment(database));
  const firstBody = await first.json();
  const second = await worker.fetch(
    request(`/api/v1/projects?q=Catmon&limit=2&cursor=${firstBody.meta.next_cursor}`),
    environment(database),
  );
  const secondBody = await second.json();

  assert.equal(first.status, 200);
  assert.equal(firstBody.meta.total, 5);
  assert.equal(firstBody.data.length, 2);
  assert.equal(secondBody.data.length, 2);
  assert.deepEqual(
    new Set([...firstBody.data, ...secondBody.data].map((record) => record.slug)).size,
    4,
  );
});

test('returns dossiers and filtered server CSV', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const dossier = await worker.fetch(
    request('/api/v1/projects/corazon-2024-phase-1'),
    environment(database),
  );
  const csv = await worker.fetch(request('/api/v1/projects.csv?year=2024'), environment(database));

  assert.equal((await dossier.json()).data.contract_id, '24HI0148');
  assert.equal(csv.headers.get('content-disposition'), 'attachment; filename=busisi-project-records.csv');
  assert.equal((await csv.text()).trim().split('\n').length, 3);
});

test('publishes source collection statistics and separate record APIs', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const stats = await worker.fetch(request('/api/v1/stats'), environment(database));
  const budgets = await worker.fetch(
    request('/api/v1/budgets?q=pumping&year=2025'),
    environment(database),
  );
  const delivery = await worker.fetch(
    request('/api/v1/delivery?q=Manila'),
    environment(database),
  );

  assert.deepEqual((await stats.json()).data, {
    budget_records: 2,
    delivery_records: 2,
    candidate_links: 2,
    reviewed_dossiers: 6,
  });
  const budgetBody = await budgets.json();
  const deliveryBody = await delivery.json();
  assert.equal(budgetBody.meta.total, 1);
  assert.equal(budgetBody.data[0].amount_centavos, 40000000000);
  assert.match(budgetBody.data[0].source_url, /budget\.bettergov\.ph/);
  assert.equal(
    budgetBody.data[0].reader_source_url,
    '/records/budget/2025%3Apump/',
  );
  assert.equal(
    budgetBody.data[0].official_documents_url,
    'https://www.dbm.gov.ph/index.php/2025/general-appropriations-act-gaa-fy-2025',
  );
  assert.doesNotMatch(budgetBody.data[0].reader_source_url, /\/api\//);
  assert.equal(deliveryBody.meta.total, 1);
  assert.equal(deliveryBody.data[0].contract_id, '25O00113');
  assert.equal(
    deliveryBody.data[0].reader_source_url,
    '/contracts/25O00113/',
  );
  assert.equal(deliveryBody.data[0].district_context.classification, 'single_district');
  assert.equal(deliveryBody.data[0].district_context.districts[0].representative_name, 'Representative One');
});

test('publishes contract-level acquisition evidence without overstating the mirror', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const exact = await worker.fetch(
    request('/api/v1/contracts/25O00113'),
    environment(database),
  );
  const conflict = await worker.fetch(
    request('/api/v1/contracts/26ZERO01'),
    environment(database),
  );
  const absent = await worker.fetch(
    request('/api/v1/contracts/24NO0001'),
    environment(database),
  );
  const exactBody = await exact.json();
  const conflictBody = await conflict.json();
  const absentBody = await absent.json();

  assert.equal(exact.status, 200);
  assert.equal(exactBody.data.acquisition.match_state, 'structured_exact');
  assert.equal(exactBody.data.award_matches[0].awardee_name, 'ACME BUILDERS');
  assert.equal(exactBody.data.metadata.award_sha256, 'a'.repeat(64));
  assert.equal(conflict.status, 200);
  assert.equal(conflictBody.data.acquisition.match_state, 'conflict_review');
  assert.equal(conflictBody.data.quarantine[0].reference_id, '26ZERO01');
  assert.equal(conflictBody.data.quarantine[0].contract_no, '25O00113');
  assert.deepEqual(
    conflictBody.data.quarantine[0].candidates.map((item) => item.contract_id),
    ['25O00113', '26ZERO01'],
  );
  assert.equal(absentBody.data.acquisition.match_state, 'no_exact_row');
  assert.deepEqual(absentBody.data.award_matches, []);
  assert.deepEqual(absentBody.data.quarantine, []);

  for (const path of [
    '/api/v1/contracts/not-valid!',
    '/api/v1/contracts/%E0%A4%A',
    '/api/v1/contracts/24MISSING',
  ]) {
    const missing = await worker.fetch(request(path), environment(database));
    assert.equal(missing.status, 404, path);
  }
});

test('renders safe contract drill-downs and redirects the former delivery route', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const exact = await siteWorker.fetch(
    request('/contracts/25O00113/'),
    environment(database),
  );
  const conflict = await siteWorker.fetch(
    request('/contracts/26ZERO01/'),
    environment(database),
  );
  const former = await siteWorker.fetch(
    request('/records/delivery/25O00113/'),
    environment(database),
  );
  const absent = await siteWorker.fetch(
    request('/contracts/24NO0001/'),
    environment(database),
  );
  const exactDocument = await exact.text();
  const conflictDocument = await conflict.text();
  const absentDocument = await absent.text();

  assert.equal(exact.status, 200);
  assert.match(exactDocument, /Contract acquisition evidence/);
  assert.match(exactDocument, /ACME BUILDERS/);
  assert.match(exactDocument, /not an official notice of award/i);
  assert.match(exactDocument, /aaaaaaaaaaaaaaaa/);
  assert.equal(conflict.status, 200);
  assert.match(conflictDocument, /Conflicting exact identifiers/);
  assert.match(conflictDocument, /26ZERO01/);
  assert.match(conflictDocument, /25O00113/);
  assert.match(conflictDocument, /not a finding of wrongdoing/i);
  assert.equal(absent.status, 200);
  assert.match(absentDocument, /No exact secondary row located/);
  assert.match(absentDocument, /No exact row for this contract was accepted/);
  assert.equal(former.status, 301);
  assert.equal(former.headers.get('location'), 'https://busisi.org/contracts/25O00113/');
});

test('renders sparse contract acquisition fields without inventing evidence', () => {
  const document = deliveryRecordBody({
    record: {
      contract_id: '24SP0001',
      fiscal_year: 2024,
      description: 'Sparse source record',
      location: '',
      budget_centavos: 0,
      district_context: null,
    },
    related: [],
    budgets: [],
    candidates: [],
    projects: [],
    signals: [],
    contractors: [],
    acquisition: {
      match_state: 'future_review_state',
      accepted_match_rows: 1,
      quarantined_match_rows: 1,
    },
    award_matches: [{
      contract_id: '24SP0001',
      match_basis: 'title_exact',
      notice_title: '',
      award_title: '',
      awardee_name: 'PUBLIC BUILDER',
      organization_name: '',
      contract_amount_centavos: 0,
      award_date: '',
      award_status: '',
      row_sha256: '',
    }],
    quarantine: [{
      source_row_id: 'sparse-row',
      notice_title: '',
      reference_id: null,
      contract_no: null,
      award_title: null,
      row_sha256: '',
      candidates: [{ contract_id: '24SP0001' }],
    }],
    metadata: {},
  });

  assert.match(document, /future review state/);
  assert.match(document, /Organization not stated/);
  assert.match(document, /Delivery record unavailable/);
  assert.match(document, /Not available/);
  assert.match(document, /not a finding of wrongdoing/i);
});

test('bounds BetterGov source searches and scopes them to the record agency', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await worker.fetch(
    request('/api/v1/budgets?q=Routine+Maintenance'),
    environment(database),
  );
  const body = await response.json();
  const source = new URL(body.data[0].source_url);

  assert.equal(response.status, 200);
  assert.equal(source.pathname, '/api/v1/gaa/departments/18/programs');
  assert.equal(source.searchParams.get('agency_id'), '18-001');
  assert.equal(source.searchParams.get('year'), '2024');
  assert.ok(source.searchParams.get('q').length <= 40);
  assert.doesNotMatch(source.searchParams.get('q'), /\s$/);
});

test('filters unreviewed candidate links by supported signal', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await worker.fetch(
    request('/api/v1/candidates?signal=zero_budget'),
    environment(database),
  );
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.meta.total, 1);
  assert.equal(body.meta.review_scope, 'unreviewed_candidates');
  assert.equal(body.data[0].contract_id, '26ZERO01');
  assert.equal(body.data[0].review_status, 'candidate');
});

test('publishes reconciled FY2027 stage-change statistics and filters', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const stats = await worker.fetch(request('/api/v1/change-stats'), environment(database));
  const changes = await worker.fetch(
    request('/api/v1/changes?dataset=dpwh&change=increased&q=bridge'),
    environment(database),
  );
  const quarantined = await worker.fetch(
    request('/api/v1/changes?review=quarantine'),
    environment(database),
  );

  assert.deepEqual((await stats.json()).data, {
    record_count: 4,
    quarantine_count: 1,
    source_commit: 'a'.repeat(40),
  });
  const changeBody = await changes.json();
  assert.equal(changeBody.meta.total, 1);
  assert.equal(changeBody.meta.review_scope, 'provisional_stage_comparisons');
  assert.equal(changeBody.data[0].record_id, 'dpwh:1');
  assert.equal(changeBody.data[0].district_context.classification, 'single_district');
  assert.equal((await quarantined.json()).data[0].record_id, 'dpwh:3');
});

test('publishes reconciled appropriation heads and Congress institutions', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const summary = await worker.fetch(
    request('/api/v1/agency-budget-summary'), environment(database),
  );
  const increases = await worker.fetch(
    request('/api/v1/agency-budgets?level=all&direction=increase&sort=difference_desc'),
    environment(database),
  );
  const unavailable = await worker.fetch(
    request('/api/v1/agency-budgets?direction=unavailable'), environment(database),
  );

  const summaryBody = await summary.json();
  assert.equal(summaryBody.data.record_count, 3);
  assert.equal(summaryBody.data.house_bill_scope_centavos, 340000);
  const increaseBody = await increases.json();
  assert.equal(increaseBody.meta.total, 2);
  assert.equal(increaseBody.meta.review_scope, 'reconciled_appropriation_head_totals');
  assert.equal(increaseBody.data[0].record_id, 'congress:004');
  assert.deepEqual(increaseBody.data[0].house_pages, [19]);
  const unavailableBody = await unavailable.json();
  assert.equal(unavailableBody.data[0].record_id, 'head:AUTO');
  assert.equal(unavailableBody.data[0].house_centavos, null);
  assert.equal(
    unavailableBody.data[0].nep_reader_url,
    'https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027',
  );

  database.database.exec("UPDATE agency_budget_items SET house_pages_json = 'broken' WHERE record_id = 'head:AUTO'");
  const malformedPages = await worker.fetch(
    request('/api/v1/agency-budgets?q=AUTO&level=all&direction=unavailable&sort=nep_desc'),
    environment(database),
  );
  assert.deepEqual((await malformedPages.json()).data[0].house_pages, []);

  for (const query of [
    '?level=heads&direction=decrease&sort=difference_asc',
    '?level=heads&direction=unchanged&sort=house_desc',
    '?level=all&sort=nep_desc',
    '?level=all&sort=name_asc',
  ]) {
    const response = await worker.fetch(
      request(`/api/v1/agency-budgets${query}`), environment(database),
    );
    assert.equal(response.status, 200, query);
  }

  const firstPage = await worker.fetch(
    request('/api/v1/agency-budgets?level=all&limit=1'), environment(database),
  );
  const firstPageBody = await firstPage.json();
  const secondPage = await worker.fetch(
    request(`/api/v1/agency-budgets?level=all&limit=1&cursor=${firstPageBody.meta.next_cursor}`),
    environment(database),
  );
  assert.equal((await secondPage.json()).data.length, 1);
});

test('publishes sourced public-value indicators without a composite score', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const summary = await worker.fetch(
    request('/api/v1/public-value-summary'), environment(database),
  );
  const indicators = await worker.fetch(
    request('/api/v1/public-value-indicators'), environment(database),
  );

  const summaryBody = await summary.json();
  assert.equal(summary.status, 200);
  assert.equal(summaryBody.data.reading, 'mixed');
  assert.equal(summaryBody.data.revenue_coverage_bps, 7544);
  const indicatorBody = await indicators.json();
  assert.equal(indicators.status, 200);
  assert.equal(indicatorBody.meta.review_scope, 'official_dbm_fiscal_program');
  assert.equal(indicatorBody.data.length, 2);
  assert.equal(indicatorBody.data[0].indicator_id, 'real_gdp_growth');
  assert.equal(indicatorBody.data[0].lower_2027, 500);
  assert.doesNotMatch(JSON.stringify(indicatorBody), /score|corruption/i);
});

test('publishes ranked review candidates, concentrations and CSV evidence', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const summary = await worker.fetch(request('/api/v1/review-summary'), environment(database));
  const repeated = await worker.fetch(
    request('/api/v1/review-rankings?signal=repeat_family'),
    environment(database),
  );
  const similar = await worker.fetch(
    request('/api/v1/review-rankings?signal=similar_family'),
    environment(database),
  );
  const concentrations = await worker.fetch(
    request('/api/v1/review-concentrations?signal=house_only&dimension=region'),
    environment(database),
  );
  const largest = await worker.fetch(
    request('/api/v1/review-rankings?signal=house_only&dataset=hfep'),
    environment(database),
  );
  const removed = await worker.fetch(
    request('/api/v1/review-rankings?signal=nep_only'),
    environment(database),
  );
  const decreased = await worker.fetch(
    request('/api/v1/review-rankings?signal=decreased'),
    environment(database),
  );
  const csv = await worker.fetch(
    request('/api/v1/review.csv?signal=increased&dataset=dpwh'),
    environment(database),
  );

  const summaryBody = await summary.json();
  const repeatedBody = await repeated.json();
  const similarBody = await similar.json();
  const concentrationBody = await concentrations.json();
  assert.equal(summary.status, 200);
  assert.equal(summaryBody.data.quarantine_count, 1);
  assert.equal(
    summaryBody.data.changes.find((item) => item.change_type === 'house_only').record_count,
    2,
  );
  assert.equal(repeatedBody.meta.total, 2);
  assert.deepEqual(repeatedBody.data[0].prior_years, [2026]);
  assert.equal(repeatedBody.data[0].district_context.classification, 'shared_office');
  assert.equal(repeatedBody.data[0].district_context.districts.length, 2);
  assert.equal(repeatedBody.data[0].district_context.districts[1].representative_status, 'ambiguous');
  assert.equal(similarBody.meta.total, 2);
  assert.equal(similarBody.data[0].family_count, 2);
  assert.equal(concentrationBody.data[0].label, 'Region VII');
  assert.equal(concentrationBody.data[0].record_count, 1);
  assert.equal((await largest.json()).meta.total, 1);
  assert.equal((await removed.json()).meta.total, 0);
  assert.equal((await decreased.json()).meta.total, 0);
  assert.equal(csv.headers.get('content-type'), 'text/csv; charset=utf-8');
  assert.match(await csv.text(), /"increased","dpwh","Sample bridge"/);
});

test('publishes delivery-integrity signals and contractor rankings', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const summary = await worker.fetch(
    request('/api/v1/integrity-summary'), environment(database),
  );
  const conflicts = await worker.fetch(
    request('/api/v1/integrity-signals?classification=source_conflict&year=2025'),
    environment(database),
  );
  const sharedSignals = await worker.fetch(
    request('/api/v1/integrity-signals?signal=missing_coordinate'), environment(database),
  );
  const contractorsByCount = await worker.fetch(
    request('/api/v1/contractors?sort=count_desc'), environment(database),
  );
  const contractorsByBudget = await worker.fetch(
    request('/api/v1/contractors?sort=budget_desc'), environment(database),
  );
  const contractorSearch = await worker.fetch(
    request('/api/v1/contractors?q=67890&sort=name_asc'), environment(database),
  );
  const concentrations = await worker.fetch(
    request('/api/v1/contractor-concentrations?dimension=region&year=0'), environment(database),
  );
  const csv = await worker.fetch(
    request('/api/v1/integrity.csv?signal=missing_coordinate'), environment(database),
  );

  assert.deepEqual((await summary.json()).data, {
    source_records: 3,
    delivery_details: 2,
    integrity_signals: 3,
    contractors: 2,
    source_artifact_sha256: 'f'.repeat(64),
    concentrations: 2,
    pcab_records: 1,
    pcab_retrieved_on: '2026-11-03',
    pcab_source_sha256: 'e'.repeat(64),
    district_count: 3,
    district_offices: 2,
    district_source_commit: 'd'.repeat(40),
    district_source_built_at: '2026-10-26T08:46:14.383Z',
    district_source_retrieved_on: '2026-11-03',
    district_snapshot_sha256: '9'.repeat(64),
    district_coverage: [
      { classification: 'shared_office', count: 1 },
      { classification: 'single_district', count: 1 },
      { classification: 'unassigned', count: 1 },
    ],
    signals: [
      { code: 'coordinate_location_conflict', count: 1 },
      { code: 'missing_coordinate', count: 1 },
      { code: 'status_progress_conflict', count: 1 },
    ],
    pcab_statuses: [
      { status: 'current_regular', count: 1 },
      { status: 'not_found_current_regular', count: 1 },
    ],
  });
  const conflictBody = await conflicts.json();
  assert.equal(conflictBody.meta.total, 2);
  assert.equal(conflictBody.meta.review_scope, 'deterministic_source_review');
  assert.match(conflictBody.data[0].source_url, /api\.dpwh\.bettergov\.ph/);
  const singleConflict = conflictBody.data.find((record) => record.contract_id === '25A');
  assert.equal(singleConflict.district_context.classification, 'single_district');
  const sharedConflict = (await sharedSignals.json()).data[0];
  assert.equal(sharedConflict.district_context.classification, 'shared_office');
  assert.equal(sharedConflict.district_context.districts.length, 2);
  assert.equal((await contractorsByCount.json()).data[0].contractor_name, 'ACME BUILDERS');
  assert.equal((await contractorsByBudget.json()).data[0].total_budget_centavos, 30000000);
  assert.equal((await contractorSearch.json()).data[0].contractor_name, 'SECOND BUILDERS');
  const concentrationPayload = await concentrations.json();
  assert.equal(concentrationPayload.data[0].top_contractor_name, 'ACME BUILDERS');
  assert.equal(concentrationPayload.data[0].top_share_basis_points, 4000);
  assert.equal(csv.headers.get('content-type'), 'text/csv; charset=utf-8');
  assert.match(await csv.text(), /"missing_coordinate","coverage_gap","24B"/);
});

test('rejects unsupported stage-change filters', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  for (const path of [
    '/api/v1/changes?dataset=all-money',
    '/api/v1/changes?change=corruption',
    '/api/v1/changes?review=confirmed',
  ]) {
    const response = await worker.fetch(request(path), environment(database));
    assert.equal(response.status, 400, path);
  }
});

test('rejects invalid filters and cursors without leaking errors', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const invalidFilter = await worker.fetch(
    request('/api/v1/projects?status=accused'),
    environment(database),
  );
  const invalidCursor = await worker.fetch(
    request('/api/v1/projects?cursor=bad'),
    environment(database),
  );

  assert.equal(invalidFilter.status, 400);
  assert.deepEqual(await invalidFilter.json(), { detail: 'status is invalid' });
  assert.equal(invalidCursor.status, 400);
  assert.deepEqual(await invalidCursor.json(), { detail: 'cursor is invalid for this query' });
});

test('applies rate limiting and security headers', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const limited = await worker.fetch(request('/api/v1/projects'), environment(database, false));

  assert.equal(limited.status, 429);
  assert.equal(limited.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(limited.headers.get('x-frame-options'), 'DENY');
});

test('serves static fallback through the asset binding', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await worker.fetch(request('/watchlist/'), environment(database));

  assert.equal(response.status, 200);
  assert.match(await response.text(), /Busisi/);
  assert.match(response.headers.get('content-security-policy'), /connect-src 'self'/);
});

test('keeps cursor ordering stable for every public sort', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  for (const sort of ['appropriation_desc', 'difference_desc', 'year_desc', 'title_asc']) {
    const slugs = [];
    let cursor = null;
    do {
      const params = new URLSearchParams({ sort, limit: '1' });
      if (cursor) params.set('cursor', cursor);
      const response = await worker.fetch(
        request(`/api/v1/projects?${params.toString()}`),
        environment(database),
      );
      const body = await response.json();
      assert.equal(response.status, 200);
      slugs.push(...body.data.map((record) => record.slug));
      cursor = body.meta.next_cursor;
    } while (cursor);
    assert.equal(slugs.length, 6);
    assert.equal(new Set(slugs).size, 6);
  }
});

test('handles health, method, numeric and missing-record boundaries', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const withoutLimiter = environment(database);
  delete withoutLimiter.PUBLIC_API_RATE_LIMITER;
  const health = await worker.fetch(request('/healthz'), withoutLimiter);
  const method = await worker.fetch(
    request('/api/v1/projects', { method: 'POST' }),
    environment(database),
  );
  const numeric = await worker.fetch(
    request('/api/v1/projects?limit=none'),
    environment(database),
  );
  const missing = await worker.fetch(
    request('/api/v1/projects/not-present'),
    environment(database),
  );

  assert.deepEqual(await health.json(), { ok: true, service: 'busisi-publication', read_only: true });
  assert.equal(method.status, 405);
  assert.equal(numeric.status, 400);
  assert.equal(missing.status, 404);
});

test('publishes evidence drilldowns without collapsing records into findings', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const paths = [
    ['/records/budget/2025%3Apump/', /Official GAA appropriation record/],
    ['/contracts/25O00113/', /Official DPWH delivery record/],
    ['/records/candidate/2025%3Apump%3A25O00113/', /Unreviewed candidate comparison/],
    ['/records/change/dpwh%3A1/', /Provisional stage comparison/],
    ['/records/integrity/25A%3Astatus_progress_conflict/', /Review signal, not a finding/],
    ['/contractors/pcab%3A12345/', /Archived contractor activity/],
  ];

  for (const [path, expected] of paths) {
    const response = await siteWorker.fetch(request(path), environment(database));
    const document = await response.text();
    assert.equal(response.status, 200, path);
    assert.match(document, expected, path);
    assert.doesNotMatch(document, /(?:is|confirms|establishes) (?:fraud|corruption|wrongdoing)/i, path);
  }
});

test('expands reviewed project dossiers with phase history and evidence boundaries', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await siteWorker.fetch(
    request('/projects/corazon-2024-phase-1/'),
    environment(database),
  );
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Reviewed project evidence dossier/);
  assert.match(document, /Related reviewed phases/);
  assert.match(document, /corazon-2024-phase-2/);
  assert.match(document, /Release, obligation and payment/);
  assert.match(document, /Not available in the acquired records/);
  assert.match(document, /COA audit evidence/);
  assert.match(document, /No qualifying project-level COA evidence/);
});

test('publishes the COA audit desk without turning absence into clearance', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const summary = await worker.fetch(request('/api/v1/coa-summary'), environment(database));
  assert.equal(summary.status, 200);
  const payload = await summary.json();
  assert.equal(payload.data.metadata.report_count, '1');
  assert.equal(payload.data.metadata.project_matches, '1');
  assert.equal(payload.data.statuses.not_covered, 2);

  const reports = await worker.fetch(request('/api/v1/coa-reports'), environment(database));
  assert.equal(reports.status, 200);
  assert.equal((await reports.json()).data[0].acquisition_status, 'discovered');

  const desk = await siteWorker.fetch(request('/audit/'), environment(database));
  const document = await desk.text();
  assert.equal(desk.status, 200);
  assert.match(document, /COA audit evidence desk/);
  assert.match(document, /Absence is not clearance/);
  assert.match(document, /DPWH reviewed annual audit report/);

  const report = await siteWorker.fetch(
    request('/audit/reports/coa-report-1/'), environment(database),
  );
  assert.equal(report.status, 200);
  const reportDocument = await report.text();
  assert.match(reportDocument, /Agency accounts and operations/);
  assert.match(reportDocument, /Source copy not archived/);
  assert.doesNotMatch(reportDocument, /audit score|cleared the project/i);
});

test('publishes exact procurement evidence and preserves missing coverage', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  database.database.exec(`
    INSERT INTO projects VALUES
      ('pump-reviewed', 'pump-reviewed', 'San Andres Pumping Station', 2025, 'Manila',
       40000000000, 37679270658, 2320729342, '25O00113',
       'Construction of San Andres Pumping Station', 'Manila 1st DEO', 'GAA 2025',
       'high', 95, '["year_match"]', 'Reviewed identity link.',
       '["https://budget.example/pump"]', 'family:pump',
       'san andres pumping station', 'Reviewed link', 'reviewed', 1);
  `);

  const summary = await worker.fetch(
    request('/api/v1/procurement-summary'), environment(database),
  );
  assert.equal(summary.status, 200);
  const summaryPayload = await summary.json();
  assert.equal(summaryPayload.data.metadata.checked_projects, '2');
  assert.equal(summaryPayload.data.metadata.projects_with_evidence, '1');

  const records = await worker.fetch(
    request('/api/v1/procurement-records'), environment(database),
  );
  assert.equal(records.status, 200);
  const recordsPayload = await records.json();
  assert.equal(recordsPayload.data[0].contract_id, '25O00113');
  assert.equal(recordsPayload.data[0].events[2].stage, 'notice_of_award');
  assert.equal(recordsPayload.data[0].artifact_sha256, '6'.repeat(64));

  const desk = await siteWorker.fetch(request('/procurement/'), environment(database));
  const document = await desk.text();
  assert.equal(desk.status, 200);
  assert.match(document, /Procurement evidence desk/);
  assert.match(document, /1 of 2 reviewed dossiers/);
  assert.match(document, /PhilGEPS bid notice 123/);
  assert.match(document, /Evidence gap, not a clean bill/);

  const dossier = await siteWorker.fetch(
    request('/projects/pump-reviewed/'), environment(database),
  );
  const dossierDocument = await dossier.text();
  assert.match(dossierDocument, /Procurement timeline/);
  assert.match(dossierDocument, /Notice of award/);
  assert.match(dossierDocument, /Difference below ABC/);
  assert.match(dossierDocument, /₱23,207,293\.42/);
  assert.match(dossierDocument, /Archived source SHA-256/);

  const missing = await getProjectProcurementEvidence(database, '26ZERO01');
  assert.equal(missing.coverage.status, 'not_located');
  assert.deepEqual(missing.records, []);
});

test('publishes contract outcome cross-checks without inventing award or payment evidence', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  database.database.exec(`
    INSERT INTO projects VALUES
      ('pump-reviewed', 'pump-reviewed', 'San Andres Pumping Station', 2025, 'Manila',
       40000000000, 37679270658, 2320729342, '25O00113',
       'Construction of San Andres Pumping Station', 'Manila 1st DEO', 'GAA 2025',
       'high', 95, '["year_match"]', 'Reviewed identity link.',
       '["https://budget.example/pump"]', 'family:pump',
       'san andres pumping station', 'Reviewed link', 'reviewed', 1);
    UPDATE delivery_project_details
    SET progress = '100.0', status = 'On-Going'
    WHERE contract_id = '25O00113';
  `);

  const response = await worker.fetch(
    request('/api/v1/contract-outcomes'), environment(database),
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  const outcome = payload.data.find((item) => item.contract_id === '25O00113');
  assert.ok(outcome);
  assert.equal(outcome.amount_check.state, 'consistent');
  assert.equal(outcome.awardee_evidence.state, 'gap');
  assert.equal(outcome.payment_evidence.state, 'gap');
  assert.ok(outcome.questions.some((item) => item.code === 'progress_status_conflict'));

  const desk = await siteWorker.fetch(request('/procurement/'), environment(database));
  const deskDocument = await desk.text();
  assert.match(deskDocument, /Contract outcome cross-checks/);
  assert.match(deskDocument, /Awardee not established by acquired procurement evidence/);
  assert.match(deskDocument, /Questions, not findings/);

  const dossier = await siteWorker.fetch(
    request('/projects/pump-reviewed/'), environment(database),
  );
  const dossierDocument = await dossier.text();
  assert.match(dossierDocument, /Contract outcome pack/);
  assert.match(dossierDocument, /Delivery record contractor/);
  assert.match(dossierDocument, /Payment evidence/);
  assert.match(dossierDocument, /No project-specific payment record acquired/);
});

test('publishes complete contract evidence checklists and a bounded retry queue', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const response = await worker.fetch(
    request('/api/v1/contract-evidence'), environment(database),
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.meta.total, 27);
  assert.equal(payload.meta.contracts, 3);
  assert.equal(payload.meta.retry_items, 3);
  assert.deepEqual(payload.meta.statuses, {
    blocked: 3,
    not_located: 20,
    secondary: 3,
    verified_archived: 1,
  });
  const notice = payload.data.find((item) => (
    item.contract_id === '24HI0148' && item.stage === 'notice_to_proceed'
  ));
  assert.equal(notice.status, 'not_located');
  assert.equal(notice.reported_date, '2024-09-05');
  assert.equal(notice.date_kind, 'actual');
  const blocked = payload.data.find((item) => (
    item.contract_id === '24HI0148' && item.stage === 'procurement_monitoring_report'
  ));
  assert.equal(blocked.http_status, 403);
  assert.equal(blocked.retry_eligible, true);

  const projectEvidence = await getProjectContractEvidence(database, '24HI0148');
  assert.equal(projectEvidence.length, 9);
  assert.equal(projectEvidence[0].stage, 'procurement_plan');

  const desk = await siteWorker.fetch(request('/procurement/'), environment(database));
  const deskDocument = await desk.text();
  assert.match(deskDocument, /Contract evidence acquisition ledger/);
  assert.match(deskDocument, /3 acquisition checks queued/);
  assert.match(deskDocument, /Official source indexed, archive blocked/);
  assert.match(deskDocument, /Secondary mirror evidence/);

  const dossier = await siteWorker.fetch(
    request('/projects/corazon-2024-phase-1/'), environment(database),
  );
  const dossierDocument = await dossier.text();
  assert.match(dossierDocument, /Contract evidence checklist/);
  assert.match(dossierDocument, /Reported date, document missing/);
  assert.match(dossierDocument, /No project-specific voucher/);
  assert.match(dossierDocument, /HTTP 403/);
  assert.match(dossierDocument, /Try official source \(last returned HTTP 403\)/);
  assert.match(dossierDocument, /Open date-reporting source/);
  assert.match(dossierDocument, /Open secondary source/);
});

test('publishes reconciled full-universe acquisition coverage', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const coverage = await getAcquisitionCoverage(database);
  assert.equal(coverage.summary.contract_count, 56887);
  assert.equal(coverage.summary.examined_contracts, 56887);
  assert.equal(coverage.summary.accepted_match_rows, 62129);
  assert.equal(coverage.summary.quarantined_source_rows, 83);
  assert.equal(coverage.summary.lifecycle_task_count, 511983);
  assert.deepEqual(coverage.states, {
    conflict_review: 161,
    multiple_exact_rows: 2077,
    no_exact_row: 9655,
    structured_exact: 38110,
    title_exact: 6884,
  });
  assert.equal(coverage.queue.retry, 3);
  assert.equal(coverage.queue.pending, 464727);
  assert.equal(coverage.years.reduce((total, item) => total + item.total_contracts, 0), 56887);

  const response = await worker.fetch(
    request('/api/v1/acquisition-coverage'), environment(database),
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.meta.review_scope, 'full_contract_universe_acquisition');
  assert.equal(payload.data.summary.contract_count, 56887);

  const page = await siteWorker.fetch(request('/procurement/'), environment(database));
  const document = await page.text();
  assert.match(document, /Full-universe acquisition coverage/);
  assert.match(document, /56,887 of 56,887 contracts examined/);
  assert.match(document, /47,071 contracts with usable exact secondary rows/);
  assert.match(document, /83 conflicting source rows quarantined/);
  assert.match(document, /Coverage is not official proof/);
});

test('classifies contract amount, sequence, schedule and completion questions deterministically', () => {
  const outcome = buildContractOutcome({
    coverage: { case_id: 'case', contract_id: '24TEST', fiscal_year: 2024 },
    procurementRecords: [{
      project_title: 'Test project', procurement_status: 'Completed',
      contract_cost_centavos: 9900,
      events: [
        { stage: 'advertisement', event_date: '2024-01-01', date_kind: 'planned' },
        { stage: 'advertisement', event_date: '2024-01-03', date_kind: 'actual' },
        { stage: 'contract_signing', event_date: '2024-02-02', date_kind: 'actual' },
        { stage: 'notice_to_proceed', event_date: '2024-02-01', date_kind: 'actual' },
      ],
    }],
    delivery: {
      contract_id: '24TEST', fiscal_year: 2024, description: 'Test project',
      budget_centavos: 10000, contractor_name: 'TEST BUILDER', status: 'On-Going',
      progress: '100.00', start_date: '2024-01-31', completion_date: '',
    },
  });
  assert.equal(outcome.amount_check.state, 'question');
  assert.equal(outcome.amount_check.difference_centavos, 100);
  assert.deepEqual(outcome.questions.map((item) => item.code), [
    'contract_amount_mismatch',
    'completion_status_conflict',
    'progress_status_conflict',
    'completion_without_inspection_evidence',
    'notice_to_proceed_before_contract',
    'implementation_before_notice_to_proceed',
    'schedule_variance:advertisement',
  ]);
});

test('keeps absent and available contract outcome evidence in separate states', () => {
  const absent = buildContractOutcome({
    coverage: null,
    procurementRecords: null,
    delivery: null,
  });
  assert.equal(absent.contract_id, null);
  assert.equal(absent.amount_check.state, 'gap');
  assert.equal(absent.award_evidence.state, 'gap');
  assert.equal(absent.awardee_evidence.detail, 'No acquired award artifact names the awardee.');
  assert.deepEqual(absent.questions, []);

  const inspected = buildContractOutcome({
    coverage: { case_id: 'case', contract_id: '25TEST', fiscal_year: 2025 },
    procurementRecords: [{
      project_title: 'Inspected project', procurement_status: 'Open',
      contract_cost_centavos: null,
      events: [
        { stage: 'notice_of_award', event_date: '2025-01-01', date_kind: 'actual' },
        { stage: 'contract_signing', event_date: '2025-01-02', date_kind: 'actual' },
        { stage: 'notice_to_proceed', event_date: '2025-01-03', date_kind: 'actual' },
        { stage: 'inspection_acceptance', event_date: '2025-03-03', date_kind: 'actual' },
      ],
    }],
    delivery: {
      contract_id: '25TEST', fiscal_year: 2025, budget_centavos: 100,
      contractor_name: '', status: 'Completed', progress: '99',
      start_date: '2025-01-03', completion_date: '2025-03-01',
    },
  });
  assert.equal(inspected.title, 'Inspected project');
  assert.equal(inspected.award_evidence.state, 'partial');
  assert.equal(inspected.inspection_evidence.state, 'available');
  assert.equal(inspected.amount_check.delivery_centavos, 100);
  assert.deepEqual(inspected.questions, []);
});

test('uses a versioned award mirror as secondary evidence without overstating verification', () => {
  const outcome = buildContractOutcome({
    coverage: { case_id: 'case', contract_id: '25TEST', fiscal_year: 2025 },
    procurementRecords: [],
    delivery: {
      contract_id: '25TEST', fiscal_year: 2025, description: 'Test project',
      budget_centavos: 10000, contractor_name: 'TEST BUILDER (12345)', status: 'On-Going',
      progress: '20', start_date: '2025-02-01', completion_date: '',
    },
    awardMirror: {
      awardee_name: 'Test Builder', contract_amount_centavos: 10000,
      source_row_id: 'row', source_revision: 'revision', row_sha256: 'hash',
    },
  });

  assert.equal(outcome.amount_check.state, 'consistent');
  assert.equal(outcome.amount_check.source_label, 'Secondary PhilGEPS mirror award amount');
  assert.equal(outcome.award_evidence.state, 'secondary');
  assert.equal(outcome.awardee_evidence.state, 'secondary');
  assert.equal(outcome.awardee_check.state, 'consistent_secondary');
  assert.deepEqual(outcome.questions, []);

  const mismatch = buildContractOutcome({
    coverage: { case_id: 'case', contract_id: '25TEST', fiscal_year: 2025 },
    procurementRecords: [],
    delivery: {
      contract_id: '25TEST', fiscal_year: 2025, description: 'Test project',
      budget_centavos: 10000, contractor_name: 'OTHER BUILDER', status: 'On-Going',
      progress: '20', start_date: '', completion_date: '',
    },
    awardMirror: {
      awardee_name: 'Test Builder', contract_amount_centavos: 9900,
      source_row_id: 'row', source_revision: 'revision', row_sha256: 'hash',
    },
  });
  assert.equal(mismatch.awardee_check.state, 'question');
  assert.deepEqual(mismatch.questions.map((item) => item.code), [
    'contract_amount_mismatch', 'awardee_contractor_name_mismatch',
  ]);
});

test('fails closed when contract outcome event arrays are malformed', async () => {
  const database = {
    prepare: (query) => ({
      all: async () => {
        if (query.includes('FROM procurement_project_coverage\n')) {
          return { results: [{
            case_id: 'case', contract_id: '25TEST', fiscal_year: 2025,
            status: 'exact_evidence', record_count: 2,
          }] };
        }
        if (query.includes('SELECT r.*')) {
          return { results: [{
            evidence_id: 'one', contract_id: '25TEST', project_title: 'Test',
            procurement_status: 'Awarded', contract_cost_centavos: null,
            events_json: '{broken',
          }, {
            evidence_id: 'two', contract_id: '25TEST', project_title: 'Test',
            procurement_status: 'Open', contract_cost_centavos: null,
            events_json: '{}',
          }] };
        }
        if (query.includes('contract_award_mirror_records')) return { results: [] };
        return { results: [{
          contract_id: '25TEST', fiscal_year: 2025, description: 'Test',
          budget_centavos: 100, status: 'On-Going', progress: '20',
          contractor_name: '', start_date: '', completion_date: '',
        }] };
      },
    }),
  };
  const outcomes = await queryContractOutcomes(database);
  const outcome = outcomes.find((item) => item.contract_id === '25TEST');
  assert.ok(outcome);
  assert.equal(outcome.award_evidence.state, 'partial');
  assert.equal(outcome.inspection_evidence.state, 'gap');
});

test('fails closed for malformed procurement record arrays', async () => {
  const database = {
    prepare: (query) => ({
      bind: () => ({
        first: async () => ({ contract_id: '24TEST', status: 'exact_evidence' }),
        all: async () => ({ results: query.includes('procurement_records') ? [{
          evidence_id: 'record', events_json: '{broken', observers_json: '{}',
        }] : [] }),
      }),
    }),
  };
  const evidence = await getProjectProcurementEvidence(database, '24TEST');
  assert.deepEqual(evidence.records[0].events, []);
  assert.deepEqual(evidence.records[0].observers, []);
});

test('renders procurement desk counts without unsafe source URLs', () => {
  const document = procurementDeskBody({
    summary: {
      metadata: { checked_projects: '1', projects_with_evidence: '1', archived_sources: '1' },
      statuses: { exact_evidence: 1 },
    },
    sources: [{
      source_id: 'source', title: 'Official source', publisher: 'Agency',
      document_type: 'bid_notice', fiscal_year: 2025, source_url: 'javascript:alert(1)',
      acquisition_status: 'verified_archived', artifact_sha256: 'a'.repeat(64),
      evidence_note: 'Archived official source.',
    }, {
      source_id: 'discovered', title: 'Discovered source', publisher: 'Agency',
      document_type: 'annual_procurement_plan', fiscal_year: 2025, source_url: 'not a url',
      acquisition_status: 'discovered', artifact_sha256: null,
      evidence_note: 'Catalogue record only.',
    }],
    coverage: [
      { case_id: 'a', contract_id: 'A', fiscal_year: 2025, status: 'partial_evidence', review_note: 'Partial.', reviewed_at: '2026-11-03' },
      { case_id: 'b', contract_id: 'B', fiscal_year: 2025, status: 'current_year_not_yet_located', review_note: 'Pending.', reviewed_at: '2026-11-03' },
      { case_id: 'c', contract_id: 'C', fiscal_year: 2025, status: 'unexpected_status', review_note: 'Unknown.', reviewed_at: '2026-11-03' },
    ],
  });
  assert.match(document, /1 of 1 reviewed dossiers/);
  assert.match(document, /Source archived and verified/);
  assert.match(document, /discovered/);
  assert.doesNotMatch(document, /javascript:/);
});

test('renders archived, unavailable and incomplete COA report presentation states', () => {
  const archived = {
    report_id: 'archived-report', title: 'Archived report', report_type: 'performance_audit',
    audited_entity: 'Public agency', fiscal_year: 2024, publication_date: null,
    source_url: 'https://www.coa.gov.ph/report', landing_url: 'https://www.coa.gov.ph/reports/',
    acquisition_status: 'verified_archived', artifact_sha256: 'a'.repeat(64), page_count: 12,
    scope_note: 'Reviewed program scope.', evidence_note: 'Official bytes archived.',
  };
  const unavailable = { ...archived, report_id: 'unavailable-report', title: 'Unavailable report',
    acquisition_status: 'unavailable', artifact_sha256: null, page_count: null };
  const desk = coaDeskBody({
    summary: { metadata: {}, statuses: {}, catalogs: [{
      catalog_id: 'catalog', title: 'Official catalogue', source_url: 'https://www.coa.gov.ph/',
      checked_status: 'reachable', evidence_note: 'Checked.',
    }] },
    reports: [archived, unavailable],
  });
  const archivedPage = coaReportBody(archived);
  const unavailablePage = coaReportBody(unavailable);

  assert.match(desk, /Source copy archived and verified/);
  assert.match(desk, /Source unavailable/);
  assert.match(desk, /0 dossiers checked/);
  assert.match(archivedPage, /Source copy archived/);
  assert.match(archivedPage, new RegExp('a{64}'));
  assert.match(archivedPage, /Not stated/);
  assert.match(unavailablePage, /Source copy not archived/);
});

test('fails closed for malformed COA match-basis metadata', async () => {
  const database = (matchBasis) => ({
    prepare: () => ({
      bind: () => ({ first: async () => ({
        contract_id: '24TEST', status: 'candidate_observation_match',
        match_basis_json: matchBasis,
      }) }),
    }),
  });

  assert.deepEqual((await getProjectCoaEvidence(database('{}'), '24TEST')).match_basis, []);
  assert.deepEqual((await getProjectCoaEvidence(database('{broken'), '24TEST')).match_basis, []);
});

test('rejects malformed and missing evidence record identifiers', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  for (const path of [
    '/records/budget/%E0%A4%A/',
    '/records/delivery/not-present/',
    `/records/change/${'x'.repeat(513)}/`,
    '/contractors/not-present/',
  ]) {
    const response = await siteWorker.fetch(request(path), environment(database));
    assert.equal(response.status, 404, path);
    assert.match(await response.text(), /noindex, nofollow/, path);
  }
});

test('renders unavailable, quarantined and alternate evidence states', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const cases = [
    ['/records/budget/2026%3Abridge/', /No candidate delivery link/],
    ['/contracts/26ZERO01/', /No exact office attribution available/],
    ['/records/change/hfep%3A2/', /NEP page not available/],
    ['/records/change/dpwh%3A3/', /No other FY2027 comparison row/],
    ['/records/integrity/24B%3Amissing_coordinate/', /Quezon, 1st District/],
    ['/records/integrity/25C%3Acoordinate_location_conflict/', /No exact office attribution available/],
    ['/contractors/pcab%3A67890/', /not found current regular/],
    ['/projects/agoncillo-2023/', /No other reviewed dossier/],
    ['/projects/corazon-2026-completion/', /Quarantined project candidate/],
  ];

  for (const [path, expected] of cases) {
    const response = await siteWorker.fetch(request(path), environment(database));
    assert.equal(response.status, 200, path);
    assert.match(await response.text(), expected, path);
  }
});

test('renders enriched record relationships and tolerates malformed candidate metadata', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  database.database.exec(`
    INSERT INTO delivery_items VALUES
      ('25PUMP02', 2025, 'San Andres Pumping Station Phase II', 25000000000,
       'Manila 1st DEO, NCR', 'GAA 2025', 'family:pump', 'san andres pumping station', '${'a'.repeat(64)}');
    INSERT INTO integrity_signal_items VALUES
      ('25O00113:missing_coordinate', '25O00113', 2025, 'missing_coordinate', 'coverage_gap',
       'Coordinate not available', 'Construction of San Andres Pumping Station', 'ACME BUILDERS',
       '12345', 37679270658, 'Completed', '100', 'Manila 1st DEO', 'NCR', '', '',
       'No usable coordinate.', 'Missing coordinates do not indicate a missing project.', '${'f'.repeat(64)}'),
      ('25O00113:completed_without_satellite_image', '25O00113', 2025,
       'completed_without_satellite_image', 'coverage_gap', 'Completed without satellite image',
       'Construction of San Andres Pumping Station', 'ACME BUILDERS', '12345', 37679270658,
       'Completed', '100', 'Manila 1st DEO', 'NCR', '14.5', '120.9',
       'No archived image reference.', 'Image coverage is incomplete.', '${'f'.repeat(64)}');
    INSERT INTO projects VALUES
      ('pump-reviewed', 'pump-reviewed', 'San Andres Pumping Station', 2025, 'Manila',
       40000000000, 37679270658, 2320729342, '25O00113',
       'Construction of San Andres Pumping Station', 'Manila 1st DEO', 'GAA 2025',
       'high', 95, '["year_match"]', 'Reviewed identity link.',
       '["http://unsafe.example","https://budget.example/pump"]', 'family:pump',
       'san andres pumping station', 'Reviewed link', 'reviewed', 1);
    INSERT INTO candidate_links VALUES
      ('missing-delivery', 2025, '18-001|pump', 'NOT-PRESENT', 'candidate', 40, '{broken',
       'Construction of San Andres Pumping Station', 'Missing delivery row', 40000000000,
       0, 40000000000, 'https://budget.example/pump', '', 'candidate');
    INSERT INTO stage_change_items VALUES
      ('dpwh:pump-2027', 2027, 'dpwh', 'San Andres Pumping Station Expansion',
       'Flood Management', 'Pumping Stations', 'NCR', 'Manila 1st DEO', 'house_only',
       'In the House bill only', 'candidate', 0, 1, 0, 5000000000, 5000000000,
       'https://budget.example/pump-2027', '', 'https://budget.example/house.pdf#page=9',
       NULL, 9, '${'a'.repeat(40)}', '${'c'.repeat(64)}', 'san andres pumping station');
  `);

  const paths = [
    ['/contracts/25O00113/', /ACME BUILDERS/],
    ['/records/integrity/25O00113%3Amissing_coordinate/', /1 additional signal/],
    ['/records/candidate/2025%3Apump%3A25O00113/', /San Andres Pumping Station/],
    ['/records/candidate/missing-delivery/', /Matching delivery row is not available/],
    ['/projects/pump-reviewed/', /Reader evidence links/],
  ];
  for (const [path, expected] of paths) {
    const response = await siteWorker.fetch(request(path), environment(database));
    assert.equal(response.status, 200, path);
    const document = await response.text();
    assert.match(document, expected, path);
    assert.doesNotMatch(document, /unsafe\.example/, path);
  }

  database.database.exec("UPDATE candidate_links SET signals_json = '{}' WHERE candidate_id = 'missing-delivery'");
  const objectSignals = await siteWorker.fetch(
    request('/records/candidate/missing-delivery/'),
    environment(database),
  );
  assert.equal(objectSignals.status, 200);

  const project = await siteWorker.fetch(request('/projects/pump-reviewed/'), environment(database));
  const dossier = await project.text();
  for (const expected of [
    'Flood Control', 'On-Going', '62.5%', '2025-01-15', '2025-12-20',
    '14.5995, 120.9842', 'ACME BUILDERS', 'Evidence by public-money stage',
    'Identifiers and archived source fingerprints', 'San Andres Pumping Station Expansion',
    'Reviewed project observation match', 'pages 12–13', 'Verify delivery records',
  ]) assert.match(dossier, new RegExp(expected.replace('.', '\\.')));
  assert.doesNotMatch(dossier, /api\.dpwh\.bettergov\.ph|budget\.bettergov\.ph\/api/);

  database.database.exec(`
    UPDATE coa_project_coverage SET status = 'program_audit_available',
      match_confidence = 'none', page_start = NULL, page_end = NULL,
      observation_summary = '', recommendation_summary = '', management_response = ''
    WHERE contract_id = '25O00113';
  `);
  const contextual = await siteWorker.fetch(
    request('/projects/pump-reviewed/'), environment(database),
  );
  assert.match(await contextual.text(), /program audit available/);
});
