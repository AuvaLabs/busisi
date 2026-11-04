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
import { getProjectImageEvidence } from '../src/project-image-query.js';
import { getAcquisitionCoverage } from '../src/acquisition-coverage-query.js';
import { getCoverageStatus } from '../src/coverage-status-query.js';
import { coverageStatusBody } from '../src/coverage-status-content.js';
import { getSourceMonitorStatus } from '../src/source-monitor-query.js';
import { buildQuestionCatalogue } from '../src/questions-query.js';
import { facilityBody } from '../src/facility-content.js';
import { publicServicesBody } from '../src/public-services-content.js';
import { watchBody } from '../src/ecosystem-content.js';
import { getAlertFeed } from '../src/alerts-query.js';
import { alertsRss } from '../src/alerts-feed.js';
import { getFacility } from '../src/facility-query.js';
import {
  getPublicServicesSummary,
  parsePublicServicesQuery,
  queryPublicServices,
} from '../src/public-services-query.js';
import { parseContractIntelligenceQuery } from '../src/contract-intelligence-query.js';
import { parseContractorProjectQuery } from '../src/contractor-activity-query.js';
import { parsePlaceQuery, queryPlaces } from '../src/place-query.js';
import { parseAgencyQuery } from '../src/agency-budget-query.js';
import { parseAllotmentReleaseQuery } from '../src/allotment-release-query.js';
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
const contractIntelligenceMigrationPath = fileURLToPath(
  new URL('../migrations/0019_contract_intelligence.sql', import.meta.url),
);
const allotmentReleaseMigrationPath = fileURLToPath(
  new URL('../migrations/0020_allotment_releases.sql', import.meta.url),
);
const projectImageMigrationPath = fileURLToPath(
  new URL('../migrations/0021_project_images.sql', import.meta.url),
);
const coverageAutomationMigrationPath = fileURLToPath(
  new URL('../migrations/0022_coverage_automation.sql', import.meta.url),
);
const sourceMonitorMigrationPath = fileURLToPath(
  new URL('../migrations/0023_source_monitor_status.sql', import.meta.url),
);
const contractorAssociationMigrationPath = fileURLToPath(
  new URL('../migrations/0024_contractor_project_associations.sql', import.meta.url),
);
const facilityIdentityMigrationPath = fileURLToPath(
  new URL('../migrations/0026_facility_identity.sql', import.meta.url),
);
const facilityRegistryDetailsMigrationPath = fileURLToPath(
  new URL('../migrations/0027_facility_registry_details.sql', import.meta.url),
);
const facilityRegistryStatusMigrationPath = fileURLToPath(
  new URL('../migrations/0028_facility_registry_status.sql', import.meta.url),
);
const contractorAccountabilityMigrationPath = fileURLToPath(
  new URL('../migrations/0029_contractor_accountability.sql', import.meta.url),
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
    this.preparedSql = [];
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
    this.database.exec(readFileSync(contractIntelligenceMigrationPath, 'utf8'));
    this.database.exec(readFileSync(allotmentReleaseMigrationPath, 'utf8'));
    this.database.exec(readFileSync(projectImageMigrationPath, 'utf8'));
    this.database.exec(readFileSync(coverageAutomationMigrationPath, 'utf8'));
    this.database.exec(readFileSync(sourceMonitorMigrationPath, 'utf8'));
    this.database.exec(readFileSync(contractorAssociationMigrationPath, 'utf8'));
    this.database.exec(readFileSync(facilityIdentityMigrationPath, 'utf8'));
    this.database.exec(readFileSync(facilityRegistryDetailsMigrationPath, 'utf8'));
    this.database.exec(readFileSync(facilityRegistryStatusMigrationPath, 'utf8'));
    this.database.exec(readFileSync(contractorAccountabilityMigrationPath, 'utf8'));
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
        ('contractor_associations', '1'),
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
      INSERT INTO contractor_project_associations VALUES
        ('pcab:12345', '25O00113', 1, 1, 'sole');
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
      INSERT INTO allotment_release_metadata VALUES
        ('fiscal_year', '2026'), ('as_of_date', '2026-09-30'), ('record_count', '3'),
        ('department_count', '1'), ('attached_agency_count', '1'),
        ('special_purpose_fund_count', '1'),
        ('current_gaa_adjusted_centavos', '439104496900000'),
        ('current_gaa_releases_centavos', '407222774000000'),
        ('current_gaa_balance_centavos', '31881722900000'),
        ('total_program_centavos', '679316200000000'),
        ('total_releases_centavos', '653295146600000'),
        ('total_balance_centavos', '26021053400000'),
        ('source_sha256', '${'a'.repeat(64)}'),
        ('source_url', 'https://www.dbm.gov.ph/releases.xlsx');
      INSERT INTO allotment_release_items VALUES
        ('release:dpwh', 2026, '2026-09-30', 35, 'department', NULL, 'DPWH',
         'Department of Public Works and Highways', 100000, 1000, 101000, 99000, 2000,
         9802, 'https://www.dbm.gov.ph/releases.xlsx', '${'a'.repeat(64)}',
         'Official DBM workbook value.'),
        ('release:oeos:amlc', 2026, '2026-09-30', 56, 'attached_agency',
         'release:oeos', 'AMLC', 'AMLC', 5000, 0, 5000, 2500, 2500, 5000,
         'https://www.dbm.gov.ph/releases.xlsx', '${'a'.repeat(64)}',
         'Official DBM workbook value.'),
        ('release:spf:test', 2026, '2026-09-30', 102, 'special_purpose_fund', NULL,
         'Test Fund', 'Test Fund', 10000, 0, 10000, 11000, -1000, 11000,
         'https://www.dbm.gov.ph/releases.xlsx', '${'a'.repeat(64)}',
         'Official DBM workbook value.');
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
      INSERT INTO project_image_coverage VALUES
        ('25O00113', 1, 1, 1, 'verified_exact', '${'3'.repeat(64)}', '${'4'.repeat(64)}',
         '2026-11-03T12:00:00+00:00', 'Project detail and image endpoint counts reconcile exactly.'),
        ('26ZERO01', 1, 2, 1, 'count_conflict', '${'5'.repeat(64)}', '${'6'.repeat(64)}',
         '2026-11-03T12:00:00+00:00', 'Source image summary and image endpoint do not reconcile.'),
        ('24NO0001', 0, 0, 0, 'no_images', '${'7'.repeat(64)}', '${'8'.repeat(64)}',
         '2026-11-03T12:00:00+00:00', 'Both source representations report no project images.');
      INSERT INTO project_images VALUES
        ('${'9'.repeat(64)}', '25O00113', 'PUMP-COMPONENT-1', 1, 'progress', 'On-Going',
         '2026-10-31 09:15:00', 'FY2025', 14.5995, 120.9842,
         'within_broad_philippine_bounds',
         'https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2025/pump/photo-1.jpg',
         'https://s3.transparency.dpwh.gov.ph/cdn-cgi/image/width=400/https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2025/pump/photo-1.jpg',
         '${'a'.repeat(64)}', 'image/jpeg', 128, 600, 400,
         'project-images/25O00113/${'a'.repeat(64)}.jpg', 'verified');
      INSERT INTO coverage_releases VALUES
        ('${'d'.repeat(64)}', '2026-11-04T01:00:00+00:00', '${'e'.repeat(64)}',
         36748, 6, 4, 1, 1, 3, 2, 36737, 5, 13);
      INSERT INTO source_monitor_status VALUES
        (1, '2026-11-04T01:30:00+00:00', 'unchanged', '[]',
         '[{"source":"Commission on Audit report catalogues","effect":"Official source blocks unattended acquisition."}]',
         '${'f'.repeat(64)}');
    `);
  }

  prepare(sql) {
    this.preparedSql.push(sql);
    return new LocalStatement(this.database.prepare(sql));
  }

  close() {
    this.database.close();
  }
}

const environment = (database, allowed = true) => ({
  DB: database,
  ASSETS: { fetch: async () => new Response('<h1>Busisi</h1>', { headers: { 'Content-Type': 'text/html' } }) },
  PROJECT_MEDIA: {
    get: async (key) => key === `project-images/25O00113/${'a'.repeat(64)}.jpg`
      ? { body: new Uint8Array([0xff, 0xd8, 0xff, 0xd9]) }
      : null,
  },
  PUBLIC_API_RATE_LIMITER: { limit: async () => ({ success: allowed }) },
});

const request = (path, init) => new Request(`https://busisi.test${path}`, init);

const insertJointContract = (database) => database.database.exec(`
  INSERT INTO delivery_items VALUES
    ('25JOINT1', 2025, 'Construction of Joint Public Market', 5000000000,
     'Manila 1st DEO, NCR', 'GAA 2025', 'family:joint-market',
     'construction joint public market', '${'b'.repeat(64)}');
  INSERT INTO delivery_project_details VALUES
    ('25JOINT1', 2025, 'Buildings and Facilities', 'On-Going', '55',
     'WRC BUILDERS (11111) / EGB BUILDERS (22222)',
     '[{"contractor_key":"pcab:11111","contractor_name":"WRC BUILDERS","pcab_id":"11111"},{"contractor_key":"pcab:22222","contractor_name":"EGB BUILDERS","pcab_id":"22222"}]',
     '2025-01-01', '2025-12-31', 'Manila 1st DEO', 'NCR', '', '', 0,
     '${'b'.repeat(64)}');
  INSERT INTO contractor_rankings VALUES
    ('pcab:11111', 'WRC BUILDERS', '11111', 1, 5000000000, 0, 1, 0,
     2025, 2025, 1, 'current_regular', 'WRC BUILDERS', 'A', '2027-01-01', 1,
     '${'e'.repeat(64)}'),
    ('pcab:22222', 'EGB BUILDERS', '22222', 1, 5000000000, 0, 1, 0,
     2025, 2025, 1, 'current_regular', 'EGB BUILDERS', 'AAAA', '2027-01-01', 1,
     '${'e'.repeat(64)}');
  INSERT INTO contractor_project_associations VALUES
    ('pcab:11111', '25JOINT1', 1, 2, 'joint'),
    ('pcab:22222', '25JOINT1', 2, 2, 'joint');
  INSERT INTO integrity_signal_items VALUES
    ('25JOINT1:missing_coordinate', '25JOINT1', 2025, 'missing_coordinate',
     'coverage_gap', 'Coordinate not available', 'Construction of Joint Public Market',
     'WRC BUILDERS (11111) / EGB BUILDERS (22222)', '11111,22222', 5000000000,
     'On-Going', '55', 'Manila 1st DEO', 'NCR', '', '', 'No usable coordinate.',
     'Missing coordinates do not indicate a missing project.', '${'f'.repeat(64)}');
  INSERT INTO contract_acquisition_details VALUES
    ('25JOINT1', 2025, 'valid', 'aligned', 'no_exact_row', 0, 0);
`);

test('publishes a bounded evidence update feed for people and machines', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  database.database.exec("INSERT INTO integrity_metadata VALUES ('source_as_of', '2026-01-22')");

  const alerts = await getAlertFeed(database);
  const kinds = new Set(alerts.map((item) => item.kind));
  assert.ok(kinds.has('source_check'));
  assert.ok(kinds.has('coverage_release'));
  assert.ok(kinds.has('contract_evidence'));
  assert.ok(kinds.has('review_question'));
  assert.ok(alerts.length <= 30);
  assert.ok(alerts.every((item) => item.boundary));

  const rss = alertsRss(alerts);
  assert.match(rss, /<rss version="2\.0"/);
  assert.match(rss, /Busisi evidence updates/);
  assert.match(rss, /A review question is not a finding of wrongdoing/);

  const api = await worker.fetch(request('/api/v1/alerts'), environment(database));
  assert.equal(api.status, 200);
  assert.equal((await api.json()).meta.review_scope, 'bounded_public_evidence_updates');

  const feed = await siteWorker.fetch(request('/feeds/updates.xml'), environment(database));
  assert.equal(feed.status, 200);
  assert.match(feed.headers.get('content-type'), /^application\/rss\+xml/);
  assert.match(await feed.text(), /<channel>/);
});

