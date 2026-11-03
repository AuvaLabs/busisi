import {
  QueryError,
  exportRegisterCsv,
  getProject,
  parseRegisterQuery,
  queryRegister,
} from './query.js';
import {
  getExplorerStats,
  parseExplorerQuery,
  queryExplorer,
} from './explorer-query.js';
import { getChangeStats, parseChangeQuery, queryChanges } from './change-query.js';
import {
  getAgencyBudgetSummary,
  parseAgencyQuery,
  queryAgencyBudgets,
} from './agency-budget-query.js';
import {
  getPublicValueSummary,
  queryPublicValueIndicators,
} from './public-value-query.js';
import {
  getBudgetCycleSummary,
  queryBudgetCycleDocuments,
} from './budget-cycle-query.js';
import { getCoaSummary, queryCoaReports } from './coa-query.js';
import {
  exportReviewCsv,
  getReviewSummary,
  parseReviewQuery,
  queryReviewConcentrations,
  queryReviewRankings,
} from './review-query.js';
import {
  exportIntegrityCsv,
  getIntegritySummary,
  parseConcentrationQuery,
  parseContractorQuery,
  parseIntegrityQuery,
  queryContractors,
  queryContractorConcentrations,
  queryIntegritySignals,
} from './integrity-query.js';

const API_PREFIX = '/api/v1/projects';
const MAX_SLUG_LENGTH = 160;
const EXPLORER_PATHS = Object.freeze({
  '/api/v1/budgets': 'budgets',
  '/api/v1/delivery': 'delivery',
  '/api/v1/candidates': 'candidates',
});

const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
});

const secure = (response, isApi) => {
  const secured = new Response(response.body, response);
  secured.headers.set('Cache-Control', isApi ? 'public, max-age=60' : 'public, max-age=300');
  secured.headers.set(
    'Content-Security-Policy',
    "default-src 'self'; base-uri 'none'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'",
  );
  secured.headers.set('Permissions-Policy', 'camera=(), geolocation=(), microphone=()');
  secured.headers.set('Referrer-Policy', 'no-referrer');
  secured.headers.set('X-Content-Type-Options', 'nosniff');
  secured.headers.set('X-Frame-Options', 'DENY');
  return secured;
};

const rateLimit = async (request, environment) => {
  if (!environment.PUBLIC_API_RATE_LIMITER) return true;
  const client = request.headers.get('CF-Connecting-IP') || 'local-preview';
  const result = await environment.PUBLIC_API_RATE_LIMITER.limit({ key: client });
  return result.success;
};

