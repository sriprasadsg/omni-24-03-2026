/**
 * Shared fixtures for the Phase 82 Platform health tests (82-12). The test files register the vi.mock calls.
 * The document follows GET /api/platform/autonomous-ops/health (82-08): everything the watchdog could not
 * read is null, and the on-call block carries only the channel type and booleans.
 */
import React from 'react';
import { vi } from 'vitest';
import { authFetch } from '../../services/apiService';
import { UserContext } from '../../contexts/UserContext';

export const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
export const minutesAhead = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

/** 14:02 on the viewer's own clock, so the expected HH:MM does not depend on the test machine's time zone. */
export const AT_1402 = new Date(2026, 9, 30, 14, 2, 0).toISOString();
export const AT_0915 = new Date(2026, 9, 30, 9, 15, 0).toISOString();

/** HH:MM on the viewer's own 24-hour clock, the way the component formats it. */
export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });

const GB = 1024 ** 3;
export const gb = (n: number) => n * GB;

export function service(id: string, over: Record<string, unknown> = {}) {
  const names: Record<string, string> = { mongod: 'MongoDB', 'omni-backend': 'Backend', nginx: 'nginx', ollama: 'Ollama' };
  return {
    id, name: names[id], unit: id, state: id === 'ollama' ? 'expected_off' : 'healthy', since: null,
    failedChecks: 0, restartsInWindow: 0, nextRestartAt: null, budgetReturnsAt: null, pagedAt: null,
    waitingOn: null, detail: null, stale: false, ...over,
  };
}

export function services(over: Record<string, Record<string, unknown>> = {}) {
  return ['mongod', 'omni-backend', 'nginx', 'ollama'].map(id => service(id, over[id] ?? {}));
}

export function cert(over: Record<string, unknown> = {}) {
  return {
    path: '/etc/nginx/ssl/omni.crt', notAfter: '2029-01-15T00:00:00Z', daysLeft: 800, rung: 0, pinned: true,
    error: null, stale: false, ...over,
  };
}

export function disk(over: Record<string, unknown> = {}) {
  return {
    mount: '/', paths: ['/', '/var/lib/mongodb'], usedPct: 62.4, freeBytes: gb(18.5), totalBytes: gb(50), rung: 0,
    forecast: { state: 'flat', days: null, rung: 0 }, stale: false, ...over,
  };
}

export function healthDoc(over: Record<string, unknown> = {}) {
  return {
    updatedAt: minutesAgo(1),
    host: 'omni-prod-01',
    watchdog: {
      state: 'running', lastSeenAt: minutesAgo(1), firstSeenAt: minutesAgo(5000), cadenceSeconds: 60, silentAfterSeconds: 300,
    },
    installChecklist: { path: 'deploy/omni-watchdog/INSTALL.md', url: null },
    stop: { effective: false, source: 'none' },
    services: services(),
    certs: [cert()],
    disks: [disk()],
    oncall: { type: 'pagerduty', heartbeatConfigured: true, status: 'working', last: { at: AT_1402, ok: true, error: null } },
    testAlert: null,
    ...over,
  };
}

/** A watchdog that has never reported: no services state, nothing measured. */
export function notInstalledDoc(over: Record<string, unknown> = {}) {
  return healthDoc({
    updatedAt: null, host: null,
    watchdog: { state: 'not_installed', lastSeenAt: null, firstSeenAt: null, cadenceSeconds: 60, silentAfterSeconds: 300 },
    services: ['mongod', 'omni-backend', 'nginx', 'ollama'].map(id => service(id, { state: null, stale: true })),
    certs: [], disks: [],
    oncall: { type: null, heartbeatConfigured: false, status: 'not_set_up', last: null },
    ...over,
  });
}

export function testAlert(over: Record<string, unknown> = {}) {
  return {
    id: 'ta-1', requestedAt: new Date().toISOString(), requestedBy: 'Pat', state: 'pending', sentAt: null, error: null,
    ...over,
  };
}

export const healthCalls = () =>
  mockAuthFetch.mock.calls.filter(c => (c[0] as string).split('?')[0] === '/api/platform/autonomous-ops/health');
export const testAlertCalls = () =>
  mockAuthFetch.mock.calls.filter(c => (c[0] as string).split('?')[0] === '/api/platform/autonomous-ops/health/test-alert');

// ── retention review (82-13) ─────────────────────────────────────────────────

export const REVIEW_PATH = '/api/platform/autonomous-ops/retention/review';
export const CONFIRM_PATH = '/api/platform/autonomous-ops/retention/confirm';

export function retentionItem(over: Record<string, unknown> = {}) {
  return {
    tenantId: 't1', tenantName: 'Acme Corp', type: 'agent_metrics', label: 'Agent metrics', collection: 'agent_metrics',
    days: 30, previousDays: null, count: 3, countError: null, countedAt: minutesAgo(10), reason: 'first_run', ...over,
  };
}

/** GET .../retention/review as 82-10 answers it; `items` default to two first-run rows (4 records, 2 organizations). */
export function retentionReview(over: Record<string, unknown> = {}) {
  const items = (over.items as unknown[] | undefined) ?? [
    retentionItem(),
    retentionItem({ tenantId: 't2', tenantName: 'Beta Ltd', type: 'logs', label: 'Logs', collection: 'logs', days: 90, count: 1 }),
  ];
  return {
    mode: 'counting_only', notCountedYet: false, nextRun: '2026-10-31T02:00:00+00:00',
    lastRun: { at: minutesAgo(600), trigger: 'scheduled', counted: 4, deleted: 0, tenants: 2, error: null, stoppedEarly: false },
    countedAt: minutesAgo(10), reviewToken: 'abc',
    totals: { records: 4, tenants: 2, rows: items.length, uncountable: 0 },
    items, total: items.length, nextOffset: null, incomplete: null,
    ...over,
  };
}

export const reviewCalls = () =>
  mockAuthFetch.mock.calls.filter(c => (c[0] as string).split('?')[0] === REVIEW_PATH);
export const confirmCalls = () =>
  mockAuthFetch.mock.calls.filter(c => (c[0] as string).split('?')[0] === CONFIRM_PATH);

export const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
export const SUPER_PERMISSIONS = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops', PLATFORM_CONTROL];

/** Render `ui` as a signed-in user holding exactly `permissions`. */
export function withUser(permissions: string[], ui: React.ReactElement) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Super Admin', tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p), enabledFeatures: [], serverLockedFeatures: {},
    }}>
      {ui}
    </UserContext.Provider>
  );
}

export type RetentionHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** Route authFetch by path; an unknown path fails loudly so a stray request shows up in the test. */
export function routeRetention(opts: { review?: RetentionHandler; confirm?: RetentionHandler } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === REVIEW_PATH) return (opts.review ?? (() => jsonRes(retentionReview())))(url, init);
    if (path === CONFIRM_PATH) return (opts.confirm ?? (() => jsonRes({ confirmed: { rows: 2, records: 4, tenants: 2 } })))(url, init);
    throw new Error(`unexpected request ${url}`);
  });
}