const explorerUrl = (query = '') => new URL(`https://busisi.test/api/v1/budgets${query}`);
const changeUrl = (query = '') => new URL(`https://busisi.test/api/v1/changes${query}`);
const reviewUrl = (query = '') => new URL(`https://busisi.test/api/v1/review-rankings${query}`);
const integrityUrl = (query = '') => new URL(`https://busisi.test/api/v1/integrity-signals${query}`);
const contractorUrl = (query = '') => new URL(`https://busisi.test/api/v1/contractors${query}`);
const placeUrl = (query = '') => new URL(`https://busisi.test/api/v1/places${query}`);
const contractorProjectUrl = (query = '') => new URL(
  `https://busisi.test/api/v1/contractors/pcab%3A22222/projects${query}`,
);
const concentrationUrl = (query = '') => new URL(`https://busisi.test/api/v1/contractor-concentrations${query}`);
const agencyUrl = (query = '') => new URL(`https://busisi.test/api/v1/agency-budgets${query}`);
const releaseUrl = (query = '') => new URL(`https://busisi.test/api/v1/allotment-releases${query}`);

test('validates allotment-release filters and cursor scope', () => {
  const query = parseAllotmentReleaseQuery(releaseUrl(
    '?q=DPWH&level=departments&band=below_90&sort=balance_desc&limit=10',
  ));
  assert.deepEqual(query, {
    q: 'DPWH', level: 'departments', band: 'below_90', sort: 'balance_desc',
    limit: 10, offset: 0,
  });
  for (const [value, message] of [
    ['?level=agency', 'level is invalid'],
    ['?band=corruption', 'band is invalid'],
    ['?sort=unknown', 'sort is invalid'],
    ['?limit=0', 'limit is outside the supported range'],
    [`?q=${'x'.repeat(201)}`, 'q is too long'],
    ['?cursor=broken', 'cursor is invalid for this query'],
  ]) {
    assert.throws(() => parseAllotmentReleaseQuery(releaseUrl(value)), {
      name: 'QueryError', message,
    });
  }
});

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
    [`?group=${'x'.repeat(201)}`, 'group is too long'],
  ];
  for (const [query, message] of invalid) {
    assert.throws(() => parseReviewQuery(reviewUrl(query)), { name: 'QueryError', message });
  }
  assert.deepEqual(parseReviewQuery(reviewUrl()), {
    signal: 'house_only', dataset: 'all', dimension: 'region', group: '', limit: 25,
  });
  assert.deepEqual(parseReviewQuery(reviewUrl('?dataset=dpwh&dimension=office&group=Central%20Office&limit=1')), {
    signal: 'house_only', dataset: 'dpwh', dimension: 'office', group: 'Central Office', limit: 1,
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
  assert.deepEqual(parseContractorProjectQuery(contractorProjectUrl(
    '?year=2025&relationship=joint&status=On-Going&signal=with_signals&sort=year_desc&limit=10',
  )), {
    year: 2025,
    relationship: 'joint',
    status: 'On-Going',
    signal: 'with_signals',
    sort: 'year_desc',
    limit: 10,
    offset: 0,
  });
  for (const [query, message] of [
    ['?relationship=partner', 'relationship is invalid'],
    ['?signal=risky', 'signal is invalid'],
    ['?sort=random', 'sort is invalid'],
    ['?year=not-a-year', 'year is invalid'],
    ['?year=1999', 'year is outside the supported range'],
    [`?status=${'x'.repeat(201)}`, 'status is too long'],
    ['?limit=101', 'limit is outside the supported range'],
    ['?cursor=broken', 'cursor is invalid for this query'],
  ]) {
    assert.throws(() => parseContractorProjectQuery(contractorProjectUrl(query)), {
      name: 'QueryError', message,
    });
  }
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
  assert.match(exactDocument, /Project image evidence/);
  assert.match(exactDocument, new RegExp(`/media/project-images/${'9'.repeat(64)}`));
  assert.match(exactDocument, /source-reported, timezone unstated/);
  assert.equal(conflict.status, 200);
  assert.match(conflictDocument, /Conflicting exact identifiers/);
  assert.match(conflictDocument, /26ZERO01/);
  assert.match(conflictDocument, /25O00113/);
  assert.match(conflictDocument, /not a finding of wrongdoing/i);
  assert.match(conflictDocument, /Source image evidence quarantined/);
  assert.equal(absent.status, 200);
  assert.match(absentDocument, /No exact secondary row located/);
  assert.match(absentDocument, /No exact row for this contract was accepted/);
  assert.match(absentDocument, /No images reported by either acquired source view/);
  assert.equal(former.status, 301);
  assert.equal(former.headers.get('location'), 'https://busisi.org/contracts/25O00113/');
});

test('serves only verified project images from private object storage', async () => {
  const database = new LocalD1();
  const imageId = '9'.repeat(64);
  const published = await siteWorker.fetch(
    request(`/media/project-images/${imageId}`),
    environment(database),
  );
  const absent = await siteWorker.fetch(
    request(`/media/project-images/${'8'.repeat(64)}`),
    environment(database),
  );
  const objectMissingEnv = environment(database);
  objectMissingEnv.PROJECT_MEDIA = { get: async () => null };
  const objectMissing = await siteWorker.fetch(
    request(`/media/project-images/${imageId}`),
    objectMissingEnv,
  );
  const bindingMissingEnv = environment(database);
  delete bindingMissingEnv.PROJECT_MEDIA;
  const bindingMissing = await siteWorker.fetch(
    request(`/media/project-images/${imageId}`),
    bindingMissingEnv,
  );

  assert.equal(published.status, 200);
  assert.equal(published.headers.get('content-type'), 'image/jpeg');
  assert.match(published.headers.get('cache-control'), /immutable/);
  assert.equal(published.headers.get('etag'), `"${'a'.repeat(64)}"`);
  assert.deepEqual(new Uint8Array(await published.arrayBuffer()), new Uint8Array([0xff, 0xd8, 0xff, 0xd9]));
  assert.equal(absent.status, 404);
  assert.equal(objectMissing.status, 404);
  assert.equal(bindingMissing.status, 404);
  database.close();
});

