import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { parseChangeQuery } from '../src/change-query.js';
import { parseExplorerQuery } from '../src/explorer-query.js';
import worker from '../src/index.js';

const migrationPath = fileURLToPath(new URL('../migrations/0001_publication.sql', import.meta.url));
const explorerMigrationPath = fileURLToPath(
  new URL('../migrations/0002_public_explorer.sql', import.meta.url),
);
const changeMigrationPath = fileURLToPath(
  new URL('../migrations/0003_stage_changes.sql', import.meta.url),
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
    this.database.exec(readFileSync(seedPath, 'utf8'));
    this.database.exec(`
      INSERT INTO public_metadata VALUES ('budget_records', '2'), ('delivery_records', '2'), ('candidate_links', '2');
      INSERT INTO budget_items VALUES
        ('2025:pump', '18-001|pump', 2025, 'Construction of San Andres Pumping Station', 40000000000, 'family:pump', 'san andres pumping station', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        ('2024:road', '18-001|road', 2024, 'Maintenance, Repair and Rehabilitation of Infrastructure Facilities and Other Related Activities - Routine Maintenance of National Roads', 1000000000, 'family:road', 'routine maintenance of national roads', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
      INSERT INTO delivery_items VALUES
        ('25O00113', 2025, 'Construction of San Andres Pumping Station', 37679270658, 'Manila, NCR', 'GAA 2025', 'family:pump', 'san andres pumping station', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'),
        ('26ZERO01', 2026, 'Construction of Sample Health Center', 0, 'Cebu, Region VII', 'GAA 2026', 'family:health', 'sample health center', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
      INSERT INTO candidate_links VALUES
        ('2025:pump:25O00113', 2025, '18-001|pump', '25O00113', 'high', 90, '["year_match"]', 'Construction of San Andres Pumping Station', 'Construction of San Andres Pumping Station', 40000000000, 37679270658, 2320729342, 'https://budget.example/pump', 'https://dpwh.example/25O00113', 'candidate'),
        ('2026:health:26ZERO01', 2026, '18-001|health', '26ZERO01', 'candidate', 70, '["year_match"]', 'Construction of Sample Health Center', 'Construction of Sample Health Center', 2500000000, 0, 2500000000, 'https://budget.example/health', 'https://dpwh.example/26ZERO01', 'candidate');
      INSERT INTO stage_change_metadata VALUES
        ('record_count', '3'), ('quarantine_count', '1'), ('source_commit', '${'a'.repeat(40)}');
      INSERT INTO stage_change_items VALUES
        ('dpwh:1', 2027, 'dpwh', 'Sample bridge', 'Network Development', 'Bridge Program', 'Region III', 'Sample DEO', 'increased', 'Higher in the House bill', 'candidate', 0, 1, 10000, 15000, 5000, 'https://budget.example/1', 'https://budget.example/nep.pdf#page=1', 'https://budget.example/house.pdf#page=2', 1, 2, '${'a'.repeat(40)}', '${'b'.repeat(64)}'),
        ('hfep:2', 2027, 'hfep', 'Sample health center', 'HFEP', '', 'Region VII', 'DOH', 'house_only', 'In the House bill only', 'candidate', 0, 0, 0, 20000, 20000, 'https://budget.example/2', '', 'https://budget.example/house.pdf#page=3', NULL, 3, '${'a'.repeat(40)}', '${'c'.repeat(64)}'),
        ('dpwh:3', 2027, 'dpwh', 'Held road match', 'Road Program', '', 'NCR', 'Central Office', 'scope_review', 'Different scope', 'quarantine', 1, 0, 30000, 35000, 5000, 'https://budget.example/3', 'https://budget.example/nep.pdf#page=4', 'https://budget.example/house.pdf#page=5', 4, 5, '${'a'.repeat(40)}', '${'d'.repeat(64)}');
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
  assert.equal(deliveryBody.meta.total, 1);
  assert.equal(deliveryBody.data[0].contract_id, '25O00113');
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
    record_count: 3,
    quarantine_count: 1,
    source_commit: 'a'.repeat(40),
  });
  const changeBody = await changes.json();
  assert.equal(changeBody.meta.total, 1);
  assert.equal(changeBody.meta.review_scope, 'provisional_stage_comparisons');
  assert.equal(changeBody.data[0].record_id, 'dpwh:1');
  assert.equal((await quarantined.json()).data[0].record_id, 'dpwh:3');
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
