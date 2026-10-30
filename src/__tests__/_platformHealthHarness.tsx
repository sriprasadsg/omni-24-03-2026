/**
 * Shared fixtures for the Phase 82 Platform health tests (82-12). The test files register the vi.mock calls.
 * The document follows GET /api/platform/autonomous-ops/health (82-08): everything the watchdog could not
 * read is null, and the on-call block carries only the channel type and booleans.
 */
import { vi } from 'vitest';
import { authFetch } from '../../services/apiService';

export const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
export const minutesAhead = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

/** 14:02 on the viewer's own clock, so the expected HH:MM does not depend on the test machine's time zone. */
export const AT_1402 = new Date(2026, 9, 30, 14, 2, 0).toISOString();
export const AT_0915 = new Date(2026, 9, 30, 9, 15, 0).toISOString();

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
