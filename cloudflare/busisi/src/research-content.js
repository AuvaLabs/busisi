import {
  fy2027StageChangesRelease,
  multipurposeBuildingsRelease,
  researchCatalogue,
} from './research-data.js';

const escapeHtml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const number = (value) => new Intl.NumberFormat('en-PH').format(value);
const money = (centavos) => new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
  maximumFractionDigits: 2,
}).format(centavos / 100);
const compactMoney = (centavos) => new Intl.NumberFormat('en-PH', {
  style: 'currency',
  currency: 'PHP',
  notation: 'compact',
  maximumFractionDigits: 2,
}).format(centavos / 100);

const claimMap = new Map(multipurposeBuildingsRelease.claims.map((claim) => [claim.id, claim]));
const claim = (id) => claimMap.get(id);

const statusLabel = (value) => ({
  published: 'Published',
  verified: 'Verified calculation',
  source_reported: 'Source-reported',
  review_candidate: 'Needs verification',
  partial: 'Partial answer',
  evidence_gap: 'Evidence gap',
}[value] || value.replaceAll('_', ' '));

const researchCard = (record) => `<article class="research-card">
  <header><span>${escapeHtml(statusLabel(record.status))}</span><time datetime="${escapeHtml(record.published_at)}">Published ${escapeHtml(record.published_at)}</time></header>
  <h2><a href="/research/${escapeHtml(record.slug)}/">${escapeHtml(record.headline)}</a></h2>
  <p>${escapeHtml(record.summary)}</p>
  <dl><div><dt>Data cutoff</dt><dd>${escapeHtml(record.data_cutoff)}</dd></div><div><dt>Release</dt><dd>Version ${number(record.version)}</dd></div></dl>
  <a class="research-action" href="/research/${escapeHtml(record.slug)}/">Read the investigation</a>
</article>`;

export const researchIndexBody = `
  <section class="research-index-intro"><p class="kicker">Research and investigations</p><h1>One public question. An inspectable answer.</h1><p class="lede">Busisi publishes dated research built from acquired public records. Every release identifies its calculations, evidence state, source cutoff, limitations, and correction path.</p></section>
  <section class="research-index-guide" aria-label="How to read Busisi research"><article><span>01</span><h2>Question</h2><p>Start with a question that matters to Filipino citizens.</p></article><article><span>02</span><h2>Investigation</h2><p>Test the available records and preserve what cannot be established.</p></article><article><span>03</span><h2>Evidence</h2><p>Let readers inspect the data, examples, sources, and limits.</p></article></section>
  <section class="research-list" aria-labelledby="published-research"><div><p class="kicker">Published work</p><h2 id="published-research">Current investigations</h2></div>${researchCatalogue.map(researchCard).join('')}</section>
  <section class="research-boundary"><div><p class="kicker">Publication boundary</p><h2>Drafts are not findings.</h2></div><p>Unpublished topic queues, working notes, rejected leads, scripts, and production instructions are kept outside this public library. A page appears here only after its data and claims pass the release checks.</p></section>`;

const regionRows = multipurposeBuildingsRelease.chart_data.regions.map((region) => `<tr>
  <th scope="row">${escapeHtml(region.region)}</th><td>${number(region.ongoing)}</td><td>${number(region.active_pipeline)}</td><td>${number(region.completed)}</td><td>${compactMoney(region.recorded_budget_centavos)}</td>
</tr>`).join('');

const workLabels = {
  construction_newness_unstated: 'Construction, newness not stated',
  completion_or_later_phase: 'Completion or later phase',
  repair_or_improvement: 'Repair or improvement',
  explicitly_new: 'Explicitly new',
  replacement_or_reconstruction: 'Replacement or reconstruction',
  unclear: 'Unclear from title',
};
const workRows = Object.entries(multipurposeBuildingsRelease.chart_data.work_types).map(([key, record]) => `<tr>
  <th scope="row">${escapeHtml(workLabels[key])}</th><td>${number(record.count)}</td><td>${compactMoney(record.recorded_budget_centavos)}</td>
</tr>`).join('');

const districtRows = multipurposeBuildingsRelease.chart_data.district_offices.slice(0, 15).map((record) => `<tr>
  <th scope="row">${escapeHtml(record.label)}</th><td>${number(record.active_pipeline)}</td><td>${compactMoney(record.recorded_budget_centavos)}</td>
</tr>`).join('');

