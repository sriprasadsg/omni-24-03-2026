/**
 * Phase 81 / ACTV-01, ACTV-03: the read-only Autonomous Ops screen. The backend routes arrive
 * in 81-09, so authFetch is mocked and the payloads follow the contract in 81-07-PLAN.md.
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

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
function routeFetch(handlers: { status?: Handler; actions?: Handler; incidents?: Handler; platformStatus?: Handler; platformActions?: Handler }) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (handlers.status ?? (() => jsonRes(statusPayload())))(url);
    if (path === '/api/autonomous-ops/actions') return (handlers.actions ?? (() => jsonRes({ items: [], nextCursor: null })))(url);
    // 83-19: the Needs your decision section reads its own cards; this screen's tests are about the activity list.
    if (path === '/api/autonomous-ops/incidents') {
      return (handlers.incidents ?? (() => jsonRes({ items: [], total: 0, offset: 0, limit: 10, stopped: null })))(url);
    }
    // 83-13: the Response settings panel reads its own settings; this screen's tests are about the activity list.
    if (path === '/api/autonomous-ops/response-settings') {
      return jsonRes({ twoSignal: true, blockHours: 24, watchedServices: [], readable: true, restartAvailable: true });
    }
    if (path === '/api/platform/autonomous-ops/response-settings') {
      return jsonRes({ organizations: 1, twoSignal: { on: 1, off: 0 }, blockHours: { '24': 1 }, unreadable: 0 });
    }
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

// ── Task 2: filters, layouts, simulation and control rows, pagination, states ──

const STATE_FILTERS = ['pending', 'done', 'undone', 'failed', 'refused', 'suggested'] as const;
const FILTER_LABELS = ['All', 'Pending', 'Done', 'Undone', 'Failed', 'Refused', 'Suggested', 'Simulation'];

const CONTROL_ROW = row({
  id: 'r3', bucket: 'control', state: 'control', createdAt: minutesAgo(45), controlEvent: 'stop_pressed',
  actionLabel: 'Stop pressed', classLine: null, reasonText: 'Investigating an incident', ruleId: null,
  host: null, target: 'All automatic actions', resultText: 'Stopped by Pat.',
});

const ALL_KINDS = [
  DONE_ROW,
  SIM_ROW,
  CONTROL_ROW,
  ...STATE_FILTERS.filter(b => b !== 'done').map((b, i) =>
    row({ id: `s-${b}`, bucket: b, state: b, actionLabel: `Action ${b}`, createdAt: minutesAgo(60 + i) })),
];

/** A server that honours the bucket parameter, like the real route will. */
function bucketAwareActions(rows: any[]): Handler {
  return (url: string) => {
    const bucket = new URLSearchParams(url.split('?')[1]).get('bucket') ?? 'all';
    const items = bucket === 'all' ? rows : rows.filter(r => r.bucket === bucket);
    return jsonRes({ items, nextCursor: null });
  };
}

const filterGroup = () => screen.getByRole('group', { name: 'Filter activity by state' });
const pill = (name: string | RegExp) => within(filterGroup()).getByRole('button', { name });
const tableRows = (container: HTMLElement) => container.querySelectorAll('tbody tr');
const lastActionsUrl = () => urlsOf('/autonomous-ops/actions').at(-1) as string;
const noClippingClasses = (container: HTMLElement) =>
  container.querySelector('.truncate, .font-medium, .font-bold');