test('defaults a missing project-image result collection to an empty gallery', async () => {
  const evidence = await getProjectImageEvidence({
    prepare: () => ({
      bind: () => ({
        first: async () => ({ contract_id: '24EMPTY1', state: 'no_images' }),
        all: async () => ({}),
      }),
    }),
  }, '24EMPTY1');

  assert.equal(evidence.coverage.contract_id, '24EMPTY1');
  assert.deepEqual(evidence.images, []);
});

test('renders original-color source image metadata without inventing missing fields', () => {
  const baseImage = {
    contract_id: '24SP0001',
    component_id: 'COMPONENT-1',
    purpose: '',
    source_status: '',
    captured_at: '2026-11-03 10:00:00',
    fiscal_year: 'FY2024',
    latitude: null,
    longitude: null,
    coordinate_status: 'not_reported',
    source_url: 'https://s3.transparency.dpwh.gov.ph/dpwh-gallery/fy2024/test/photo.jpg',
    artifact_sha256: 'a'.repeat(64),
    width: 1280,
    height: 960,
  };
  const document = deliveryRecordBody({
    record: {
      contract_id: '24SP0001', fiscal_year: 2024, description: 'Sparse source record',
      location: '', budget_centavos: 0, district_context: null,
    },
    related: [], budgets: [], candidates: [], projects: [], signals: [], contractors: [],
    imageEvidence: {
      coverage: {
        state: 'verified_exact', summary_count: 2, endpoint_count: 2,
        note: 'Counts reconcile.', retrieved_at: '2026-11-03T10:00:00Z',
      },
      images: [
        { ...baseImage, image_id: 'b'.repeat(64), photo_number: 1 },
        { ...baseImage, image_id: 'c'.repeat(64), photo_number: 2 },
      ],
    },
  });

  assert.match(document, /2 archived source images/);
  assert.match(document, /Purpose not stated/);
  assert.match(document, /Status not stated/);
  assert.match(document, /Coordinates<\/dt><dd>Not reported/);
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

test('validates contract intelligence filters and cursor scope', () => {
  const url = new URL('https://busisi.test/api/v1/contracts?q=pump&year=2025&state=structured_exact&category=Flood%20Control&region=NCR&province=Manila%201st%20DEO&status=On-Going&contractor=ACME&awardee=ACME&signal=without_signals&budget=100m_500m&sort=contract_asc&limit=10');
  assert.deepEqual(parseContractIntelligenceQuery(url), {
    q: 'pump',
    year: 2025,
    state: 'structured_exact',
    category: 'Flood Control',
    region: 'NCR',
    province: 'Manila 1st DEO',
    status: 'On-Going',
    contractor: 'ACME',
    awardee: 'ACME',
    signal: 'without_signals',
    budget: '100m_500m',
    sort: 'contract_asc',
    limit: 10,
    offset: 0,
  });
  for (const search of [
    '?state=accused',
    '?signal=corruption',
    '?budget=unlimited',
    '?sort=random',
    '?year=abc',
    '?year=1999',
    '?limit=0',
    '?limit=1000',
    `?q=${'x'.repeat(201)}`,
    `?category=${'x'.repeat(121)}`,
    `?region=${'x'.repeat(121)}`,
    `?province=${'x'.repeat(121)}`,
    `?status=${'x'.repeat(121)}`,
    `?contractor=${'x'.repeat(201)}`,
    `?awardee=${'x'.repeat(201)}`,
    '?cursor=not-a-cursor',
  ]) {
    assert.throws(
      () => parseContractIntelligenceQuery(new URL(`https://busisi.test/api/v1/contracts${search}`)),
      { name: 'QueryError' },
    );
  }
});

test('publishes searchable contract intelligence, facets and CSV evidence', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const summary = await worker.fetch(
    request('/api/v1/contract-intelligence-summary'),
    environment(database),
  );
  const records = await worker.fetch(
    request('/api/v1/contracts?year=2025&state=structured_exact&category=Flood%20Control&region=NCR&province=Manila%201st%20DEO&status=On-Going&contractor=ACME&signal=without_signals&budget=100m_500m'),
    environment(database),
  );
  const conflicts = await worker.fetch(
    request('/api/v1/contracts?state=conflict_review'),
    environment(database),
  );
  const csv = await worker.fetch(
    request('/api/v1/contracts.csv?state=conflict_review'),
    environment(database),
  );
  const summaryBody = await summary.json();
  const recordsBody = await records.json();
  const conflictBody = await conflicts.json();

  assert.equal(summary.status, 200);
  assert.equal(summaryBody.data.total_contracts, 3);
  assert.deepEqual(summaryBody.data.states, {
    conflict_review: 1,
    no_exact_row: 1,
    structured_exact: 1,
  });
  assert.ok(summaryBody.data.facets.categories.some((item) => item.value === 'Flood Control'));
  assert.ok(summaryBody.data.facets.provinces.some((item) => item.value === 'Manila 1st DEO'));
  assert.equal(recordsBody.meta.total, 1);
  assert.equal(recordsBody.meta.review_scope, 'contract_intelligence_evidence');
  assert.equal(recordsBody.data[0].contract_id, '25O00113');
  assert.equal(recordsBody.data[0].awardee_names, 'ACME BUILDERS');
  assert.equal(recordsBody.data[0].reader_url, '/contracts/25O00113/');
  assert.equal(conflictBody.meta.total, 1);
  assert.equal(conflictBody.data[0].contract_id, '26ZERO01');
  assert.equal(csv.status, 200);
  assert.match(csv.headers.get('content-disposition'), /busisi-contract-evidence\.csv/);
  assert.equal(csv.headers.get('x-export-row-limit'), '10000');
  assert.match(await csv.text(), /"26ZERO01","conflict_review"/);

  const firstPage = await worker.fetch(
    request('/api/v1/contracts?sort=contract_asc&limit=1'),
    environment(database),
  );
  const firstPageBody = await firstPage.json();
  assert.equal(firstPageBody.data[0].contract_id, '24NO0001');
  assert.ok(firstPageBody.meta.next_cursor);
  const secondPage = await worker.fetch(
    request(`/api/v1/contracts?sort=contract_asc&limit=1&cursor=${encodeURIComponent(firstPageBody.meta.next_cursor)}`),
    environment(database),
  );
  const secondPageBody = await secondPage.json();
  assert.equal(secondPageBody.data[0].contract_id, '25O00113');
  const mismatchedCursor = await worker.fetch(
    request(`/api/v1/contracts?sort=budget_desc&limit=1&cursor=${encodeURIComponent(firstPageBody.meta.next_cursor)}`),
    environment(database),
  );
  assert.equal(mismatchedCursor.status, 400);

  database.database.exec(`
    INSERT INTO integrity_signal_items VALUES
      ('25O00113:test', '25O00113', 2025, 'missing_coordinate', 'coverage_gap',
       'Coordinate not available', 'Construction of San Andres Pumping Station',
       'ACME BUILDERS', '12345', 37679270658, 'On-Going', '62.5',
       'Manila 1st DEO', 'NCR', '', '', 'No usable coordinate.',
       'Missing coordinates do not indicate a missing project.', '${'f'.repeat(64)}');
    UPDATE delivery_project_details SET contractor_parties_json = '{}'
      WHERE contract_id = '24NO0001';
  `);
  const signalled = await worker.fetch(
    request('/api/v1/contracts?signal=with_signals&budget=100m_500m&sort=signals_desc'),
    environment(database),
  );
  const signalledBody = await signalled.json();
  assert.equal(signalledBody.meta.total, 1);
  assert.deepEqual(signalledBody.data[0].signal_codes, ['missing_coordinate']);
  const underBudget = await worker.fetch(
    request('/api/v1/contracts?budget=under_10m&signal=without_signals'),
    environment(database),
  );
  assert.equal((await underBudget.json()).meta.total, 2);
  const sparse = await worker.fetch(
    request('/api/v1/contracts?budget=500m_plus&sort=awards_desc'),
    environment(database),
  );
  assert.equal((await sparse.json()).meta.total, 0);
  const nonArrayParties = await worker.fetch(
    request('/api/v1/contracts?q=24NO0001&sort=year_desc'),
    environment(database),
  );
  assert.deepEqual((await nonArrayParties.json()).data[0].contractor_parties, []);
});

test('publishes the contract intelligence explorer and client', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await siteWorker.fetch(request('/contracts/'), environment(database));
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /Contract intelligence explorer/);
  assert.match(document, /56,887 archived DPWH contract records/);
  assert.match(document, /Compare selected contracts/);
  assert.match(document, /Province/);
  assert.match(document, /Download filtered CSV, up to 10,000 rows/);
  assert.match(document, /\/assets\/contracts-v1\.js\?v=3/);
  assert.match(document, /Source patterns are review leads, not findings/);
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

test('publishes official FY2026 allotment releases with attached-agency filters', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const summary = await worker.fetch(
    request('/api/v1/allotment-release-summary'), environment(database),
  );
  const attached = await worker.fetch(
    request('/api/v1/allotment-releases?level=attached&band=below_90&sort=rate_asc'),
    environment(database),
  );
  const overReleased = await worker.fetch(
    request('/api/v1/allotment-releases?level=special&band=over_100'),
    environment(database),
  );

  const summaryBody = await summary.json();
  assert.equal(summaryBody.data.record_count, 3);
  assert.equal(summaryBody.data.as_of_date, '2026-09-30');
  assert.equal(summaryBody.data.total_releases_centavos, 653295146600000);
  const attachedBody = await attached.json();
  assert.equal(attachedBody.meta.total, 1);
  assert.equal(attachedBody.meta.review_scope, 'official_dbm_allotment_releases');
  assert.equal(attachedBody.data[0].record_id, 'release:oeos:amlc');
  assert.equal(attachedBody.data[0].parent_name, null);
  assert.equal(attachedBody.data[0].source_reader_url, '/releases/#source');
  const overBody = await overReleased.json();
  assert.equal(overBody.data[0].record_id, 'release:spf:test');

  const firstPage = await worker.fetch(
    request('/api/v1/allotment-releases?level=all&limit=1'), environment(database),
  );
  const firstBody = await firstPage.json();
  const secondPage = await worker.fetch(
    request(`/api/v1/allotment-releases?level=all&limit=1&cursor=${firstBody.meta.next_cursor}`),
    environment(database),
  );
  assert.equal((await secondPage.json()).data.length, 1);
});

