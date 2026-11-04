import chartData from '../public/data/research/multipurpose-buildings/v1/chart-data.json' with { type: 'json' };
import claims from '../public/data/research/multipurpose-buildings/v1/claims.json' with { type: 'json' };
import findings from '../public/data/research/multipurpose-buildings/v1/findings.json' with { type: 'json' };
import investigations from '../public/data/research/multipurpose-buildings/v1/investigations.json' with { type: 'json' };
import limitations from '../public/data/research/multipurpose-buildings/v1/limitations.json' with { type: 'json' };
import manifest from '../public/data/research/multipurpose-buildings/v1/manifest.json' with { type: 'json' };
import projectExamples from '../public/data/research/multipurpose-buildings/v1/project-examples.json' with { type: 'json' };
import sources from '../public/data/research/multipurpose-buildings/v1/sources.json' with { type: 'json' };

export const multipurposeBuildingsRelease = Object.freeze({
  manifest,
  claims,
  findings,
  investigations,
  chart_data: chartData,
  project_examples: projectExamples,
  sources,
  limitations,
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
    summary: 'A source-bounded count of ongoing, planned, completed, repaired, and later-phase multipurpose-building records, with location and pricing limits kept visible.',
  },
]);