describe('filters', () => {
  it('renders eight filter buttons in a labelled group, All pressed by default', async () => {
    routeFetch({ actions: bucketAwareActions(ALL_KINDS) });
    render(screenFor('Tenant Admin'));
    const buttons = within(filterGroup()).getAllByRole('button');
    expect(buttons.map(b => b.textContent)).toEqual(FILTER_LABELS);
    expect(pill('All').getAttribute('aria-pressed')).toBe('true');
    expect(pill('Pending').getAttribute('aria-pressed')).toBe('false');
    expect(filterGroup().className).toContain('flex-wrap');
    expect(filterGroup().className).toContain('gap-2');
  });

  it('selecting Pending requests bucket=pending from the first page, with no cursor', async () => {
    routeFetch({ actions: bucketAwareActions(ALL_KINDS) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    fireEvent.click(pill('Pending'));
    await waitFor(() => expect(lastActionsUrl()).toBe('/api/autonomous-ops/actions?bucket=pending&limit=25'));
    expect(pill('Pending').getAttribute('aria-pressed')).toBe('true');
    expect(pill('All').getAttribute('aria-pressed')).toBe('false');
    await waitFor(() => expect(screen.getAllByText('Action pending').length).toBeGreaterThan(0));
    expect(screen.queryByText('Block IP address')).toBeNull();
  });

  it('shows per-filter counts only when the first page returns a counts object', async () => {
    routeFetch({ actions: () => jsonRes({
      items: [DONE_ROW], nextCursor: null,
      counts: { pending: 2, done: 5, undone: 0, failed: 1, refused: 0, suggested: 3, simulation: 4 },
    }) });
    const { unmount } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(pill('Pending 2')).toBeInTheDocument());
    expect(pill('Simulation 4')).toBeInTheDocument();
    expect(pill('All').textContent).toBe('All');
    unmount();

    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW], nextCursor: null }) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(within(filterGroup()).getAllByRole('button').map(b => b.textContent)).toEqual(FILTER_LABELS);
  });
});