test('publishes a deterministic catalogue of answerable and unsupported questions', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const response = await worker.fetch(
    request('/api/v1/questions'), environment(database),
  );
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.deepEqual(body.meta, {
    total: 22,
    states: { answerable: 11, partially_answerable: 5, not_supported: 6 },
    review_scope: 'evidence_question_catalogue',
  });
  assert.equal(new Set(body.data.map(({ id }) => id)).size, body.data.length);
  assert.ok(body.data.every(({ state }) => [
    'answerable', 'partially_answerable', 'not_supported',
  ].includes(state)));

  const changes = body.data.find(({ id }) => id === 'fy2027-project-stage-changes');
  assert.equal(changes.state, 'answerable');
  assert.equal(changes.scope_count, 4);
  assert.equal(changes.as_of, 'FY2027');
  assert.equal(changes.answer_url, '/changes/');
  assert.match(changes.limitation, /four acquired programs/i);

  const releases = body.data.find(({ id }) => id === 'dbm-allotment-releases');
  assert.equal(releases.scope_count, 3);
  assert.equal(releases.as_of, '2026-09-30');
  assert.match(releases.limitation, /not payment or spending/i);

  const procurement = body.data.find(({ id }) => id === 'official-procurement-evidence');
  assert.equal(procurement.state, 'partially_answerable');
  assert.equal(procurement.scope_count, 2);
  assert.match(procurement.limitation, /reviewed pilot/i);

  const payment = body.data.find(({ id }) => id === 'actual-project-payment');
  assert.equal(payment.state, 'not_supported');
  assert.equal(payment.answer_url, null);
  assert.equal(payment.scope_count, 0);
  assert.match(payment.limitation, /voucher|receipt|payment confirmation/i);

  for (const item of body.data) {
    assert.equal(typeof item.question, 'string');
    assert.equal(typeof item.scope_label, 'string');
    assert.equal(typeof item.evidence_level, 'string');
    assert.equal(typeof item.answer_summary, 'string');
    assert.equal(typeof item.limitation, 'string');
    assert.equal(item.answer_url !== null && item.answer_url.startsWith('/api/'), false);
  }
});

test('renders the evidence question catalogue with current counts and hard boundaries', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const response = await siteWorker.fetch(request('/questions/'), environment(database));
  const document = await response.text();

  assert.equal(response.status, 200);
  assert.match(document, /What can Busisi answer today/);
  assert.match(document, /Can answer/);
  assert.match(document, /Can partly answer/);
  assert.match(document, /Cannot answer yet/);
  assert.match(document, /What this answer cannot prove/);
  assert.match(document, /4 compared project rows/);
  assert.match(document, /3 official DBM release rows/);
  assert.match(document, /36,748 contracts in the latest coverage release/);
  assert.match(document, /Based on official or checked records/);
  assert.match(document, /Acquired FY2027 NEP and House bill pages/);
  assert.match(document, /Was this project actually paid/);
  assert.match(document, /Who inserted, sponsored, or politically motivated a line item/);
  assert.match(document, /href="\/changes\/"/);
  assert.match(document, /href="\/methodology\/"/);
  assert.doesNotMatch(document, /establishes (?:fraud|corruption)|confirmed ghost project/i);
  assert.doesNotMatch(document, /href="\/api\/v1\//);
});

test('keeps the question catalogue explicit when optional releases are unavailable', () => {
  const records = buildQuestionCatalogue({
    change: {}, review: {}, agency: {}, release: {}, integrity: {}, contracts: {},
    cycle: { metadata: {} }, publicValue: {}, source: null,
    acquisition: { summary: {}, states: {} }, coverage: null,
    procurement: { metadata: {} }, coa: { metadata: {} },
  });

  assert.equal(records.length, 22);
  assert.equal(records.find(({ id }) => id === 'fy2027-project-stage-changes').as_of, 'FY2027');
  assert.match(
    records.find(({ id }) => id === 'project-image-coverage').answer_summary,
    /No gated coverage release is available/,
  );
  assert.match(
    records.find(({ id }) => id === 'monitored-source-revisions').scope_label,
    /No monitor release available/,
  );
  assert.ok(records.every(({ scope_count }) => Number.isSafeInteger(scope_count)));
});

const insertPublicServiceExamples = (database) => database.database.exec(`
  INSERT INTO facility_registry_status VALUES
    (1, '2026-11-04T14:00:00+00:00',
     'https://www.deped.gov.ph/wp-content/uploads/List-of-PSIP-III-Sites.xlsx',
     'blocked', 'source_blocked', 403, NULL, 1095, 0, 0, 0, NULL, NULL, 0,
     'The official DepEd source blocked unattended acquisition.', '${'8'.repeat(64)}');
  INSERT INTO facility_registry_sources VALUES
    ('deped-ppp-2025', 'Department of Education', 'PPP indicative school list',
     'https://www.deped.gov.ph/example.pdf', '${'9'.repeat(64)}',
     '2026-11-04T00:00:00+00:00', 'Preliminary school list, not a complete national registry.', 'partial');
  INSERT INTO facility_identities VALUES
    ('deped:136505', 'school', '136505', 'San Antonio Elementary School',
     'Quezon City', 'Metro Manila', 'NCR', 14650000, 121050000, 'deped-ppp-2025');
  INSERT INTO facility_identity_details VALUES
    ('deped:136505', 'Quezon City', 48, 1, 0, 1, 1);
  INSERT INTO facility_record_links VALUES
    ('budget', 'dpwh:school', 'official_exact', 'deped:136505',
     'school:san-antonio-es:quezon-city', 'San Antonio Elementary School',
     'official_id_and_place', 100, '["official_id","place_match"]',
     'The source list is preliminary and does not cover every Philippine school.',
     '2026-11-04T00:00:00+00:00'),
    ('delivery', '25HOSP01', 'group_only', NULL,
     'hospital:district-hospital:cebu', 'District Hospital',
     'normalized_name_and_place', 70, '["name_match","place_match"]',
     'This groups similar record labels. It is not an official facility identity.',
     '2026-11-04T00:00:00+00:00'),
    ('delivery', '26ZERO01', 'ambiguous', NULL, NULL, 'Sample Health Center',
     'multiple_registry_candidates', 0, '["multiple_candidates"]',
     'More than one facility could fit the name and place, so no identity was selected.',
     '2026-11-04T00:00:00+00:00');
  INSERT INTO stage_change_items VALUES
    ('dpwh:school', 2027, 'dpwh', 'Construction of Four-Storey School Building',
     'Basic Education Facilities', 'School Building Program', 'Region VII',
     'Cebu 1st DEO', 'unchanged', 'Same amount in both', 'candidate', 0, 1,
     4500000000, 4500000000, 0, 'https://budget.example/school',
     'https://budget.example/nep-school.pdf#page=8',
     'https://budget.example/house-school.pdf#page=9', 8, 9,
     '${'a'.repeat(40)}', '${'4'.repeat(64)}', 'four storey school building');
  INSERT INTO delivery_items VALUES
    ('25HOSP01', 2025, 'Rehabilitation of District Hospital', 9800000000,
     'Cebu, Region VII', 'GAA 2025', 'family:hospital',
     'rehabilitation district hospital', '${'b'.repeat(64)}');
  INSERT INTO delivery_project_details VALUES
    ('25HOSP01', 2025, 'Buildings and Facilities', 'On-Going', '40',
     'HEALTH BUILDERS (54321)',
     '[{"contractor_key":"pcab:54321","contractor_name":"HEALTH BUILDERS","pcab_id":"54321"}]',
     '2025-01-15', '2025-12-20', 'Cebu 1st DEO', 'Region VII', '', '', 0,
     '${'b'.repeat(64)}');
  INSERT INTO contract_acquisition_details VALUES
    ('25HOSP01', 2025, 'valid', 'aligned', 'no_exact_row', 0, 0);
  INSERT INTO integrity_signal_items VALUES
    ('25HOSP01:missing_coordinate', '25HOSP01', 2025, 'missing_coordinate',
     'coverage_gap', 'Coordinate not available', 'Rehabilitation of District Hospital',
     'HEALTH BUILDERS', '54321', 9800000000, 'On-Going', '40', 'Cebu 1st DEO',
     'Region VII', '', '', 'No usable coordinate.',
     'Missing coordinates do not indicate a missing project.', '${'f'.repeat(64)}'),
    ('25HOSP01:same_site_repeat_family', '25HOSP01', 2025, 'same_site_repeat_family',
     'identity_review', 'Same site and project family across fiscal years',
     'Rehabilitation of District Hospital', 'HEALTH BUILDERS', '54321', 9800000000,
     'On-Going', '40', 'Cebu 1st DEO', 'Region VII', '', '',
     'The project family appears at the same recorded site in another year.',
     'The records can describe legitimate phases or continuing works at one site.',
     '${'f'.repeat(64)}');
  INSERT INTO project_image_coverage VALUES
    ('25HOSP01', 0, 0, 0, 'no_images', '${'7'.repeat(64)}', '${'8'.repeat(64)}',
     '2026-11-04T02:00:00+00:00', 'Both source representations report no images.');
`);

