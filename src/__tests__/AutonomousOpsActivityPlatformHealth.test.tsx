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

// ── Task 2: pill, counts, empty states, partial rows, loading ───────────────

const pillNames = () => within(screen.getByRole('group', { name: 'Filter activity by state' }))
  .getAllByRole('button').map(b => (b.textContent ?? '').replace(/\s+\d+$/, '').trim());
const healthPill = () => screen.getByRole('button', { name: /^Platform health/ });

describe('Platform health filter pill', () => {
  it('platform scope: nine pills, Platform health last, after Simulation', async () => {
    route({ platform: () => ({ items: [healthRow()], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));
    expect(pillNames()).toEqual([
      'All', 'Pending', 'Done', 'Undone', 'Failed', 'Refused', 'Suggested', 'Simulation', 'Platform health',
    ]);
  });

  it('tenant scope: eight pills and no Platform health', async () => {
    route({ tenant: () => ({ items: [doneRow()], nextCursor: null }) });
    render(tenantList());
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(pillNames()).toEqual(['All', 'Pending', 'Done', 'Undone', 'Failed', 'Refused', 'Suggested', 'Simulation']);
    expect(screen.queryByRole('button', { name: /Platform health/ })).toBeNull();
  });

  it('shows counts.platform_health when the server returns it, and no number when it does not', async () => {
    route({ platform: () => ({ items: [healthRow()], nextCursor: null, counts: {
      pending: 0, done: 0, undone: 0, failed: 0, refused: 0, suggested: 0, simulation: 0, platform_health: 4,
    } }) });
    const first = render(superList());
    await waitFor(() => expect(healthPill().textContent).toBe('Platform health 4'));
    first.unmount();

    route({ platform: () => ({ items: [healthRow()], nextCursor: null, counts: {
      pending: 0, done: 0, undone: 0, failed: 0, refused: 0, suggested: 0, simulation: 0,
    } }) });
    render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));
    expect(healthPill().textContent).toBe('Platform health');
  });

  it('selecting it requests bucket=platform_health from the platform call and uses the accent selected classes', async () => {
    route({ platform: () => ({ items: [healthRow()], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));
    const idle = healthPill().className;
    fireEvent.click(healthPill());
    await waitFor(() => expect(actionCalls(true).some(u => u.includes('bucket=platform_health'))).toBe(true));
    expect(actionCalls(false)).toEqual([]);
    expect(healthPill()).toHaveAttribute('aria-pressed', 'true');
    expect(healthPill().className).toContain('bg-primary-500/10');
    expect(idle).not.toContain('bg-primary-500/10');
  });

  it('All includes platform-health rows next to the other rows', async () => {
    route({ platform: () => ({ items: [healthRow(), doneRow()], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Service check').length).toBeGreaterThan(0);
  });
});

describe('Platform health empty states', () => {
  it('before the first heartbeat: "No platform health events yet." with the install body and no Show all button', async () => {
    watchdogState.current = 'not_installed';
    route({ platform: () => ({ items: [], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(actionCalls(true).length).toBeGreaterThan(0));
    await waitFor(() => expect(mockAuthFetch.mock.calls.some(c => String(c[0]).startsWith('/api/platform/autonomous-ops/status'))).toBe(true));
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(healthPill());
    expect(await screen.findByRole('heading', { name: 'No platform health events yet.' })).toBeInTheDocument();
    expect(screen.getByText('Events appear here once the watchdog is installed and reporting.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show all activity' })).toBeNull();
  });

  it('after the watchdog reports: "No platform health events." with Show all activity, which selects All', async () => {
    watchdogState.current = 'running';
    route({ platform: () => ({ items: [], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(actionCalls(true).length).toBeGreaterThan(0));
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(healthPill());
    expect(await screen.findByRole('heading', { name: 'No platform health events.' })).toBeInTheDocument();
    expect(screen.queryByText('Events appear here once the watchdog is installed and reporting.')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show all activity' }));
    await waitFor(() => expect(healthPill()).toHaveAttribute('aria-pressed', 'false'));
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    expect(actionCalls(true).at(-1)).not.toContain('platform_health');
  });
});

describe('Platform-health row presentation', () => {
  it('a row with no target and no result shows an em dash in both cells and still renders', async () => {
    route({ platform: () => ({ items: [healthRow({ host: null, target: null, resultText: null })], nextCursor: null }) });
    const { container } = render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));
    const cells = container.querySelectorAll('tbody tr td');
    expect(cells[3].textContent).toBe('—'); // Target
    expect(cells[4].textContent).toBe('—'); // Result
  });

  it('a row with a host but no target keeps the host and shows a dash for the target', async () => {
    route({ platform: () => ({ items: [healthRow({ target: null })], nextCursor: null }) });
    const { container } = render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));
    const target = container.querySelectorAll('tbody tr td')[3];
    expect(target.textContent).toContain('omni');
    expect(target.textContent).toContain('—');
  });

  it('long reasons wrap with break-words, paths wrap with break-all, and nothing is truncated', async () => {
    const reason = 'Restart budget used up: '.repeat(20).trim();
    const path = '/etc/nginx/ssl/' + 'very-long-directory-name/'.repeat(10) + 'omni.crt';
    route({ platform: () => ({ items: [healthRow({ reasonText: reason, target: path })], nextCursor: null }) });
    const { container } = render(superList());
    await waitFor(() => expect(screen.getAllByText(reason).length).toBeGreaterThan(0));
    for (const el of screen.getAllByText(reason)) expect(el.className).toContain('break-words');
    for (const el of screen.getAllByText(path)) expect(el.className).toContain('break-all');
    expect(container.querySelector('.truncate')).toBeNull();
  });

  it('the footer uses the Phase 81 singular and plural forms', async () => {
    route({ platform: () => ({ items: [healthRow()], nextCursor: null }) });
    const one = render(superList());
    await waitFor(() => expect(screen.getByText('Showing 1 action')).toBeInTheDocument());
    one.unmount();
    route({ platform: () => ({ items: [healthRow(), healthRow({ id: 'h2' })], nextCursor: null }) });
    render(superList());
    await waitFor(() => expect(screen.getByText('Showing 2 actions')).toBeInTheDocument());
  });
});

describe('Platform health loading', () => {
  it('a filter change shows five skeleton rows with aria-busy true; a background refresh shows none', async () => {
    let release: (p: Page) => void = () => {};
    let hold = false;
    route({ platform: () => (hold
      ? new Promise<Page>(resolve => { release = resolve; })
      : { items: [healthRow()], nextCursor: null }) });
    const { container, rerender } = render(superList());
    await waitFor(() => expect(screen.getAllByText('Service check').length).toBeGreaterThan(0));

    hold = true;
    fireEvent.click(healthPill());
    await waitFor(() => expect(container.querySelectorAll('[data-skeleton="row"]').length).toBe(5));
    expect(container.querySelector('.card')).toHaveAttribute('aria-busy', 'true');
    await act(async () => { release({ items: [healthRow()], nextCursor: null }); });
    await waitFor(() => expect(container.querySelectorAll('[data-skeleton="row"]').length).toBe(0));
    expect(container.querySelector('.card')).toHaveAttribute('aria-busy', 'false');

    // background refresh: rows stay, no skeleton, aria-busy stays false
    hold = true;
    const list = (signal: number) => (
      <UserContext.Provider value={{
        currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Super Admin', tenantId: 'tenant-a', permissions: SUPER } as any,
        login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
        hasPermission: (p: any) => SUPER.includes(p), enabledFeatures: [], serverLockedFeatures: {},
      }}>
        <AutonomousOpsStatusProvider tenantId={null} enabled>
          <AutonomousOpsActivityList scope={{ kind: 'platform' }} refreshSignal={signal} />
        </AutonomousOpsStatusProvider>
      </UserContext.Provider>
    );
    rerender(list(1));
    await act(async () => { await Promise.resolve(); });
    expect(container.querySelectorAll('[data-skeleton="row"]').length).toBe(0);
    expect(container.querySelector('.card')).toHaveAttribute('aria-busy', 'false');
    expect(screen.getAllByText('Service check').length).toBeGreaterThan(0);
  });
});
