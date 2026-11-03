// Run with k6, not Node.js. See LOAD_BALANCING.md, Phase 5.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

function integer(name, fallback, minimum, maximum) {
  const value = Number(__ENV[name] === undefined ? fallback : __ENV[name]);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${maximum}`);
  }
  return value;
}

const PROFILE = __ENV.PROFILE || 'smoke';
if (!['smoke', 'autoscale'].includes(PROFILE)) throw new Error('PROFILE must be smoke or autoscale');
const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:5007').replace(/\/+$/, '');
const EXPECTED_VERSION = (__ENV.EXPECTED_VERSION || '').trim();
const EXPECTED_COMMIT = (__ENV.EXPECTED_COMMIT || '').trim();
if (!EXPECTED_VERSION || !EXPECTED_COMMIT) {
  throw new Error('Set EXPECTED_VERSION and EXPECTED_COMMIT to the deployed image identities');
}
const MAX_VUS = integer('MAX_VUS', 100, 10, 1000);
const MID_VUS = integer('MID_VUS', 50, 10, MAX_VUS);
const HOLD_SECONDS = integer('HOLD_SECONDS', 180, 60, 1800);
const COOLDOWN_SECONDS = integer('COOLDOWN_SECONDS', 180, 120, 900);
const THINK_SECONDS = Number(__ENV.THINK_SECONDS === undefined ? 0.1 : __ENV.THINK_SECONDS);
if (!Number.isFinite(THINK_SECONDS) || THINK_SECONDS < 0 || THINK_SECONDS > 10) {
  throw new Error('THINK_SECONDS must be a number from 0 to 10');
}
const P95_MS = integer('P95_MS', 1000, 1, 60000);
const REPORT_PATH = __ENV.REPORT_PATH || '.artifacts/k6/summary.json';
const stages = [
  { duration: '30s', target: 10 },
  { duration: '30s', target: 10 },
  { duration: '30s', target: MID_VUS },
  { duration: '120s', target: MID_VUS },
  { duration: '30s', target: MAX_VUS },
  { duration: `${HOLD_SECONDS}s`, target: MAX_VUS },
  { duration: '30s', target: 0 },
  { duration: `${COOLDOWN_SECONDS}s`, target: 0 },
];

export const options = {
  scenarios: PROFILE === 'smoke'
    ? { smoke: { executor: 'constant-vus', vus: 2, duration: '15s', gracefulStop: '5s' } }
    : { autoscale: {
      executor: 'ramping-vus', startVUs: 0, stages,
      gracefulRampDown: '5s', gracefulStop: '5s',
    } },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    http_req_duration: [`p(95)<${P95_MS}`],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
  userAgent: 'CalFit-k6-lab',
};

const backendResponses = new Counter('backend_responses');
const metricPayload = { units: 'metric', age: 30, height: 180, weight: 80 };
const caloriePayload = { ...metricPayload, sex: 'male', activity: 'moderate' };
const cases = [
  { path: '/api/fitness', payload: caloriePayload, bmi: true, calories: true },
  { path: '/api/bmi', payload: metricPayload, bmi: true, calories: false },
  { path: '/api/calories', payload: caloriePayload, bmi: false, calories: true },
];

// Fail early if the tunnel points to the wrong deployment or mixed image versions.
export function setup() {
  for (const path of ['/version', '/frontend-version.json']) {
    const response = http.get(BASE_URL + path, { timeout: '10s', tags: { name: path } });
    let body;
    try { body = response.json(); } catch (_) { body = null; }
    if (response.status !== 200 || !body || body.version !== EXPECTED_VERSION || body.commit !== EXPECTED_COMMIT) {
      throw new Error(`Identity preflight failed at ${path}; verify port-forward and expected version/commit`);
    }
  }
  console.log(`Starting ${PROFILE}: ${BASE_URL}; version ${EXPECTED_VERSION}; commit ${EXPECTED_COMMIT}`);
}

export default function () {
  const test = cases[__ITER % cases.length];
  const response = http.post(BASE_URL + test.path, JSON.stringify(test.payload), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '10s',
    tags: { name: test.path },
  });
  let body;
  try { body = response.json(); } catch (_) { body = null; }
  const instance = response.headers['X-Instance-Id'] || response.headers['X-Instance-ID'];
  check(response, {
    'HTTP 200': r => r.status === 200,
    'JSON response': r => (r.headers['Content-Type'] || '').includes('application/json') && body !== null,
    'backend instance present': () => typeof instance === 'string' && instance.length > 0,
    'correct normalised measurements': () => body?.measurements?.weight_kg === 80 && body?.measurements?.height_cm === 180,
    'correct BMI contract': () => test.bmi
      ? body?.bmi?.value === 24.69 && body?.bmi?.category === 'Healthy weight'
      : body !== null && !Object.prototype.hasOwnProperty.call(body, 'bmi'),
    'correct calorie contract': () => test.calories
      ? body?.calories?.resting_kcal === 1780 && body?.calories?.maintenance_kcal === 2759
        && body?.calories?.activity_factor === 1.55 && body?.calories?.activity === 'moderate'
      : body !== null && !Object.prototype.hasOwnProperty.call(body, 'calories'),
  }, { endpoint: test.path });
  if (instance) backendResponses.add(1, { instance, endpoint: test.path });
  if (THINK_SECONDS > 0) sleep(THINK_SECONDS);
}

export function handleSummary(data) {
  const metrics = data.metrics || {};
  const values = name => metrics[name]?.values || {};
  const failedThresholds = [];
  for (const [metric, result] of Object.entries(metrics)) {
    for (const [expression, threshold] of Object.entries(result.thresholds || {})) {
      if (!threshold.ok) failedThresholds.push(`${metric}: ${expression}`);
    }
  }
  const summary = {
    generated_at: new Date().toISOString(),
    target: BASE_URL,
    expected_version: EXPECTED_VERSION,
    expected_commit: EXPECTED_COMMIT,
    profile: PROFILE,
    configuration: {
      max_vus: PROFILE === 'smoke' ? 2 : MAX_VUS,
      think_seconds: THINK_SECONDS,
      stages: PROFILE === 'autoscale' ? stages : null,
      p95_target_ms: P95_MS,
    },
    results: {
      requests: values('http_reqs').count,
      throughput_rps: values('http_reqs').rate,
      http_failure_rate: values('http_req_failed').rate,
      check_pass_rate: values('checks').rate,
      p95_ms: values('http_req_duration')['p(95)'],
      failed_thresholds: failedThresholds,
    },
    evidence_scope: 'HTTP results only. Record HPA events, CPU metrics and pod counts separately to prove autoscaling.',
    k6_summary: data,
  };
  const line = value => value === undefined ? 'unavailable' : String(value);
  const consoleSummary = [
    `CalFit k6 (${PROFILE})`,
    `Requests: ${line(summary.results.requests)}; throughput: ${line(summary.results.throughput_rps)} req/s`,
    `p95: ${line(summary.results.p95_ms)} ms; HTTP failure rate: ${line(summary.results.http_failure_rate)}`,
    `Check pass rate: ${line(summary.results.check_pass_rate)}`,
    `Failed thresholds: ${failedThresholds.length ? failedThresholds.join('; ') : 'none'}`,
    `Report: ${REPORT_PATH}`,
    summary.evidence_scope,
    '',
  ].join('\n');
  return { stdout: consoleSummary, [REPORT_PATH]: JSON.stringify(summary, null, 2) + '\n' };
}
