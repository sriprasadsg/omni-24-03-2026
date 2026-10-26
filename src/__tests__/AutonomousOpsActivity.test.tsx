/**
 * Phase 81 / ACTV-01, ACTV-03: the read-only Autonomous Ops screen. The backend routes arrive
 * in 81-09, so authFetch is mocked and the payloads follow the contract in 81-07-PLAN.md.
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));

import { authFetch } from '../../services/apiService';
import { UserContext } from '../../contexts/UserContext';
import {
  AutonomousOpsStatusProvider,
  useAutonomousOpsStatus,
} from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

// ── fixtures ────────────────────────────────────────────────────────────────

const NOW = new Date('2026-10-25T12:00:00Z');
const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000).toISOString();

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'r1', bucket: 'done', state: 'done', createdAt: minutesAgo(12),
    actionLabel: 'Block IP address', classLine: 'Automatic',
    reasonText: 'Repeated failed sign-ins from one address', ruleId: 'rule.block_ip.bruteforce',
    host: 'web-01.example.com', target: '203.0.113.7', resultText: 'Blocked for 24 hours.',
    controlEvent: null,
    ...over,
  };
}

const DONE_ROW = row();
const SIM_ROW = row({
  id: 'r2', bucket: 'simulation', state: 'simulation', createdAt: minutesAgo(30),
  actionLabel: 'Isolate host', classLine: 'Needs approval',
  reasonText: 'Ransomware behaviour detected', ruleId: 'rule.isolate.ransomware',
  host: 'db-02.example.com', target: 'db-02',
  resultText: 'Nothing was done. This is what would have happened: the host would have been isolated from the network.',
});

function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

function platformStatusPayload() {
  return {
    scope: 'platform', stop: { platform: null }, tenantStopsCount: 0,
    canStopPlatform: true, canResumePlatform: true,
  };
}

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

type Handler = (url: string) => Response | Promise<Response>;

/** Route authFetch by path; unknown paths fail loudly so a stray request shows up in the test. */
function routeFetch(handlers: { status?: Handler; actions?: Handler; platformStatus?: Handler; platformActions?: Handler }) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (handlers.status ?? (() => jsonRes(statusPayload())))(url);
    if (path === '/api/autonomous-ops/actions') return (handlers.actions ?? (() => jsonRes({ items: [], nextCursor: null })))(url);
    if (path === '/api/platform/autonomous-ops/status') return (handlers.platformStatus ?? (() => jsonRes(platformStatusPayload())))(url);
    if (path === '/api/platform/autonomous-ops/actions') return (handlers.platformActions ?? (() => jsonRes({ items: [], nextCursor: null })))(url);
    throw new Error(`unexpected request ${url}`);
  });
}

const urlsOf = (suffix: string) =>
  mockAuthFetch.mock.calls.map(c => c[0] as string).filter(u => u.split('?')[0] === `/api${suffix}`);

function user(role: string) {
  return {
    id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a',
    permissions: ['view:autonomous_ops'],
  } as any;
}