test('publishes a deterministic public-services inventory with separated review flags', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);

  const summary = await worker.fetch(
    request('/api/v1/public-services-summary'), environment(database),
  );
  const summaryBody = await summary.json();
  assert.equal(summary.status, 200);
  assert.equal(summaryBody.meta.review_scope, 'title_classified_public_service_records');
  assert.deepEqual(summaryBody.data.records, {
    total: 4, budget: 2, delivery: 2, flagged: 3,
  });
  assert.deepEqual(summaryBody.data.facilities, {
    school: 1, hospital: 1, health_center: 2,
  });
  assert.equal(summaryBody.data.work_types.new_build, 2);
  assert.equal(summaryBody.data.work_types.rehabilitation, 1);
  assert.equal(summaryBody.data.work_types.unspecified, 1);
  assert.equal(summaryBody.data.classification_version, 'public-services-v2');
  assert.equal(summaryBody.data.identity_method_version, 'facility-identity-v1');
  assert.deepEqual(summaryBody.data.registry_status, {
    checked_at: '2026-11-04T14:00:00+00:00',
    source_url: 'https://www.deped.gov.ph/wp-content/uploads/List-of-PSIP-III-Sites.xlsx',
    source_state: 'blocked',
    release_state: 'source_blocked',
    http_status: 403,
    source_artifact_sha256: null,
    expected_facilities: 1095,
    validated_facilities: 0,
    candidate_links: 0,
    reviewed_cases: 0,
    precision_bps: null,
    agreement_bps: null,
    critical_failures: 0,
    status_note: 'The official DepEd source blocked unattended acquisition.',
    status_sha256: '8'.repeat(64),
  });
  assert.match(summaryBody.data.limitation, /not unique facilities/i);
  assert.deepEqual(summaryBody.data.identity_coverage, {
    official_facilities: 1,
    official_linked_records: 1,
    record_groups: 1,
    grouped_records: 1,
    ambiguous_records: 1,
    unlinked_records: 1,
  });

  const schools = await worker.fetch(
    request('/api/v1/public-services?facility=school'), environment(database),
  );
  const schoolBody = await schools.json();
  assert.equal(schoolBody.meta.total, 1);
  assert.equal(schoolBody.meta.review_scope, 'title_classified_public_service_records');
  assert.equal(schoolBody.data[0].record_id, 'dpwh:school');
  assert.equal(schoolBody.data[0].facility_type, 'school');
  assert.equal(schoolBody.data[0].work_type, 'new_build');
  assert.equal(schoolBody.data[0].facility_identity.state, 'official_exact');
  assert.equal(schoolBody.data[0].facility_identity.official_id, '136505');
  assert.equal(schoolBody.data[0].facility_identity.name, 'San Antonio Elementary School');
  assert.match(schoolBody.data[0].facility_identity.explanation, /official school ID/i);
  assert.deepEqual(schoolBody.data[0].flags, []);
  assert.match(schoolBody.data[0].reader_url, /^\/records\/change\//);

  const identity = await worker.fetch(
    request('/api/v1/public-services?flag=identity_conflict'), environment(database),
  );
  const identityBody = await identity.json();
  assert.equal(identityBody.meta.total, 1);
  assert.equal(identityBody.data[0].record_id, '26ZERO01');
  assert.ok(identityBody.data[0].flags.some(({ code, classification }) => (
    code === 'contract_identifier_conflict' && classification === 'identity_conflict'
  )));
  const identityLanguage = identityBody.data[0].flags.find(
    ({ classification }) => classification === 'identity_conflict',
  ).plain_language;
  assert.equal(identityLanguage.label, 'The project ID may point to different records');
  assert.match(identityLanguage.why_check, /right project/i);
  assert.match(identityLanguage.not_proof, /does not prove/i);
  assert.match(identityLanguage.next_step, /compare/i);

  const rehabilitation = await worker.fetch(
    request('/api/v1/public-services?work=rehabilitation'), environment(database),
  );
  const rehabilitationBody = await rehabilitation.json();
  assert.equal(rehabilitationBody.meta.total, 1);
  assert.equal(rehabilitationBody.data[0].record_id, '25HOSP01');
  assert.equal(rehabilitationBody.data[0].source_type, 'delivery');
  assert.equal(rehabilitationBody.data[0].facility_identity.state, 'group_only');
  assert.equal(rehabilitationBody.data[0].facility_identity.name, 'District Hospital');
  assert.match(rehabilitationBody.data[0].facility_identity.explanation, /not an official identity/i);
  assert.ok(rehabilitationBody.data[0].flags.some(({ code }) => code === 'missing_coordinate'));
  assert.ok(rehabilitationBody.data[0].flags.some(({ code }) => code === 'no_exact_secondary_row'));
  assert.ok(rehabilitationBody.data[0].flags.some(({ code }) => code === 'source_image_gap'));
  assert.equal(rehabilitationBody.data[0].reader_url, '/contracts/25HOSP01/');
});

test('filters public-service records by explainable facility identity state', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);

  const official = await worker.fetch(
    request('/api/v1/public-services?identity=official_exact'), environment(database),
  );
  const officialBody = await official.json();
  assert.equal(official.status, 200);
  assert.equal(officialBody.meta.total, 1);
  assert.equal(officialBody.data[0].record_id, 'dpwh:school');

  const ambiguous = await worker.fetch(
    request('/api/v1/public-services?identity=ambiguous'), environment(database),
  );
  const ambiguousBody = await ambiguous.json();
  assert.equal(ambiguousBody.meta.total, 1);
  assert.equal(ambiguousBody.data[0].record_id, '26ZERO01');
  assert.match(ambiguousBody.data[0].facility_identity.explanation, /more than one/i);

  assert.throws(() => parsePublicServicesQuery(new URL(
    'https://busisi.test/api/v1/public-services?identity=confirmed',
  )), /identity is invalid/);
});

test('publishes an official facility dossier without converting records into buildings', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);
  database.database.exec(`
    INSERT INTO budget_items VALUES
      ('budget:school', 'line:school', 2026, 'Repair of San Antonio Elementary School',
       1200000000, 'family:school-repair', 'San Antonio school repair', '${'c'.repeat(64)}');
    INSERT INTO delivery_items VALUES
      ('26SCHOOL01', 2026, 'Repair of San Antonio Elementary School', 1500000000,
       'Quezon City, NCR', 'GAA 2026', 'family:school-repair',
       'San Antonio school repair', '${'d'.repeat(64)}');
    INSERT INTO delivery_project_details VALUES
      ('26SCHOOL01', 2026, 'Buildings and Facilities', 'Completed', '100',
       'SAMPLE BUILDER', '[]', '2026-01-01', '2026-06-30', 'Quezon City DEO',
       'NCR', '', '', 0, '${'d'.repeat(64)}');
    INSERT INTO facility_record_links VALUES
      ('budget', 'budget:school', 'official_exact', 'deped:136505', NULL,
       'San Antonio Elementary School', 'exact_registry_name_and_place', 95, '{}',
       'The link identifies a school, not a completed building.',
       '2026-11-04T00:00:00+00:00'),
      ('delivery', '26SCHOOL01', 'official_exact', 'deped:136505', NULL,
       'San Antonio Elementary School', 'exact_registry_name_and_place', 95,
       '["exact_registry_name_in_title","place_in_record"]',
       'The link identifies a school, not a completed building.',
       '2026-11-04T00:00:00+00:00');
  `);

  const facility = await getFacility(database, 'deped:136505');
  assert.equal(facility.record.official_id, '136505');
  assert.equal(facility.record.division, 'Quezon City');
  assert.equal(facility.links.length, 3);
  assert.deepEqual(
    facility.links.map(({ reader_url }) => reader_url).sort(),
    [
      '/contracts/26SCHOOL01/',
      '/records/budget/budget%3Aschool/',
      '/records/change/dpwh%3Aschool/',
    ],
  );
  assert.deepEqual(facility.links.find(({ record_id }) => record_id === 'budget:school').signals, []);
  assert.equal(facility.summary.record_count, 3);
  assert.equal(facility.summary.budget_records, 2);
  assert.equal(facility.summary.delivery_records, 1);
  assert.equal(facility.summary.first_year, 2026);
  assert.equal(facility.summary.last_year, 2027);

  const api = await worker.fetch(
    request('/api/v1/facilities/deped%3A136505'), environment(database),
  );
  const apiBody = await api.json();
  assert.equal(api.status, 200);
  assert.equal(apiBody.meta.review_scope, 'official_facility_identity_and_linked_records');
  assert.equal(apiBody.data.record.official_name, 'San Antonio Elementary School');

  const pageResponse = await siteWorker.fetch(
    request('/facilities/deped%3A136505/'), environment(database),
  );
  const pageDocument = await pageResponse.text();
  assert.equal(pageResponse.status, 200);
  assert.match(pageDocument, /San Antonio Elementary School/);
  assert.match(pageDocument, /Official school ID 136505/);
  assert.match(pageDocument, /3 linked public records/);
  assert.match(pageDocument, /not a count of school buildings/i);
  assert.match(pageDocument, /Preliminary school list, not a complete national registry/);
  assert.match(pageDocument, /Open linked record/);

  const missingApi = await worker.fetch(
    request('/api/v1/facilities/deped%3Amissing'), environment(database),
  );
  assert.equal(missingApi.status, 404);
  assert.deepEqual(await missingApi.json(), { detail: 'facility not found' });
});

