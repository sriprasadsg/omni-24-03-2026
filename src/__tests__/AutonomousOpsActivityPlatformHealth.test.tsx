/**
 * Phase 82 / HEAL-07, D-23: platform-health rows in the platform Activity list.
 * authFetch is mocked; rows follow the actions contract (healthChip and source on platform_health rows).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivityList } from '../../components/AutonomousOpsActivityList';
import { mockAuthFetch, jsonRes } from './_platformHealthHarness';

const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
const SUPER = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops', PLATFORM_CONTROL];
const TENANT_ADMIN = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops'];

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

function healthRow(over: Record<string, unknown> = {}) {
  return {
    id: 'h1', bucket: 'platform_health', state: 'critical', createdAt: minutesAgo(5),
    actionLabel: 'Service check', classLine: null, source: 'Watchdog', healthChip: 'critical',
    reasonText: 'Failed 2 checks in a row.', ruleId: 'service-down',
    host: 'omni', target: 'mongod', resultText: 'MongoDB is down.', controlEvent: null,
    ...over,
  };
}

function doneRow(over: Record<string, unknown> = {}) {
  return {
    id: 'd1', bucket: 'done', state: 'done', createdAt: minutesAgo(12),
    actionLabel: 'Block IP address', classLine: 'Automatic',
    reasonText: 'Repeated failed sign-ins from one address', ruleId: 'rule.block_ip.bruteforce',
    host: 'web-01.example.com', target: '203.0.113.7', resultText: 'Blocked for 24 hours.', controlEvent: null,
    ...over,
  };
}

function tenantStatus() {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
  };
}

const watchdogState = { current: 'running' as string | null };
function platformStatus() {
  return {
    scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true,
    health: watchdogState.current
      ? { watchdog: watchdogState.current, lastSeenAt: null, channel: null, channelError: null }
      : null,
  };
}

type Page = { items: unknown[]; nextCursor?: string | null; counts?: Record<string, number>; total?: number };
type PageFn = (url: string) => Page | Promise<Page>;

function route(opts: { platform?: PageFn; tenant?: PageFn } = {}) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return jsonRes(tenantStatus());
    if (path === '/api/platform/autonomous-ops/status') return jsonRes(platformStatus());
    if (path === '/api/platform/autonomous-ops/actions') {
      return jsonRes(await (opts.platform ?? (() => ({ items: [], nextCursor: null })))(url));
    }
    if (path === '/api/autonomous-ops/actions') {
      return jsonRes(await (opts.tenant ?? (() => ({ items: [], nextCursor: null })))(url));
    }
    throw new Error(`unexpected request ${url}`);
  });
}

const actionCalls = (platform: boolean) =>
  mockAuthFetch.mock.calls.map(c => c[0] as string)
    .filter(u => u.split('?')[0] === (platform ? '/api/platform/autonomous-ops/actions' : '/api/autonomous-ops/actions'));

function superList() {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Super Admin', tenantId: 'tenant-a', permissions: SUPER } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: (p: any) => SUPER.includes(p), enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>
        <AutonomousOpsActivityList scope={{ kind: 'platform' }} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

function tenantList() {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u2', name: 'Tess', email: 'tess@example.com', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: TENANT_ADMIN } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: (p: any) => TENANT_ADMIN.includes(p), enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>
        <AutonomousOpsActivityList scope={{ kind: 'tenant', tenantId: null }} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

beforeEach(() => { mockAuthFetch.mockReset(); watchdogState.current = 'running'; });
afterEach(() => { vi.useRealTimers(); });

describe('Platform-health rows in the Activity list (tracer)', () => {
  it('platform scope: the table and the stacked card show the chip, label, source, reason, rule id, host, target and result', async () => {
    route({ platform: () => ({ items: [healthRow()], nextCursor: null }) });
    const { container } = render(superList());

    await waitFor(() => expect(screen.getAllByText('Service check').length).toBe(2)); // table + card
    expect(screen.getAllByText('Critical').length).toBe(2);
    expect(screen.getAllByText('Watchdog').length).toBe(2);
    expect(screen.getAllByText('Failed 2 checks in a row.').length).toBe(2);
    for (const el of screen.getAllByText('service-down')) expect(el.className).toContain('font-mono');
    expect(screen.getAllByText('omni').length).toBe(2);
    for (const el of screen.getAllByText('mongod')) expect(el.className).toContain('font-mono');
    expect(screen.getAllByText('MongoDB is down.').length).toBe(2);
    // the five-column table, no extra column and no row actions
    expect(container.querySelectorAll('thead th').length).toBe(5);
    expect(container.querySelectorAll('tbody tr button').length).toBe(0);
  });

  it('platform scope: each of the six chips reads from healthChip, not from the informational chip', async () => {
    const chips: Array<[string, string]> = [
      ['healthy', 'Healthy'], ['notice', 'Notice'], ['warning', 'Warning'],
      ['critical', 'Critical'], ['paged', 'Paged'], ['skipped', 'Skipped'],
    ];
    route({ platform: () => ({
      items: chips.map(([chip], i) => healthRow({ id: `c${i}`, healthChip: chip, actionLabel: `Event ${chip}` })),
      nextCursor: null,
    }) });
    render(superList());
    await waitFor(() => expect(screen.getAllByText('Event healthy').length).toBe(2));
    for (const [, label] of chips) expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    // the Suggested filter pill exists; no row wears the Suggested chip
    expect(screen.queryAllByText('Suggested').filter(el => !el.closest('button'))).toEqual([]);
  });

  it('tenant scope: a platform_health row the server sent anyway is not rendered', async () => {
    route({ tenant: () => ({ items: [healthRow(), doneRow()], nextCursor: null, total: 2 }) });
    render(tenantList());

    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(screen.queryByText('Service check')).toBeNull();
    expect(screen.queryByText('MongoDB is down.')).toBeNull();
    expect(screen.queryByText('service-down')).toBeNull();
  });
});
