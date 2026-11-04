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
]);