test('publishes the facility registry gate status without exposing a false release', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);

  const response = await worker.fetch(
    request('/api/v1/facility-registry-status'), environment(database),
  );
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.meta.review_scope, 'official_facility_registry_release_gate');
  assert.equal(body.data.source_state, 'blocked');
  assert.equal(body.data.release_state, 'source_blocked');
  assert.equal(body.data.validated_facilities, 0);
  assert.equal(body.data.candidate_links, 0);
  assert.equal(body.data.reviewed_cases, 0);
});

test('renders a sparse facility dossier without inventing coordinates or linked records', () => {
  const document = facilityBody({
    record: {
      official_id: '<100001>',
      official_name: '<Sample School>',
      municipality: 'Sample City',
      province: 'Sample Province',
      region: 'Region I',
      division: '',
      latitude_e6: null,
      longitude_e6: null,
      source_row: null,
      demolition_required: 0,
      geotechnical_report: 0,
      site_development_plan: 0,
      ownership_documents: 0,
      dataset_name: 'Scoped school list',
      publisher: 'Department of Education',
      acquired_at: '2026-11-04T00:00:00+00:00',
      artifact_sha256: 'a'.repeat(64),
      source_status: 'partial',
      scope_note: 'Not a national registry.',
      source_url: 'https://www.deped.gov.ph/list.xlsx',
    },
    links: [],
    summary: {
      record_count: 0,
      budget_records: 0,
      delivery_records: 0,
      budget_amount_centavos: 0,
      delivery_amount_centavos: 0,
      first_year: null,
      last_year: null,
    },
  });

  assert.match(document, /Not stated in the registry/);
  assert.match(document, /No public budget or delivery record has passed/);
  assert.match(document, /Not marked yes in the source list/);
  assert.match(document, /&lt;Sample School&gt;/);
  assert.doesNotMatch(document, /<Sample School>/);
});

test('reuses the public-services and registry-status summary within one database binding', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const preparedBeforeSummary = database.preparedSql.length;

  const first = await getPublicServicesSummary(database);
  const second = await getPublicServicesSummary(database);

  assert.strictEqual(second, first);
  assert.equal(database.preparedSql.length - preparedBeforeSummary, 2);
});

test('explains every facility registry release state in plain language', () => {
  const states = {
    source_unavailable: 'The official school list needs checking',
    awaiting_review: 'The school list passed, but links still need review',
    gate_failed: 'The school-link review did not pass',
    ready_for_publication: 'The checked school links are ready to publish',
    published: 'The checked school links are published',
    acquisition_failed: 'The official school-list check needs attention',
  };
  for (const [releaseState, heading] of Object.entries(states)) {
    const document = publicServicesBody({
      registry_status: {
        release_state: releaseState,
        status_note: 'Current checked state.',
        checked_at: '2026-11-04T14:00:00+00:00',
      },
    });
    assert.match(document, new RegExp(heading));
  }
  assert.match(publicServicesBody({}), /No official school-list check is available/);
});

test('validates public-services filters without exposing an accusation filter', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  for (const query of ['?facility=clinic', '?work=construction', '?flag=corruption', '?source=agency']) {
    const response = await worker.fetch(
      request(`/api/v1/public-services${query}`), environment(database),
    );
    assert.equal(response.status, 400, query);
  }
});

test('validates public-services pagination, combined filters and sparse rendering', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);

  const firstQuery = parsePublicServicesQuery(new URL(
    'https://busisi.test/api/v1/public-services?source=budget&limit=1&sort=title_asc',
  ));
  const preparedBeforeFirstPage = database.preparedSql.length;
  const first = await queryPublicServices(database, firstQuery);
  assert.equal(database.preparedSql.length - preparedBeforeFirstPage, 1);
  assert.equal(first.total, 2);
  assert.equal(first.records.length, 1);
  assert.ok(first.nextCursor);
  const secondQuery = parsePublicServicesQuery(new URL(
    `https://busisi.test/api/v1/public-services?source=budget&limit=1&sort=title_asc&cursor=${first.nextCursor}`,
  ));
  const second = await queryPublicServices(database, secondQuery);
  assert.equal(second.records.length, 1);
  assert.equal(second.nextCursor, null);
  assert.notEqual(second.records[0].record_id, first.records[0].record_id);
  assert.throws(() => parsePublicServicesQuery(new URL(
    `https://busisi.test/api/v1/public-services?source=delivery&limit=1&sort=title_asc&cursor=${first.nextCursor}`,
  )), /cursor is invalid/);

  const combined = parsePublicServicesQuery(new URL(
    'https://busisi.test/api/v1/public-services?q=Cebu&source=delivery&facility=hospital&work=rehabilitation&flag=with_flags&year=2025&sort=year_desc',
  ));
  const result = await queryPublicServices(database, combined);
  assert.equal(result.total, 1);
  assert.equal(result.records[0].record_id, '25HOSP01');
  assert.ok(result.records[0].flags.some(({ classification }) => (
    classification === 'location_review'
  )));

  const unflagged = await queryPublicServices(
    database,
    parsePublicServicesQuery(new URL(
      'https://busisi.test/api/v1/public-services?flag=without_flags&facility=school',
    )),
  );
  assert.equal(unflagged.total, 1);
  assert.deepEqual(unflagged.records[0].flags, []);

  const repeated = await queryPublicServices(
    database,
    parsePublicServicesQuery(new URL(
      'https://busisi.test/api/v1/public-services?flag=repeat_family',
    )),
  );
  assert.equal(repeated.total, 1);
  assert.equal(repeated.records[0].record_id, '25HOSP01');
  assert.ok(repeated.records[0].flags.some(({ classification }) => (
    classification === 'repeat_family'
  )));

  for (const query of [
    `?q=${'x'.repeat(201)}`, '?year=word', '?year=1900', '?limit=0', '?limit=101',
    '?sort=money', '?cursor=not-a-cursor',
  ]) {
    assert.throws(() => parsePublicServicesQuery(new URL(
      `https://busisi.test/api/v1/public-services${query}`,
    )));
  }
  assert.match(publicServicesBody(), /0 records that name a facility/);
});