const cityRows = multipurposeBuildingsRelease.chart_data.explicit_cities.slice(0, 12).map((record) => `<tr>
  <th scope="row">${escapeHtml(record.city)}</th><td>${number(record.active_pipeline)}</td>
</tr>`).join('');

const investigationCards = multipurposeBuildingsRelease.investigations.map((record) => `<article>
  <span>${escapeHtml(statusLabel(record.state))}</span><h3>${escapeHtml(record.question)}</h3><p>${escapeHtml(record.result)}</p><small>${escapeHtml(record.calculation_id)}</small>
</article>`).join('');

const exampleRows = multipurposeBuildingsRelease.project_examples.largest_active_recorded_budgets.slice(0, 8).map((record) => `<tr>
  <th scope="row"><a href="${escapeHtml(record.reader_url)}">${escapeHtml(record.contract_id)}</a><small>${escapeHtml(record.description)}</small></th><td>${escapeHtml(record.region)}</td><td>${escapeHtml(record.status)}</td><td>${money(record.recorded_budget_centavos)}</td>
</tr>`).join('');

const pricing = multipurposeBuildingsRelease.chart_data.pricing;
const ongoing = claim('mpb-ongoing');
const pipeline = claim('mpb-active-pipeline');
const existing = claim('mpb-existing-work-wording');
const activeBudget = claim('mpb-active-budget');
const coordinateCandidates = claim('mpb-prior-coordinate-candidates');
const releaseSource = multipurposeBuildingsRelease.sources[0];