function withUser(role: string, ui: React.ReactElement) {
  return (
    <UserContext.Provider value={{
      currentUser: user(role),
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false, hasPermission: () => true,
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      {ui}
    </UserContext.Provider>
  );
}

function screenFor(role: string, props: { tenantId?: string | null; onGoToTenants?: () => void; enabled?: boolean } = {}) {
  const { tenantId = null, onGoToTenants, enabled = true } = props;
  return withUser(
    role,
    <AutonomousOpsStatusProvider tenantId={tenantId} enabled={enabled}>
      <AutonomousOpsActivity tenantId={tenantId} onGoToTenants={onGoToTenants} />
    </AutonomousOpsStatusProvider>,
  );
}

beforeEach(() => { mockAuthFetch.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

// ── Task 1: tracer ──────────────────────────────────────────────────────────

describe('Autonomous Ops screen (tracer)', () => {
  it('shows the title, subtitle and both rows with what ran, why, target and result', async () => {
    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW, SIM_ROW], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));

    expect(screen.getByRole('heading', { level: 1, name: 'Autonomous Ops' })).toBeInTheDocument();
    expect(screen.getByText(
      'Automatic actions within limits you set. Riskier actions wait for your approval, and every decision is listed below.',
    )).toBeInTheDocument();

    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    for (const text of [
      'Repeated failed sign-ins from one address', 'rule.block_ip.bruteforce', 'web-01.example.com',
      '203.0.113.7', 'Blocked for 24 hours.', 'Isolate host', 'Needs approval', 'rule.isolate.ransomware',
    ]) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText('Automatic').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Done').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Simulation').length).toBeGreaterThan(0);
    expect(container.querySelector('[data-slot="autonomous-ops-status"]')).not.toBeNull();

    expect(urlsOf('/autonomous-ops/actions')[0]).toBe('/api/autonomous-ops/actions?bucket=all&limit=25');
  });

  it('renders every server string as text, never as markup', async () => {
    const hostile = '<img src=x onerror=alert(1)>';
    routeFetch({ actions: () => jsonRes({ items: [row({ reasonText: hostile })], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText(hostile).length).toBeGreaterThan(0));
    expect(container.querySelector('img')).toBeNull();
  });
});

describe('AutonomousOpsStatusProvider (one shared poller)', () => {
  function Probe() {
    const { status, platformStatus, refresh } = useAutonomousOpsStatus();
    return (
      <div>
        <span data-testid="tenant">{status?.tenantName ?? '-'}</span>
        <span data-testid="platform">{platformStatus ? 'platform' : '-'}</span>
        <button onClick={() => { void refresh(); }}>probe-refresh</button>
      </div>
    );
  }
  const mount = (role: string, props: { tenantId?: string | null; enabled?: boolean }) =>
    render(withUser(role, (
      <AutonomousOpsStatusProvider tenantId={props.tenantId ?? null} enabled={props.enabled ?? true}>
        <Probe />
      </AutonomousOpsStatusProvider>
    )));

  it('fetches status once on mount, again on window focus and on refresh()', async () => {
    routeFetch({});
    mount('Tenant Admin', {});
    await waitFor(() => expect(screen.getByTestId('tenant').textContent).toBe('Acme Corp'));
    expect(urlsOf('/autonomous-ops/status')).toEqual(['/api/autonomous-ops/status']);

    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(urlsOf('/autonomous-ops/status').length).toBe(2));

    await act(async () => { fireEvent.click(screen.getByText('probe-refresh')); });
    await waitFor(() => expect(urlsOf('/autonomous-ops/status').length).toBe(3));
  });

  it('polls every 30 s while the tab is visible and not while it is hidden', async () => {
    vi.useFakeTimers();
    routeFetch({});
    mount('Tenant Admin', {});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(urlsOf('/autonomous-ops/status').length).toBe(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(urlsOf('/autonomous-ops/status').length).toBe(2);

    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    await act(async () => { await vi.advanceTimersByTimeAsync(90_000); });
    expect(urlsOf('/autonomous-ops/status').length).toBe(2);

    visibility.mockReturnValue('visible');
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(urlsOf('/autonomous-ops/status').length).toBe(3);
    visibility.mockRestore();
  });

  it('makes no request at all when disabled (a user without view:autonomous_ops)', async () => {
    routeFetch({});
    mount('Analyst', { enabled: false });
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    fireEvent.click(screen.getByText('probe-refresh'));
    await act(async () => { await Promise.resolve(); });
    expect(mockAuthFetch).not.toHaveBeenCalled();
  });

  it('a failed poll keeps the last known status', async () => {
    let fail = false;
    routeFetch({ status: () => (fail ? jsonRes({ detail: 'boom' }, 500) : jsonRes(statusPayload())) });
    mount('Tenant Admin', {});
    await waitFor(() => expect(screen.getByTestId('tenant').textContent).toBe('Acme Corp'));
    fail = true;
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(urlsOf('/autonomous-ops/status').length).toBe(2));
    expect(screen.getByTestId('tenant').textContent).toBe('Acme Corp');
  });

  it('scopes the poll: Super Admin without a tenant reads platform status, Platform Support without a tenant reads nothing', async () => {
    routeFetch({});
    const a = mount('Super Admin', {});
    await waitFor(() => expect(screen.getByTestId('platform').textContent).toBe('platform'));
    expect(urlsOf('/autonomous-ops/status')).toEqual([]);
    expect(urlsOf('/platform/autonomous-ops/status').length).toBe(1);
    a.unmount();

    mockAuthFetch.mockClear();
    routeFetch({});
    mount('Platform Support', {});
    await act(async () => { await Promise.resolve(); });
    expect(mockAuthFetch).not.toHaveBeenCalled();
  });

  it('sends tenantId only for platform staff', async () => {
    routeFetch({});
    const a = mount('Platform Support', { tenantId: 'tenant-b' });
    await waitFor(() => expect(urlsOf('/autonomous-ops/status').length).toBe(1));
    expect(urlsOf('/autonomous-ops/status')[0]).toBe('/api/autonomous-ops/status?tenantId=tenant-b');
    a.unmount();

    mockAuthFetch.mockClear();
    routeFetch({});
    mount('Tenant Admin', { tenantId: 'tenant-b' });
    await waitFor(() => expect(urlsOf('/autonomous-ops/status').length).toBe(1));
    expect(urlsOf('/autonomous-ops/status')[0]).toBe('/api/autonomous-ops/status');
  });
});

describe('App wiring', () => {
  const app = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8');
  it('lazy-loads the screen and mounts the provider for holders of view:autonomous_ops', () => {
    expect(app).toMatch(/const AutonomousOpsActivity = lazy\(/);
    expect(app).toMatch(/case 'autonomousOps':/);
    expect(app).toMatch(/<AutonomousOpsStatusProvider[^>]*enabled=\{hasPermission\('view:autonomous_ops'\)\}/);
  });
});