test('renders an interactive public-services desk with explicit red-flag boundaries', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertPublicServiceExamples(database);

  const response = await siteWorker.fetch(
    request('/public-services/'), environment(database),
  );
  const document = await response.text();
  assert.equal(response.status, 200);
  assert.match(document, /Schools and health facilities in the public record/);
  assert.match(document, /4 records that name a facility/);
  assert.match(document, /3 records with things to check/);
  assert.match(document, /A budget amount and a contract budget mean different things/);
  assert.match(document, /Things that need checking/);
  assert.match(document, /The budget entry changed/);
  assert.match(document, /The same record says two different things/);
  assert.match(document, /The project ID may point to different records/);
  assert.match(document, /Some information is missing/);
  assert.match(document, /This does not mean the project is bad or illegal/);
  assert.match(document, /1 official facility identity linked/);
  assert.match(document, /1 possible facility group/);
  assert.match(document, /Official school list is currently blocked/);
  assert.match(document, /Last checked 2026-11-04T14:00:00\+00:00/);
  assert.match(document, /An official identity means the record was linked to a published facility ID/);
  assert.match(document, /data-public-services-desk/);
  assert.match(document, /\/assets\/public-services-v1\.js/);
  assert.doesNotMatch(document, /risk score|proves? (?:fraud|corruption)/i);
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
  const grouped = await worker.fetch(
    request('/api/v1/review-rankings?signal=house_only&dimension=region&group=Region%20VII'),
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
  const groupedCsv = await worker.fetch(
    request('/api/v1/review.csv?signal=house_only&dimension=region&group=Region%20VII'),
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
  const groupedBody = await grouped.json();
  assert.equal(groupedBody.meta.total, 1);
  assert.equal(groupedBody.data[0].region, 'Region VII');
  assert.equal((await largest.json()).meta.total, 1);
  assert.equal((await removed.json()).meta.total, 0);
  assert.equal((await decreased.json()).meta.total, 0);
  assert.equal(csv.headers.get('content-type'), 'text/csv; charset=utf-8');
  assert.match(await csv.text(), /"increased","dpwh","Sample bridge"/);
  const groupedCsvText = await groupedCsv.text();
  assert.match(groupedCsvText, /"Region VII"/);
  assert.doesNotMatch(groupedCsvText, /"Region III"/);
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
    contractor_associations: 1,
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
  assert.deepEqual(singleConflict.plain_language, {
    label: 'The project says ongoing, but progress says 100%',
    category: 'The record disagrees with itself',
    why_check: 'The status and progress fields should describe the same point in the work.',
    not_proof: 'This mismatch does not prove that the project is unfinished or that anyone did something wrong.',
    next_step: 'Check the latest project update, completion record, and inspection documents.',
  });
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

test('publishes a bounded place directory from recorded source labels', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const query = parsePlaceQuery(placeUrl('?level=province&q=Quezon&limit=20'));
  const direct = await queryPlaces(database, query);
  const response = await worker.fetch(
    request('/api/v1/places?level=province&q=Quezon&limit=20'), environment(database),
  );
  const payload = await response.json();

  assert.deepEqual(query, { level: 'province', q: 'Quezon', limit: 20 });
  assert.equal(response.status, 200);
  assert.equal(payload.meta.review_scope, 'recorded_dpwh_place_labels');
  assert.equal(payload.meta.boundary, 'Source labels are not verified geographic boundaries.');
  assert.equal(payload.data[0].place_name, 'Quezon 1st DEO');
  assert.equal(payload.data[0].project_count, direct[0].project_count);
  assert.match(payload.data[0].reader_url, /^\/contracts\/\?province=/);
  assert.throws(() => parsePlaceQuery(placeUrl('?level=barangay')), /level is invalid/);
  assert.throws(() => parsePlaceQuery(placeUrl('?limit=none')), /limit is invalid/);
  assert.throws(() => parsePlaceQuery(placeUrl('?limit=101')), /supported range/);
  assert.throws(() => parsePlaceQuery(placeUrl(`?q=${'x'.repeat(201)}`)), /q is too long/);
  assert.deepEqual(parsePlaceQuery(placeUrl()), { level: 'province', q: '', limit: 50 });
});

test('renders source-watch states without trusting source text as markup', () => {
  const unchanged = watchBody(
    { completed_contracts: 7, universe_contracts: 56890 },
    {
      checked_at: '<script>alert(1)</script>', status: 'unchanged',
      differences: [], limitations: [],
    },
  );
  const changed = watchBody(
    { completed_contracts: 9, universe_contracts: 56890 },
    { checked_at: '2026-11-04', status: 'changed', differences: ['one'], limitations: ['two'] },
  );

  assert.match(unchanged, /No source change detected/);
  assert.match(unchanged, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(unchanged, /<script>/);
  assert.match(changed, /source change or access problem needs checking/i);
  assert.match(changed, />1<\/h2>/);
});

test('publishes a public API catalogue', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  const response = await worker.fetch(request('/api/v1'), environment(database));
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.name, 'Busisi public evidence API');
  assert.equal(payload.read_only, true);
  assert.ok(payload.endpoints.some((item) => item.path === '/api/v1/places'));
  assert.ok(payload.endpoints.some((item) => item.path === '/api/v1/contracts'));
  assert.match(payload.evidence_boundary, /review lead/i);
});

test('keeps every joint contractor independently drillable and reconciled', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertJointContract(database);

  const contracts = await worker.fetch(
    request('/api/v1/contracts?contractor=EGB%20BUILDERS'), environment(database),
  );
  const projects = await worker.fetch(
    request('/api/v1/contractors/pcab%3A22222/projects?relationship=joint'),
    environment(database),
  );
  const profile = await siteWorker.fetch(
    request('/contractors/pcab%3A22222/'), environment(database),
  );
  const signal = await siteWorker.fetch(
    request('/records/integrity/25JOINT1%3Amissing_coordinate/'), environment(database),
  );
  const places = await worker.fetch(
    request('/api/v1/places?level=region&q=NCR'), environment(database),
  );

  const contractPayload = await contracts.json();
  assert.equal(contractPayload.meta.total, 1);
  assert.deepEqual(
    contractPayload.data[0].contractor_parties.map((party) => party.contractor_key),
    ['pcab:11111', 'pcab:22222'],
  );
  const projectPayload = await projects.json();
  assert.equal(projectPayload.meta.total, 1);
  assert.equal(projectPayload.data[0].contract_id, '25JOINT1');
  assert.equal(projectPayload.data[0].relationship, 'joint');
  assert.equal(projectPayload.data[0].party_position, 2);
  assert.equal(projectPayload.data[0].signal_count, 1);
  const place = (await places.json()).data.find((item) => item.place_name === 'NCR');
  assert.equal(place.project_count, 2);
  assert.equal(place.contractor_count, 3);
  assert.equal(place.total_budget_centavos, 42679270658);

  const profileDocument = await profile.text();
  assert.match(profileDocument, /1 joint-project association/);
  assert.match(profileDocument, /Projects associated with this recorded identity/);
  assert.match(profileDocument, /data-contractor-key="pcab:22222"/);
  assert.match(profileDocument, /\/assets\/contractor-v1\.js\?v=1/);
  const signalDocument = await signal.text();
  assert.match(signalDocument, /WRC BUILDERS/);
  assert.match(signalDocument, /EGB BUILDERS/);
  assert.match(signalDocument, /contractors\/pcab%3A11111/);
  assert.match(signalDocument, /contractors\/pcab%3A22222/);
});

test('publishes evidence-linked contractor accountability without alleging wrongdoing', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  database.database.exec(`
    INSERT INTO accountability_metadata VALUES
      ('checked_on', '2026-11-04'), ('blacklist_events', '1'), ('blacklist_active', '1'),
      ('cpes_events', '1'), ('award_signals', '2'), ('blacklist_name_only', '3'),
      ('cpes_missing_or_unmatched_pcab', '2');
    INSERT INTO contractor_blacklist_events VALUES
      ('order-1', 'pcab:12345', 'ACME BUILDERS', '12345', 'ACME BUILDERS, INC.',
       'pcab_name_exact', 'DPWH Central Office', 'Example public works contract',
       '2025-01-01', '2025-12-31', 'expired', '${'a'.repeat(64)}');
    INSERT INTO contractor_cpes_events VALUES
      ('rating-1', 'pcab:12345', 'ACME BUILDERS', '12345', 'ACME BUILDERS, INC.',
       'pcab_id_exact', 'Example road project', '2026-03-10', 'DPWH', 6215, 7156,
       'Poor', 1, '41st Release', '${'b'.repeat(64)}',
       'https://www.gppb.gov.ph/example-cpes.pdf');
    INSERT INTO contractor_award_timing_signals VALUES
      ('signal-1', 'award_during_blacklist', 'pcab:12345', 'ACME BUILDERS', '12345',
       'order-1', '25O00113', 'sole', 'structured_exact', 'ACME BUILDERS',
       '2025-03-01', 37679270658, '${'c'.repeat(64)}'),
      ('signal-2', 'award_after_low_cpes', 'pcab:12345', 'ACME BUILDERS', '12345',
       'rating-1', '25O00113', 'sole', 'structured_exact', 'ACME BUILDERS',
       '2026-04-01', 37679270658, '${'d'.repeat(64)}');
  `);

  const [summary, events, contractorApi, desk, profile] = await Promise.all([
    worker.fetch(request('/api/v1/accountability-summary'), environment(database)),
    worker.fetch(request('/api/v1/accountability-events'), environment(database)),
    worker.fetch(
      request('/api/v1/contractors/pcab%3A12345/accountability'), environment(database),
    ),
    siteWorker.fetch(request('/accountability/'), environment(database)),
    siteWorker.fetch(request('/contractors/pcab%3A12345/'), environment(database)),
  ]);

  assert.equal(summary.status, 200);
  assert.equal((await summary.json()).data.award_signals, 2);
  const eventBody = await events.json();
  assert.equal(eventBody.meta.total, 2);
  assert.equal(eventBody.data[0].contractor_key, 'pcab:12345');
  const contractorBody = await contractorApi.json();
  assert.equal(contractorBody.data.blacklist_events.length, 1);
  assert.equal(contractorBody.data.cpes_events[0].final_rating_bps, 7156);
  assert.equal(contractorBody.data.award_signals.length, 2);

  const deskDocument = await desk.text();
  assert.match(deskDocument, /Contractor accountability/);
  assert.match(deskDocument, /official restriction record/i);
  assert.match(deskDocument, /not proof of corruption/i);
  assert.match(deskDocument, /contractors\/pcab%3A12345/);
  const profileDocument = await profile.text();
  assert.match(profileDocument, /Accountability evidence timeline/);
  assert.match(profileDocument, /Archived secondary award row/);
  assert.match(profileDocument, /contracts\/25O00113/);
});

