import chartData from '../public/data/research/multipurpose-buildings/v6/chart-data.json' with { type: 'json' };
import claims from '../public/data/research/multipurpose-buildings/v6/claims.json' with { type: 'json' };
import editorialPackage from '../public/data/research/multipurpose-buildings/v6/editorial-package.json' with { type: 'json' };
import findings from '../public/data/research/multipurpose-buildings/v6/findings.json' with { type: 'json' };
import investigations from '../public/data/research/multipurpose-buildings/v6/investigations.json' with { type: 'json' };
import limitations from '../public/data/research/multipurpose-buildings/v6/limitations.json' with { type: 'json' };
import manifest from '../public/data/research/multipurpose-buildings/v6/manifest.json' with { type: 'json' };
import projectExamples from '../public/data/research/multipurpose-buildings/v6/project-examples.json' with { type: 'json' };
import sources from '../public/data/research/multipurpose-buildings/v6/sources.json' with { type: 'json' };
import story from '../public/data/research/multipurpose-buildings/v6/story.json' with { type: 'json' };
import stageChartData from '../public/data/research/fy2027-nep-house-changes/v1/chart-data.json' with { type: 'json' };
import stageClaims from '../public/data/research/fy2027-nep-house-changes/v1/claims.json' with { type: 'json' };
import stageEditorialPackage from '../public/data/research/fy2027-nep-house-changes/v1/editorial-package.json' with { type: 'json' };
import stageFindings from '../public/data/research/fy2027-nep-house-changes/v1/findings.json' with { type: 'json' };
import stageInvestigations from '../public/data/research/fy2027-nep-house-changes/v1/investigations.json' with { type: 'json' };
import stageLimitations from '../public/data/research/fy2027-nep-house-changes/v1/limitations.json' with { type: 'json' };
import stageManifest from '../public/data/research/fy2027-nep-house-changes/v1/manifest.json' with { type: 'json' };
import stageProjectExamples from '../public/data/research/fy2027-nep-house-changes/v1/project-examples.json' with { type: 'json' };
import stageSources from '../public/data/research/fy2027-nep-house-changes/v1/sources.json' with { type: 'json' };
import stageStory from '../public/data/research/fy2027-nep-house-changes/v1/story.json' with { type: 'json' };
import concentrationChartData from '../public/data/research/fy2027-change-concentration/v1/chart-data.json' with { type: 'json' };
import concentrationClaims from '../public/data/research/fy2027-change-concentration/v1/claims.json' with { type: 'json' };
import concentrationEditorialPackage from '../public/data/research/fy2027-change-concentration/v1/editorial-package.json' with { type: 'json' };
import concentrationFindings from '../public/data/research/fy2027-change-concentration/v1/findings.json' with { type: 'json' };
import concentrationInvestigations from '../public/data/research/fy2027-change-concentration/v1/investigations.json' with { type: 'json' };
import concentrationLimitations from '../public/data/research/fy2027-change-concentration/v1/limitations.json' with { type: 'json' };
import concentrationManifest from '../public/data/research/fy2027-change-concentration/v1/manifest.json' with { type: 'json' };
import concentrationProjectExamples from '../public/data/research/fy2027-change-concentration/v1/project-examples.json' with { type: 'json' };
import concentrationSources from '../public/data/research/fy2027-change-concentration/v1/sources.json' with { type: 'json' };
import concentrationStory from '../public/data/research/fy2027-change-concentration/v1/story.json' with { type: 'json' };
import releaseHistory from '../public/data/research/release-history.json' with { type: 'json' };

export const multipurposeBuildingsRelease = Object.freeze({
  manifest,
  claims,
  findings,
  investigations,
  chart_data: chartData,
  project_examples: projectExamples,
  sources,
  limitations,
  story,
  editorial_package: editorialPackage,
});

export const fy2027StageChangesRelease = Object.freeze({
  manifest: stageManifest,
  claims: stageClaims,
  findings: stageFindings,
  investigations: stageInvestigations,
  chart_data: stageChartData,
  project_examples: stageProjectExamples,
  sources: stageSources,
  limitations: stageLimitations,
  story: stageStory,
  editorial_package: stageEditorialPackage,
});

export const fy2027ChangeConcentrationRelease = Object.freeze({
  manifest: concentrationManifest,
  claims: concentrationClaims,
  findings: concentrationFindings,
  investigations: concentrationInvestigations,
  chart_data: concentrationChartData,
  project_examples: concentrationProjectExamples,
  sources: concentrationSources,
  limitations: concentrationLimitations,
  story: concentrationStory,
  editorial_package: concentrationEditorialPackage,
});

export const researchReleaseHistory = Object.freeze(releaseHistory);

export const researchCatalogue = Object.freeze([
  {
    story_id: manifest.story_id,
    slug: manifest.slug,
    headline: manifest.headline,
    status: manifest.status,
    version: manifest.version,
    published_at: manifest.published_at,
    data_cutoff: manifest.data_cutoff,
    canonical_url: manifest.canonical_url,
    package_sha256: manifest.package_sha256,
    manifest_url: editorialPackage.manifest_url,
    story_url: editorialPackage.story_url,
    editorial_package_url: `${editorialPackage.package_base_url}/editorial-package.json`,
    summary: 'A source-bounded count and ₱88.79 billion active-pipeline reconciliation, with official procurement leads and conflicts clearly separated from verified evidence.',
  },
  {
    story_id: stageManifest.story_id,
    slug: stageManifest.slug,
    headline: stageManifest.headline,
    status: stageManifest.status,
    version: stageManifest.version,
    published_at: stageManifest.published_at,
    data_cutoff: stageManifest.data_cutoff,
    canonical_url: stageManifest.canonical_url,
    package_sha256: stageManifest.package_sha256,
    manifest_url: stageEditorialPackage.manifest_url,
    story_url: stageEditorialPackage.story_url,
    editorial_package_url: `${stageEditorialPackage.package_base_url}/editorial-package.json`,
    summary: 'A reconciled comparison of four FY2027 NEP and House project lists, separating document changes from claims the records cannot prove.',
  },
  {
    story_id: concentrationManifest.story_id,
    slug: concentrationManifest.slug,
    headline: concentrationManifest.headline,
    status: concentrationManifest.status,
    version: concentrationManifest.version,
    published_at: concentrationManifest.published_at,
    data_cutoff: concentrationManifest.data_cutoff,
    canonical_url: concentrationManifest.canonical_url,
    package_sha256: concentrationManifest.package_sha256,
    manifest_url: concentrationEditorialPackage.manifest_url,
    story_url: concentrationEditorialPackage.story_url,
    editorial_package_url: `${concentrationEditorialPackage.package_base_url}/editorial-package.json`,
    summary: 'A bounded ranking of where FY2027 project-list differences cluster by recorded program, region, office, and dataset labels.',
  },
]);