export const multipurposeBuildingsBody = `
  <article class="research-article">
    <header class="research-hero"><div><p class="kicker">Infrastructure investigation</p><h1>How many multipurpose buildings are being built?</h1><p class="lede">At least <strong>${number(ongoing.value)}</strong> conservatively classified records are marked On-Going. Busisi examined where they appear, how the work is described, what the recorded amounts say, and what the source still cannot prove.</p></div><aside><span>Release v${number(multipurposeBuildingsRelease.manifest.version)}</span><dl><div><dt>Published</dt><dd>${escapeHtml(multipurposeBuildingsRelease.manifest.published_at)}</dd></div><div><dt>Data cutoff</dt><dd>${escapeHtml(multipurposeBuildingsRelease.manifest.data_cutoff)}</dd></div><div><dt>Method</dt><dd>${escapeHtml(multipurposeBuildingsRelease.manifest.methodology_version)}</dd></div></dl></aside></header>

    <section class="research-answer" aria-labelledby="direct-answer"><div><p class="kicker">Direct answer</p><h2 id="direct-answer">The source reports a large active pipeline.</h2><p>${escapeHtml(ongoing.statement)} The wider pipeline reaches ${number(pipeline.value)} records when For Procurement and Not Yet Started are included. These are records and source statuses, not independently counted buildings or verified present-day construction sites.</p></div><div class="research-metrics"><article><span>Marked ongoing</span><strong>${number(ongoing.value)}</strong><small>Source-reported status</small></article><article><span>Active pipeline</span><strong>${number(pipeline.value)}</strong><small>Ongoing, procurement, or not started</small></article><article><span>Recorded active budget</span><strong>${compactMoney(activeBudget.value)}</strong><small>Not payment or final cost</small></article><article><span>Existing-work wording</span><strong>${number(existing.value)}</strong><small>Completion, phase, repair, or replacement</small></article></div></section>

    <section class="research-section" id="investigation"><div class="research-heading"><p class="kicker">What we investigated</p><h2>Four questions, with four different evidence limits.</h2></div><div class="investigation-grid">${investigationCards}</div></section>

    <section class="research-section split-section" id="work-type"><div><p class="kicker">New or existing work?</p><h2>Most titles do not explicitly say “new.”</h2><p>Construction by itself does not establish that no structure existed before. Completion, phase, repair, rehabilitation, improvement, replacement, and reconstruction language indicates work on an existing or partly built asset.</p></div><div class="research-table-wrap"><table><thead><tr><th>Title classification</th><th>Active records</th><th>Recorded budget</th></tr></thead><tbody>${workRows}</tbody></table></div></section>

    <section class="research-section" id="regions"><div class="research-heading"><p class="kicker">Where the records point</p><h2>Region totals reconcile to the national result.</h2><p>District-office labels come from the source. They are not legislative-boundary determinations.</p></div><div class="research-table-wrap"><table class="region-table"><thead><tr><th>Region</th><th>On-Going</th><th>Pipeline</th><th>Completed</th><th>Pipeline budget</th></tr></thead><tbody>${regionRows}</tbody></table></div></section>

    <section class="research-section location-breakdown" id="local-breakdown"><div><p class="kicker">DPWH district-office labels</p><h2>Highest active counts in the source.</h2><div class="research-table-wrap"><table><thead><tr><th>District-office label</th><th>Pipeline</th><th>Recorded budget</th></tr></thead><tbody>${districtRows}</tbody></table></div><p class="table-note">These are administrative source labels. They do not assign project authorship, sponsorship, control, or responsibility.</p></div><div><p class="kicker">Explicit city labels</p><h2>Partial city coverage only.</h2><div class="research-table-wrap"><table><thead><tr><th>City stated in title</th><th>Pipeline</th></tr></thead><tbody>${cityRows}</tbody></table></div><p class="table-note">City names were explicit in only ${number(multipurposeBuildingsRelease.chart_data.explicit_city_coverage.classified)} of ${number(multipurposeBuildingsRelease.chart_data.explicit_city_coverage.active)} active titles. This is not a complete nationwide city ranking.</p></div></section>

    <section class="research-section split-section" id="pricing"><div><p class="kicker">Recorded pricing</p><h2>The median alone cannot tell us what is expensive.</h2><p>${number(pricing.positive_budget_records)} active records have a positive recorded budget. ${number(pricing.zero_budget_records)} records, all held at a source stage without a positive amount in this release, cannot support pricing comparisons.</p></div><div class="pricing-scale"><div><span>25th percentile</span><strong>${money(pricing.p25_centavos)}</strong></div><div><span>Median</span><strong>${money(pricing.median_centavos)}</strong></div><div><span>75th percentile</span><strong>${money(pricing.p75_centavos)}</strong></div><div><span>90th percentile</span><strong>${money(pricing.p90_centavos)}</strong></div><p>A fair comparison still needs facility type, floor area, materials, number of floors, scope, year, and location.</p></div></section>

    <section class="research-section evidence-callout" id="existing"><div><p class="kicker">Existing at the location?</p><h2>${number(coordinateCandidates.value)} records need a closer location review.</h2><p>${escapeHtml(coordinateCandidates.statement)} Those matches cover ${number(multipurposeBuildingsRelease.chart_data.evidence.candidate_coordinates)} exact coordinates.</p></div><aside><strong>What this does not establish</strong><p>An exact coordinate can be reused for a later phase, a nearby structure, a central barangay point, or an incorrect source location. Physical existence needs dated imagery, inspection, completion, acceptance, asset-registry, or field evidence.</p></aside></section>

    <section class="research-section" id="examples"><div class="research-heading"><p class="kicker">Records to inspect</p><h2>Largest recorded active budgets in this classified set.</h2><p>These examples show why raw amount rankings are not price verdicts. Open each project dossier before comparing scope.</p></div><div class="research-table-wrap"><table class="example-table"><thead><tr><th>Contract and description</th><th>Region</th><th>Status</th><th>Recorded budget</th></tr></thead><tbody>${exampleRows}</tbody></table></div></section>

    <section class="research-section research-sources" id="sources"><div><p class="kicker">Evidence source</p><h2>Where the records came from.</h2><p>The records originated from the ${escapeHtml(releaseSource.publisher)} transparency system and were accessed through ${escapeHtml(releaseSource.access_provider)} as a curated extract. Busisi archived the exact acquired file and verified its SHA-256 identity before calculating any result.</p><p>Research tools may help locate documents, but search result pages are never used as evidence. Busisi records the underlying publisher and document instead.</p></div><aside class="research-source-card"><span>Source register</span><dl><div><dt>Publisher</dt><dd>${escapeHtml(releaseSource.publisher)}</dd></div><div><dt>Accessed through</dt><dd>${escapeHtml(releaseSource.access_provider)}</dd></div><div><dt>Source modified</dt><dd>${escapeHtml(releaseSource.modified)}</dd></div><div><dt>Retrieved</dt><dd>${escapeHtml(releaseSource.retrieved_at)}</dd></div></dl><a href="${escapeHtml(releaseSource.origin_url)}" target="_blank" rel="noopener noreferrer">Visit the DPWH Transparency Portal</a><a href="${escapeHtml(releaseSource.source_url)}" target="_blank" rel="noopener noreferrer">Open the archived source dataset</a></aside></section>

    <section class="research-section research-method" id="method"><div><p class="kicker">Reproduce the result</p><h2>The article and downstream editorial package use the same release.</h2><p>The classifier first removes generic “multipurpose buildings/facilities” program headings, then counts only titles where the project itself still names a multipurpose building. Every payload is hashed in the release manifest.</p><dl><div><dt>Source artifact</dt><dd><code>${escapeHtml(multipurposeBuildingsRelease.manifest.source_artifact_sha256)}</code></dd></div><div><dt>Package</dt><dd><code>${escapeHtml(multipurposeBuildingsRelease.manifest.package_sha256)}</code></dd></div></dl></div><div class="research-downloads"><a href="/data/research/multipurpose-buildings/v2/manifest.json">Download the research package</a><a href="/data/research/multipurpose-buildings/v2/story.json">Download the finished story</a><a href="/data/research/multipurpose-buildings/v2/editorial-package.json">Open the consumption index</a><a href="/data/research/multipurpose-buildings/v2/chart-data.json">Download chart data</a><a href="/data/research/multipurpose-buildings/v2/claims.json">Download checked claims</a><a href="/methodology/">Read the full Busisi method</a></div></section>
  </article>`;