test('treats contractor searches literally and separates recorded parties from awardees', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertJointContract(database);

  const wildcard = await worker.fetch(
    request('/api/v1/contractors?q=%25'), environment(database),
  );
  const recorded = await worker.fetch(
    request('/api/v1/contracts?contractor=EGB%20BUILDERS'), environment(database),
  );
  const awardee = await worker.fetch(
    request('/api/v1/contracts?awardee=ACME%20BUILDERS'), environment(database),
  );

  assert.equal((await wildcard.json()).meta.total, 0);
  assert.equal((await recorded.json()).meta.total, 1);
  assert.equal((await awardee.json()).meta.total, 1);

  const client = readFileSync(
    fileURLToPath(new URL('../public/assets/contracts-v1.js', import.meta.url)),
    'utf8',
  );
  assert.doesNotMatch(client, /contractor_parties\?\.find/);
  assert.match(client, /contractor_parties.*forEach/s);
});

test('paginates and filters structured contractor project associations', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());
  insertJointContract(database);
  database.database.exec(`
    INSERT INTO delivery_items VALUES
      ('25SOLE01', 2025, 'Construction of Sole Public Market', 2000000000,
       'Manila 1st DEO, NCR', 'GAA 2025', 'family:sole-market',
       'construction sole public market', '${'b'.repeat(64)}');
    INSERT INTO delivery_project_details VALUES
      ('25SOLE01', 2025, 'Buildings and Facilities', 'Completed', '100',
       'EGB BUILDERS (22222)',
       '[{"contractor_key":"pcab:22222","contractor_name":"EGB BUILDERS","pcab_id":"22222"}]',
       '2025-01-01', '2025-12-31', 'Manila 1st DEO', 'NCR', '', '', 0,
       '${'b'.repeat(64)}');
    INSERT INTO contractor_project_associations VALUES
      ('pcab:22222', '25SOLE01', 1, 1, 'sole');
  `);

  const first = await worker.fetch(
    request('/api/v1/contractors/pcab%3A22222/projects?sort=contract_asc&limit=1'),
    environment(database),
  );
  const firstPayload = await first.json();
  const second = await worker.fetch(
    request(`/api/v1/contractors/pcab%3A22222/projects?sort=contract_asc&limit=1&cursor=${firstPayload.meta.next_cursor}`),
    environment(database),
  );
  const sole = await worker.fetch(
    request('/api/v1/contractors/pcab%3A22222/projects?relationship=sole&status=Completed&signal=without_signals'),
    environment(database),
  );
  const missing = await worker.fetch(
    request('/api/v1/contractors/pcab%3A99999/projects'), environment(database),
  );
  const malformed = await worker.fetch(
    request('/api/v1/contractors/wrong-key/projects'), environment(database),
  );

  assert.equal(firstPayload.meta.total, 2);
  assert.equal(firstPayload.data[0].contract_id, '25JOINT1');
  assert.ok(firstPayload.meta.next_cursor);
  assert.equal((await second.json()).data[0].contract_id, '25SOLE01');
  const solePayload = await sole.json();
  assert.equal(solePayload.meta.total, 1);
  assert.equal(solePayload.data[0].relationship, 'sole');
  assert.equal(solePayload.data[0].signal_count, 0);
  assert.equal(missing.status, 404);
  assert.equal(malformed.status, 404);
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
    ['/records/integrity/25A%3Astatus_progress_conflict/', /Something to check, not a finding/],
    ['/contractors/pcab%3A12345/', /Archived contractor activity/],
  ];

  for (const [path, expected] of paths) {
    const response = await siteWorker.fetch(request(path), environment(database));
    const document = await response.text();
    assert.equal(response.status, 200, path);
    assert.match(document, expected, path);
    assert.doesNotMatch(document, /(?:is|confirms|establishes) (?:fraud|corruption|wrongdoing)/i, path);
  }

  const budget = await siteWorker.fetch(
    request('/records/budget/2025%3Apump/'), environment(database),
  );
  const budgetDocument = await budget.text();
  assert.match(budgetDocument, /Original publisher/);
  assert.match(budgetDocument, /Department of Budget and Management/);
  assert.match(budgetDocument, /Accessed through/);
  assert.match(budgetDocument, /BetterGov GAA dataset/);
  assert.match(budgetDocument, /Processed and published by/);

  const delivery = await siteWorker.fetch(
    request('/contracts/25O00113/'), environment(database),
  );
  const deliveryDocument = await delivery.text();
  assert.match(deliveryDocument, /Department of Public Works and Highways/);
  assert.match(deliveryDocument, /BetterGov DPWH dataset and API/);
  assert.match(deliveryDocument, /aria-label="Dossier sections"/);
  assert.match(deliveryDocument, /Procurement timeline/);
  assert.match(deliveryDocument, /Contract evidence checklist/);
  assert.match(deliveryDocument, /Contract outcome pack/);
  assert.match(deliveryDocument, /COA audit evidence/);
  assert.match(deliveryDocument, /Identifiers and archived source fingerprints/);
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
  assert.match(document, /What do COA reports say about the projects Busisi checked/);
  assert.match(document, /Not finding a report is not the same as COA clearance/);
  assert.match(document, /DPWH reviewed annual audit report/);
  assert.match(document, /class="record-title-link"/);

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
  assert.match(document, /What contract documents can Busisi find/);
  assert.match(document, /1 of 2 project files have evidence/);
  assert.match(document, /PhilGEPS bid notice 123/);
  assert.match(document, /A missing document does not mean procurement did not happen/);
  assert.match(document, /class="record-title-link"/);

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
  assert.match(deskDocument, /Do the contract records agree/);
  assert.match(deskDocument, /Awardee not established by acquired procurement evidence/);
  assert.match(deskDocument, /Questions to check, not findings/);

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
  assert.match(document, /1 of 1 project files have evidence/);
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
  assert.match(desk, /0 project files checked/);
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
    ['/records/integrity/25O00113%3Amissing_coordinate/', /1 other flag on this contract/],
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
    if (path.includes('missing_coordinate')) {
      assert.match(document, /What we noticed:<\/b> No archived image reference\./);
    }
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

test('serves gated coverage status through the API and public page', async (context) => {
  const database = new LocalD1();
  context.after(() => database.close());

  const status = await getCoverageStatus(database);
  assert.equal(status.universe_contracts, 36748);
  assert.equal(status.verified_images, 5);
  const sourceStatus = await getSourceMonitorStatus(database);
  assert.equal(sourceStatus.status, 'unchanged');
  assert.equal(sourceStatus.limitations.length, 1);

  const api = await worker.fetch(request('/api/v1/coverage-status'), environment(database));
  assert.equal(api.status, 200);
  assert.equal((await api.json()).data.conflict_contracts, 1);

  const sourceApi = await worker.fetch(
    request('/api/v1/source-monitor-status'), environment(database),
  );
  assert.equal(sourceApi.status, 200);
  const sourceBody = await sourceApi.json();
  assert.equal(sourceBody.meta.review_scope, 'automated_source_revision_monitor');
  assert.equal(sourceBody.data.status, 'unchanged');
  assert.equal(sourceBody.data.observations_sha256, 'f'.repeat(64));

  const pageResponse = await siteWorker.fetch(request('/coverage/'), environment(database));
  assert.equal(pageResponse.status, 200);
  const pageDocument = await pageResponse.text();
  assert.match(pageDocument, /See how many project images Busisi has checked/);
  assert.match(pageDocument, /36,748/);
  assert.match(pageDocument, /No AI model decides whether an image is published/);
  assert.match(pageDocument, /The checked sources have not changed/);
  assert.match(pageDocument, /Commission on Audit report catalogues/);
});

test('renders unavailable and drifted source-monitor coverage states', () => {
  assert.match(coverageStatusBody(null), /No checked coverage update is available/);
  const coverage = {
    universe_contracts: 0,
    completed_contracts: 0,
    verified_exact_contracts: 0,
    no_image_contracts: 0,
    conflict_contracts: 0,
    pending_contracts: 0,
    retry_contracts: 0,
    verified_images: 0,
    quarantined_images: 0,
    released_at: '2026-11-04T00:00:00+00:00',
    release_id: 'release',
    source_sha256: 'source',
  };
  assert.match(coverageStatusBody(coverage), /No new source check is available/);
  const drifted = coverageStatusBody(coverage, {
    status: 'drift_detected',
    checked_at: '2026-11-04T00:00:00+00:00',
    differences: ['PCAB table changed'],
    limitations: [],
    observations_sha256: 'fingerprint',
  });
  assert.match(drifted, /A source changed and needs checking/);
  assert.match(drifted, /1 change or download problem needs checking/);
  assert.match(drifted, /No other source limit was reported/);
});