describe('simulation and control rows', () => {
  it('a simulation row carries the chip, the dashed rule and the would-have result under All and Simulation', async () => {
    routeFetch({ actions: bucketAwareActions(ALL_KINDS) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Isolate host').length).toBeGreaterThan(0));

    expect(screen.getAllByText(/^Nothing was done\. This is what would have happened: /).length).toBeGreaterThan(0);
    const chip = screen.getAllByText('Simulation').find(el => el.closest('span')?.className.includes('border-dashed'));
    expect(chip).toBeTruthy();
    expect(container.querySelector('tbody td.border-dashed.border-l-2')).not.toBeNull();
    expect(container.querySelector('li.border-dashed.border-l-2')).not.toBeNull();

    fireEvent.click(pill('Simulation'));
    await waitFor(() => expect(lastActionsUrl()).toContain('bucket=simulation'));
    await waitFor(() => expect(screen.queryByText('Block IP address')).toBeNull());
    expect(screen.getAllByText('Isolate host').length).toBeGreaterThan(0);
  });

  it('a simulation row is absent under each of the six state filters, even if the server leaks one', async () => {
    routeFetch({ actions: (url) => {
      const bucket = new URLSearchParams(url.split('?')[1]).get('bucket');
      const own = ALL_KINDS.filter(r => r.bucket === bucket);
      return jsonRes({ items: bucket === 'all' ? ALL_KINDS : [...own, SIM_ROW], nextCursor: null });
    } });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Isolate host').length).toBeGreaterThan(0));
    for (const state of STATE_FILTERS) {
      fireEvent.click(pill(new RegExp(`^${state}$`, 'i')));
      await waitFor(() => expect(lastActionsUrl()).toContain(`bucket=${state}`));
      await waitFor(() => expect(screen.getAllByText(`Action ${state}`.replace('Action done', 'Block IP address')).length).toBeGreaterThan(0));
      expect(screen.queryByText('Isolate host')).toBeNull();
      expect(screen.queryByText('Simulation', { selector: 'span' })).toBeNull();
    }
  });

  it('never presents a simulation as carried out, whatever text the server sent', async () => {
    routeFetch({ actions: () => jsonRes({ items: [
      row({ id: 'x1', bucket: 'simulation', actionLabel: 'Kill process', resultText: 'Process terminated.' }),
      row({ id: 'x2', bucket: 'simulation', actionLabel: 'Quarantine file', resultText: null }),
    ], nextCursor: null }) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Kill process').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Nothing was done. This is what would have happened: Process terminated.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Nothing was done.').length).toBeGreaterThan(0);
    expect(screen.queryByText('Process terminated.')).toBeNull();
  });

  it('control rows show the Stop or Resume chip and appear under All only', async () => {
    const resume = row({ id: 'r9', bucket: 'control', controlEvent: 'stop_cleared', actionLabel: 'Stop cleared', resultText: 'Resumed by Pat.' });
    routeFetch({ actions: (url) => {
      const bucket = new URLSearchParams(url.split('?')[1]).get('bucket');
      return jsonRes({ items: bucket === 'all' ? [CONTROL_ROW, resume] : [CONTROL_ROW, resume, DONE_ROW], nextCursor: null });
    } });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Stop pressed').length).toBeGreaterThan(0));
    expect(screen.getAllByText('Stop').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Resume').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Stopped by Pat.').length).toBeGreaterThan(0);

    fireEvent.click(pill('Done'));
    await waitFor(() => expect(lastActionsUrl()).toContain('bucket=done'));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(screen.queryByText('Stop pressed')).toBeNull();
  });
});

describe('table and cards', () => {
  it('has an sr-only caption, five column headers with scope=col, and read-only rows', async () => {
    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW, SIM_ROW], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(2));
    const caption = container.querySelector('caption');
    expect(caption?.textContent).toBe('Autonomous Ops activity');
    expect(caption?.className).toContain('sr-only');
    const headers = Array.from(container.querySelectorAll('thead th'));
    expect(headers.map(h => h.textContent)).toEqual(['State', 'What ran', 'Why (the rule)', 'Target', 'Result']);
    expect(headers.every(h => h.getAttribute('scope') === 'col')).toBe(true);

    // read-only: no row actions, no click targets in the activity rows
    expect(container.querySelectorAll('tbody button, tbody a, li button, li a').length).toBe(0);
    expect(container.querySelectorAll('tbody tr[onclick], [role="menu"]').length).toBe(0);

    // stacked cards carry the same values under dl labels
    const cards = container.querySelectorAll('ul > li');
    expect(cards.length).toBe(2);
    const labels = Array.from(cards[0].querySelectorAll('dt')).map(d => d.textContent);
    expect(labels).toEqual(['Why', 'Target', 'Result']);
  });

  it('shows a dash for a missing target or result and still renders the row', async () => {
    routeFetch({ actions: () => jsonRes({ items: [row({ host: null, target: null, resultText: null })], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(1));
    const cells = tableRows(container)[0].querySelectorAll('td');
    expect(cells[3].textContent).toBe('—');
    expect(cells[4].textContent).toBe('—');
    const dds = container.querySelectorAll('ul > li dl dd');
    expect(dds[1].textContent).toBe('—');
    expect(dds[2].textContent).toBe('—');
  });

  it('wraps long values and never clips them', async () => {
    const long = 'x'.repeat(200);
    routeFetch({ actions: () => jsonRes({ items: [row({
      host: `host-${long}.example.com`, target: `C:\\${long}\\file.dll`, reasonText: `reason ${long}`, ruleId: `rule.${long}`,
    })], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(1));
    expect(container.querySelector('.font-mono.break-all')).not.toBeNull();
    expect(container.querySelector('.break-words')).not.toBeNull();
    expect(noClippingClasses(container)).toBeNull();
  });

  it('uses relative time under 24 hours and an absolute time with the full stamp in title after', async () => {
    routeFetch({ actions: () => jsonRes({ items: [
      row({ id: 'a', createdAt: new Date(Date.now() - 12 * 60_000).toISOString() }),
      row({ id: 'b', createdAt: '2026-01-05T14:32:00Z' }),
    ], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(2));
    const times = container.querySelectorAll('tbody time');
    expect(times[0].textContent).toBe('12 min ago');
    expect(times[1].textContent).toMatch(/2026/);
    expect(times[1].getAttribute('title')).toBeTruthy();
    expect(times[1].getAttribute('datetime')).toBe('2026-01-05T14:32:00Z');
  });
});

describe('pagination', () => {
  const page = (ids: string[], extra: Record<string, unknown> = {}) =>
    ({ items: ids.map(id => row({ id, actionLabel: `Act ${id}` })), ...extra });

  it('Load more requests the next cursor, appends rows and disappears on the last page', async () => {
    routeFetch({ actions: (url) => jsonRes(url.includes('cursor=c2') ? page(['d'], { nextCursor: null }) : page(['a', 'b', 'c'], { nextCursor: 'c2', total: 4 })) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(3));
    expect(screen.getByText('Showing 3 of 4 actions')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
    await waitFor(() => expect(tableRows(container).length).toBe(4));
    expect(lastActionsUrl()).toBe('/api/autonomous-ops/actions?bucket=all&limit=25&cursor=c2');
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
    expect(screen.getByText('Showing 4 actions')).toBeInTheDocument();
  });

  it('reads Showing 1 action for a single row and Showing n of total when more exist', async () => {
    routeFetch({ actions: () => jsonRes(page(['a'], { nextCursor: null })) });
    const one = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getByText('Showing 1 action')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
    one.unmount();

    routeFetch({ actions: () => jsonRes(page(['a', 'b', 'c'], { nextCursor: 'c2', total: 10 })) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getByText('Showing 3 of 10 actions')).toBeInTheDocument());
  });

  it('after Load more, Refresh still reloads the first page and starts again from page one (WR-23)', async () => {
    let fresh = false;
    routeFetch({ actions: (url) => {
      if (url.includes('cursor=c2')) return jsonRes(page(['c'], { nextCursor: null }));
      return jsonRes(page(fresh ? ['a', 'b2'] : ['a', 'b'], { nextCursor: 'c2' }));
    } });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
    await waitFor(() => expect(tableRows(container).length).toBe(3));

    fresh = true;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.getAllByText('Act b2').length).toBeGreaterThan(0));
    expect(lastActionsUrl()).toBe('/api/autonomous-ops/actions?bucket=all&limit=25');
    expect(tableRows(container).length).toBe(2);
    expect(screen.getByRole('button', { name: 'Load more' })).toBeInTheDocument();
  });

  it('a failed Load more keeps the loaded rows, shows its own alert and Try again retries', async () => {
    let failMore = true;
    routeFetch({ actions: (url) => {
      if (!url.includes('cursor=')) return jsonRes(page(['a', 'b'], { nextCursor: 'c2' }));
      return failMore ? jsonRes({ detail: 'down' }, 503) : jsonRes(page(['c'], { nextCursor: null }));
    } });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load more activity. Try again.");
    expect(tableRows(container).length).toBe(2);

    failMore = false;
    fireEvent.click(within(alert.parentElement as HTMLElement).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(tableRows(container).length).toBe(3));
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('list states', () => {
  it('loading: five skeleton rows, aria-busy, filters stay interactive; no skeleton once loaded', async () => {
    let release: (r: Response) => void = () => {};
    routeFetch({ actions: () => new Promise<Response>(res => { release = res; }) });
    const { container } = render(screenFor('Tenant Admin'));
    // the status card above the list is aria-busy while it loads too (81-10): find the list's own container
    const busy = container.querySelector('[data-skeleton="row"]')?.closest('[aria-busy="true"]') as HTMLElement;
    expect(busy).not.toBeNull();
    expect(busy.querySelectorAll('[data-skeleton="row"]').length).toBe(5);
    expect(noClippingClasses(container)).toBeNull();
    within(filterGroup()).getAllByRole('button').forEach(b => expect(b).not.toBeDisabled());

    await act(async () => { release(jsonRes({ items: [DONE_ROW], nextCursor: null })); });
    await waitFor(() => expect(container.querySelector('[data-skeleton="row"]')).toBeNull());
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
  });

  it('first-page error: alert with Try again that refetches, filters stay enabled', async () => {
    let ok = false;
    routeFetch({ actions: () => (ok ? jsonRes({ items: [DONE_ROW], nextCursor: null }) : jsonRes({ detail: 'x' }, 500)) });
    const { container } = render(screenFor('Tenant Admin'));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load activity. Check your connection and try again.");
    within(filterGroup()).getAllByRole('button').forEach(b => expect(b).not.toBeDisabled());
    expect(noClippingClasses(container)).toBeNull();

    ok = true;
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('empty under All: live and shadow-mode variants, no footer and no Load more', async () => {
    routeFetch({});
    const live = render(screenFor('Tenant Admin'));
    expect(await screen.findByRole('heading', { name: 'No activity yet' })).toBeInTheDocument();
    expect(screen.getByText("Autonomous Ops hasn't made any decisions for this organization yet. When it does, each one appears here with the rule behind it.")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing /)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
    expect(noClippingClasses(live.container)).toBeNull();
    expect(live.container.querySelector('.max-w-prose')).not.toBeNull();
    live.unmount();

    routeFetch({ status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'tenant' } })) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getByText(/Shadow mode is on, so when it does, entries are marked as a simulation and nothing is carried out\./)).toBeInTheDocument());
  });

  it('empty under a filter: short variant with Show all activity selecting All', async () => {
    routeFetch({ actions: (url) => jsonRes({ items: url.includes('bucket=all') ? [DONE_ROW] : [], nextCursor: null }) });
    render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));

    fireEvent.click(pill('Pending'));
    expect(await screen.findByText('No pending actions.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show all activity' }));
    await waitFor(() => expect(screen.getAllByText('Block IP address').length).toBeGreaterThan(0));
    expect(pill('All').getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(pill('Simulation'));
    expect(await screen.findByText('No simulated actions.')).toBeInTheDocument();
  });

  it('a background refresh (Refresh button) shows no skeleton and keeps the rows', async () => {
    let hold = false;
    let release: (r: Response) => void = () => {};
    routeFetch({ actions: () => (hold ? new Promise<Response>(res => { release = res; }) : jsonRes({ items: [DONE_ROW], nextCursor: null })) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(tableRows(container).length).toBe(1));
    const before = urlsOf('/autonomous-ops/actions').length;

    hold = true;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(urlsOf('/autonomous-ops/actions').length).toBe(before + 1));
    expect(container.querySelector('[data-skeleton="row"]')).toBeNull();
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
    expect(tableRows(container).length).toBe(1);
    await act(async () => { release(jsonRes({ items: [DONE_ROW, SIM_ROW], nextCursor: null })); });
    await waitFor(() => expect(tableRows(container).length).toBe(2));
  });
});

describe('scope', () => {
  it('Platform Support with no tenant sees only the header and Select an organization, and makes no request', async () => {
    routeFetch({});
    const goTo = vi.fn();
    const { container } = render(screenFor('Platform Support', { onGoToTenants: goTo }));
    expect(screen.getByRole('heading', { level: 1, name: 'Autonomous Ops' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Select an organization' })).toBeInTheDocument();
    expect(screen.getByText('Choose an organization in Tenants to see its Autonomous Ops activity. This view is read-only.')).toBeInTheDocument();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Filter activity by state' })).toBeNull();
    expect(container.querySelector('[data-slot="autonomous-ops-status"]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Go to Tenants' }));
    expect(goTo).toHaveBeenCalledTimes(1);
    await act(async () => { await Promise.resolve(); });
    expect(mockAuthFetch).not.toHaveBeenCalled();
  });

  it('Platform Support offers no Go to Tenants button when it cannot open that screen', () => {
    routeFetch({});
    render(screenFor('Platform Support'));
    expect(screen.queryByRole('button', { name: 'Go to Tenants' })).toBeNull();
  });

  it('Platform Support with a tenant selected reads that tenant, read-only', async () => {
    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW], nextCursor: null }) });
    render(screenFor('Platform Support', { tenantId: 'tenant-b' }));
    await waitFor(() => expect(urlsOf('/autonomous-ops/actions')[0]).toBe('/api/autonomous-ops/actions?bucket=all&limit=25&tenantId=tenant-b'));
    await waitFor(() => expect(screen.getByText('Viewing Acme Corp')).toBeInTheDocument());
    expect(screen.getByText('Read-only')).toBeInTheDocument();
  });

  it('Super Admin with no tenant reads the platform-scope list; with a tenant, that tenant', async () => {
    routeFetch({ platformActions: () => jsonRes({ items: [CONTROL_ROW], nextCursor: null }) });
    const platform = render(screenFor('Super Admin'));
    await waitFor(() => expect(screen.getAllByText('Stop pressed').length).toBeGreaterThan(0));
    expect(urlsOf('/platform/autonomous-ops/actions')[0]).toBe('/api/platform/autonomous-ops/actions?bucket=all&limit=25');
    expect(urlsOf('/autonomous-ops/actions')).toEqual([]);
    expect(screen.getByText('Platform')).toBeInTheDocument();
    expect(screen.queryByText('Read-only')).toBeNull();
    platform.unmount();

    mockAuthFetch.mockClear();
    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW], nextCursor: null }) });
    render(screenFor('Super Admin', { tenantId: 'tenant-b' }));
    await waitFor(() => expect(urlsOf('/autonomous-ops/actions')[0]).toContain('tenantId=tenant-b'));
    expect(urlsOf('/platform/autonomous-ops/actions')).toEqual([]);
  });

  it('a tenant role never sends tenantId and never uses the platform routes', async () => {
    routeFetch({ actions: () => jsonRes({ items: [DONE_ROW], nextCursor: null }) });
    render(screenFor('Security Analyst', { tenantId: 'tenant-b' }));
    await waitFor(() => expect(urlsOf('/autonomous-ops/actions').length).toBeGreaterThan(0));
    expect(urlsOf('/autonomous-ops/actions')[0]).toBe('/api/autonomous-ops/actions?bucket=all&limit=25');
    expect(urlsOf('/platform/autonomous-ops/actions')).toEqual([]);
  });
});