const stageClaimMap = new Map(fy2027StageChangesRelease.claims.map((item) => [item.id, item]));
const stageClaim = (id) => stageClaimMap.get(id);
const changeLabels = {
  house_only: 'House list only',
  nep_only: 'NEP list only',
  increased: 'Matched row increased',
  decreased: 'Matched row decreased',
  unchanged: 'Matched row unchanged',
  scope_review: 'Scope needs review',
};
const changeRows = Object.entries(fy2027StageChangesRelease.chart_data.change_types)
  .map(([key, item]) => `<tr><th scope="row">${escapeHtml(changeLabels[key])}</th><td>${number(item.count)}</td><td>${number(item.quarantined)}</td><td>${compactMoney(item.net_difference_centavos)}</td></tr>`)
  .join('');
const datasetRows = fy2027StageChangesRelease.chart_data.datasets
  .map((item) => `<tr><th scope="row">${escapeHtml(item.label)}</th><td>${number(item.records)}</td><td>${number(item.change_counts.house_only || 0)}</td><td>${number(item.quarantined)}</td><td>${compactMoney(item.net_difference_centavos)}</td></tr>`)
  .join('');
const stageExamples = fy2027StageChangesRelease.project_examples.largest_absolute_changes
  .slice(0, 6)
  .map((item) => `<tr><th scope="row"><a href="${escapeHtml(item.reader_url)}">${escapeHtml(item.title)}</a><small>${escapeHtml(item.dataset.toUpperCase())} · ${escapeHtml(item.region)}</small></th><td>${escapeHtml(changeLabels[item.change_type])}</td><td>${money(item.nep_centavos)}</td><td>${money(item.house_centavos)}</td></tr>`)
  .join('');

