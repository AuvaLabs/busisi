import chartData from '../public/data/research/multipurpose-buildings/v2/chart-data.json' with { type: 'json' };
import claims from '../public/data/research/multipurpose-buildings/v2/claims.json' with { type: 'json' };
import editorialPackage from '../public/data/research/multipurpose-buildings/v2/editorial-package.json' with { type: 'json' };
import findings from '../public/data/research/multipurpose-buildings/v2/findings.json' with { type: 'json' };
import investigations from '../public/data/research/multipurpose-buildings/v2/investigations.json' with { type: 'json' };
import limitations from '../public/data/research/multipurpose-buildings/v2/limitations.json' with { type: 'json' };
import manifest from '../public/data/research/multipurpose-buildings/v2/manifest.json' with { type: 'json' };
import projectExamples from '../public/data/research/multipurpose-buildings/v2/project-examples.json' with { type: 'json' };
import sources from '../public/data/research/multipurpose-buildings/v2/sources.json' with { type: 'json' };
import story from '../public/data/research/multipurpose-buildings/v2/story.json' with { type: 'json' };
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
    summary: 'A source-bounded count of ongoing, planned, completed, repaired, and later-phase multipurpose-building records, with location and pricing limits kept visible.',
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
]);