describe('a row that runs several steps (Phase 81 review WR-10)', () => {
  const steps = (list: Element | undefined) => Array.from(list?.querySelectorAll('li') ?? []).map(li => li.textContent);

  it('lists every step and every step that puts it back, as text, in the table and the stacked card', async () => {
    const multi = row({
      id: 'm1', bucket: 'pending', state: 'awaiting_approval', actionLabel: 'Restart service and 1 more step',
      classLine: 'Needs approval', target: null, resultText: 'Waiting for a person to approve.',
      steps: [{ label: 'Restart service', target: 'nginx' }, { label: 'Block IP address', target: '198.51.100.4' }],
      compensationSteps: [{ label: 'Unblock IP address', target: '198.51.100.4' }],
    });
    const single = row({ steps: [{ label: 'Block IP address', target: '203.0.113.7' }], compensationSteps: [] });
    routeFetch({ actions: () => jsonRes({ items: [multi, single], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Restart service and 1 more step').length).toBeGreaterThan(0));

    const lists = container.querySelectorAll('ol[aria-label="Steps"]');
    expect(lists.length).toBe(2);                          // the table row and the stacked card, never the single-step row
    for (const list of Array.from(lists)) {
      expect(steps(list)).toEqual(['Restart service nginx', 'Block IP address 198.51.100.4']);
    }
    const back = container.querySelectorAll('ol[aria-label="Steps that put it back"]');
    expect(back.length).toBe(2);
    expect(steps(back[0])).toEqual(['Unblock IP address 198.51.100.4']);
  });

  it('a step without a target, an older server without the lists and hostile text all stay plain', async () => {
    const hostile = '<b>x</b>';
    const multi = row({ id: 'm2', actionLabel: 'Kill process and 1 more step',
                        steps: [{ label: 'Kill process', target: null }, { label: hostile, target: hostile }] });
    routeFetch({ actions: () => jsonRes({ items: [multi, row({ id: 'old' })], nextCursor: null }) });
    const { container } = render(screenFor('Tenant Admin'));
    await waitFor(() => expect(screen.getAllByText('Kill process and 1 more step').length).toBeGreaterThan(0));
    const first = container.querySelector('ol[aria-label="Steps"]') ?? undefined;
    expect(steps(first)).toEqual(['Kill process', `${hostile} ${hostile}`]);
    expect(container.querySelector('ol b')).toBeNull();
    expect(container.querySelectorAll('ol[aria-label="Steps that put it back"]').length).toBe(0);
  });
});

describe('screen source guards', () => {
  it('uses no dangerouslySetInnerHTML and no weights or clipping outside the contract', () => {
    for (const f of ['components/AutonomousOpsActivity.tsx', 'components/AutonomousOpsActivityList.tsx', 'contexts/AutonomousOpsStatusContext.tsx']) {
      const src = readFileSync(resolve(__dirname, '../..', f), 'utf8');
      expect(src).not.toContain('dangerouslySetInnerHTML');
      expect(src).not.toMatch(/\btruncate\b|font-medium|font-bold/);
    }
  });
});