export const fy2027StageChangesBody = `
  <article class="research-article">
    <header class="research-hero"><div><p class="kicker">Budget-stage investigation</p><h1>What changed between the FY2027 NEP and House project lists?</h1><p class="lede">Busisi checked <strong>${number(stageClaim('stage-total-records').value)}</strong> rows across four project-level lists acquired for this release. The result shows where the documents differ. It does not assign authorship, motive, or wrongdoing.</p></div><aside><span>Release v${number(fy2027StageChangesRelease.manifest.version)}</span><dl><div><dt>Published</dt><dd>${escapeHtml(fy2027StageChangesRelease.manifest.published_at)}</dd></div><div><dt>Data cutoff</dt><dd>${escapeHtml(fy2027StageChangesRelease.manifest.data_cutoff)}</dd></div><div><dt>Scope</dt><dd>Four project lists</dd></div></dl></aside></header>

    <section class="research-answer" aria-labelledby="stage-answer"><div><p class="kicker">Direct answer</p><h2 id="stage-answer">The compared House lists are larger in total, but the records changed in several ways.</h2><p>${escapeHtml(stageClaim('stage-net-movement').statement)} This is proposed budget authority in four lists, not proof of releases, payments, completed work, or value delivered.</p></div><div class="research-metrics"><article><span>Rows compared</span><strong>${number(stageClaim('stage-total-records').value)}</strong><small>All four lists</small></article><article><span>House-list only</span><strong>${number(stageClaim('stage-house-only').value)}</strong><small>Document comparison label</small></article><article><span>Amount changed</span><strong>${number(stageClaim('stage-amount-changes').value)}</strong><small>Matched rows</small></article><article><span>Quarantined</span><strong>${number(stageClaim('stage-quarantined').value)}</strong><small>Not promoted as findings</small></article></div></section>

    <section class="research-section split-section"><div><p class="kicker">How to read this</p><h2>“House-list only” is not proof of an insertion.</h2><p>A row may look new because wording, grouping, scope, or matching changed. The ${number(stageClaim('stage-house-only').value)} source-classified rows are leads for document review. Even the ${number(stageClaim('stage-publishable-house-only').value)} rows that passed automated quarantine still need evidence review before any stronger conclusion.</p></div><aside class="research-source-card"><span>Safe conclusion</span><p>The documents differ.</p><span>Not established</span><p>Who requested a change, why it changed, whether it is improper, or whether money was released or spent.</p></aside></section>

    <section class="research-section"><div class="research-heading"><p class="kicker">Change ledger</p><h2>Every row belongs to a stated comparison class.</h2></div><div class="research-table-wrap"><table><thead><tr><th>Comparison class</th><th>Rows</th><th>Quarantined</th><th>Net document movement</th></tr></thead><tbody>${changeRows}</tbody></table></div></section>

    <section class="research-section"><div class="research-heading"><p class="kicker">Covered programs</p><h2>This is a four-list investigation, not the whole national budget.</h2></div><div class="research-table-wrap"><table><thead><tr><th>Project list</th><th>Rows</th><th>House-list only</th><th>Quarantined</th><th>Net movement</th></tr></thead><tbody>${datasetRows}</tbody></table></div></section>

    <section class="research-section"><div class="research-heading"><p class="kicker">Largest changes to inspect</p><h2>Open the row before drawing a conclusion.</h2><p>These examples rank absolute document movement. Size alone is not a red flag or evidence of wrongdoing.</p></div><div class="research-table-wrap"><table class="example-table"><thead><tr><th>Project record</th><th>Class</th><th>NEP amount</th><th>House amount</th></tr></thead><tbody>${stageExamples}</tbody></table></div></section>

    <section class="research-section evidence-callout"><div><p class="kicker">Evidence boundary</p><h2>${number(stageClaim('stage-quarantined').value)} rows are held back.</h2><p>Busisi does not turn ambiguous matches or scope-review rows into public findings. The comparison also stops before the Senate, bicameral conference, enacted GAA, release, procurement, payment, and implementation stages.</p></div><aside><strong>What to verify next</strong><p>Read the original project-list pages, confirm whether the scope is truly the same, then follow any surviving change through later official stages.</p></aside></section>

    <section class="research-section research-method"><div><p class="kicker">Reproduce the result</p><h2>The article, API, and editorial package share one immutable release.</h2><p>Busisi authenticated the archived overview and source documents, validated every page, and reconciled row counts and money totals before publication.</p><dl><div><dt>Source artifact</dt><dd><code>${escapeHtml(fy2027StageChangesRelease.manifest.source_artifact_sha256)}</code></dd></div><div><dt>Package</dt><dd><code>${escapeHtml(fy2027StageChangesRelease.manifest.package_sha256)}</code></dd></div></dl></div><div class="research-downloads"><a href="/data/research/fy2027-nep-house-changes/v1/manifest.json">Download the research package</a><a href="/data/research/fy2027-nep-house-changes/v1/story.json">Download the finished story</a><a href="/data/research/fy2027-nep-house-changes/v1/editorial-package.json">Open the consumption index</a><a href="/data/research/fy2027-nep-house-changes/v1/chart-data.json">Download chart data</a><a href="/changes/">Explore the change ledger</a><a href="/methodology/">Read the Busisi method</a></div></section>
  </article>`;