const apiResponse = async (request, environment, url) => {
  if (!(await rateLimit(request, environment))) {
    return jsonResponse({ detail: 'too many requests' }, 429);
  }
  if (request.method !== 'GET') {
    return jsonResponse({ detail: 'method not allowed' }, 405);
  }
  if (url.pathname === '/healthz') {
    return jsonResponse({ ok: true, service: 'busisi-publication', read_only: true });
  }
  if (url.pathname === '/api/v1/stats') {
    return jsonResponse({ data: await getExplorerStats(environment.DB) });
  }
  if (url.pathname === '/api/v1/change-stats') {
    return jsonResponse({ data: await getChangeStats(environment.DB) });
  }
  if (url.pathname === '/api/v1/agency-budget-summary') {
    return jsonResponse({ data: await getAgencyBudgetSummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/agency-budgets') {
    const query = parseAgencyQuery(url);
    const page = await queryAgencyBudgets(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        review_scope: 'reconciled_appropriation_head_totals',
      },
      data: page.records,
    });
  }
  if (url.pathname === '/api/v1/public-value-summary') {
    return jsonResponse({ data: await getPublicValueSummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/public-value-indicators') {
    return jsonResponse({
      meta: { review_scope: 'official_dbm_fiscal_program' },
      data: await queryPublicValueIndicators(environment.DB),
    });
  }
  if (url.pathname === '/api/v1/budget-cycle') {
    return jsonResponse({ data: await getBudgetCycleSummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/budget-cycle/documents') {
    const records = await queryBudgetCycleDocuments(environment.DB);
    return jsonResponse({
      meta: {
        total: records.length,
        review_scope: 'source_separated_budget_cycle_catalogue',
      },
      data: records,
    });
  }
  if (url.pathname === '/api/v1/coa-summary') {
    return jsonResponse({ data: await getCoaSummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/coa-reports') {
    const records = await queryCoaReports(environment.DB);
    return jsonResponse({
      meta: { total: records.length, review_scope: 'official_coa_report_catalogue' },
      data: records,
    });
  }
  if (url.pathname === '/api/v1/changes') {
    const query = parseChangeQuery(url);
    const page = await queryChanges(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        review_scope: 'provisional_stage_comparisons',
      },
      data: page.records,
    });
  }
  if (url.pathname === '/api/v1/review-summary') {
    return jsonResponse({ data: await getReviewSummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/review-rankings') {
    const query = parseReviewQuery(url);
    const page = await queryReviewRankings(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        review_scope: 'deterministic_review_candidates',
      },
      data: page.records,
    });
  }
  if (url.pathname === '/api/v1/review-concentrations') {
    const query = parseReviewQuery(url);
    return jsonResponse({
      meta: { review_scope: 'deterministic_aggregate' },
      data: await queryReviewConcentrations(environment.DB, query),
    });
  }
  if (url.pathname === '/api/v1/review.csv') {
    const query = parseReviewQuery(url);
    const document = await exportReviewCsv(environment.DB, query);
    return new Response(document, {
      headers: {
        'Content-Disposition': 'attachment; filename=busisi-review-candidates.csv',
        'Content-Type': 'text/csv; charset=utf-8',
      },
    });
  }
  if (url.pathname === '/api/v1/integrity-summary') {
    return jsonResponse({ data: await getIntegritySummary(environment.DB) });
  }
  if (url.pathname === '/api/v1/integrity-signals') {
    const query = parseIntegrityQuery(url);
    const page = await queryIntegritySignals(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        review_scope: 'deterministic_source_review',
      },
      data: page.records,
    });
  }
  if (url.pathname === '/api/v1/integrity.csv') {
    const query = parseIntegrityQuery(url);
    const document = await exportIntegrityCsv(environment.DB, query);
    return new Response(document, {
      headers: {
        'Content-Disposition': 'attachment; filename=busisi-project-integrity-signals.csv',
        'Content-Type': 'text/csv; charset=utf-8',
      },
    });
  }
  if (url.pathname === '/api/v1/contractors') {
    const query = parseContractorQuery(url);
    const page = await queryContractors(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        review_scope: 'archived_dpwh_contract_aggregation',
      },
      data: page.records,
    });
  }
  if (url.pathname === '/api/v1/contractor-concentrations') {
    const query = parseConcentrationQuery(url);
    return jsonResponse({
      meta: {
        review_scope: 'archived_dpwh_party_association_concentration',
        denominator: 'contractor_party_associations',
      },
      data: await queryContractorConcentrations(environment.DB, query),
    });
  }
  const collection = EXPLORER_PATHS[url.pathname];
  if (collection) {
    const query = parseExplorerQuery(url, collection);
    const page = await queryExplorer(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        review_scope: collection === 'candidates' ? 'unreviewed_candidates' : 'official_source_records',
      },
      data: page.records,
    });
  }
  const query = parseRegisterQuery(url);
  if (url.pathname === API_PREFIX) {
    const page = await queryRegister(environment.DB, query);
    return jsonResponse({
      meta: {
        total: page.total,
        count: page.records.length,
        limit: query.limit,
        next_cursor: page.nextCursor,
        release_scope: 'reviewed_golden_set',
      },
      data: page.records,
    });
  }
  if (url.pathname === `${API_PREFIX}.csv`) {
    const document = await exportRegisterCsv(environment.DB, query);
    return new Response(document, {
      headers: {
        'Content-Disposition': 'attachment; filename=busisi-project-records.csv',
        'Content-Type': 'text/csv; charset=utf-8',
      },
    });
  }
  const slug = decodeURIComponent(url.pathname.slice(`${API_PREFIX}/`.length));
  if (!/^[a-z0-9-]+$/.test(slug) || slug.length > MAX_SLUG_LENGTH) {
    return jsonResponse({ detail: 'project not found' }, 404);
  }
  const dossier = await getProject(environment.DB, slug);
  return dossier
    ? jsonResponse({ data: dossier })
    : jsonResponse({ detail: 'project not found' }, 404);
};

const isApiPath = (pathname) => pathname === '/healthz' || pathname.startsWith('/api/');

export default {
  async fetch(request, environment) {
    const url = new URL(request.url);
    const api = isApiPath(url.pathname);
    try {
      const response = api
        ? await apiResponse(request, environment, url)
        : await environment.ASSETS.fetch(request);
      return secure(response, api);
    } catch (error) {
      if (error instanceof QueryError) {
        return secure(jsonResponse({ detail: error.message }, error.status), true);
      }
      console.error('Busisi request failed', error);
      return secure(jsonResponse({ detail: 'service unavailable' }, 503), api);
    }
  },
};
