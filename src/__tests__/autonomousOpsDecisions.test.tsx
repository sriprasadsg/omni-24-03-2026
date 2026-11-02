/**
 * Phase 83 / ACTV-02 (83-19): the Needs your decision section. authFetch is mocked and the payloads follow the
 * 83-18 card contract (83-18-SUMMARY.md). Every control comes from the server's flags.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsDecisions } from '../../components/AutonomousOpsDecisions';
import { formatExpires, formatReverts } from '../../components/AutonomousOpsIncidentCard';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

// ── fixtures ────────────────────────────────────────────────────────────────

const MIN = 60_000;
const HOUR = 60 * MIN;
const at = (ms: number) => new Date(Date.now() + ms).toISOString();
const clock = (iso: string) => new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

function line(over: Record<string, unknown> = {}) {
  return {
    id: 'AO-1', state: 'awaiting_approval', bucket: 'pending', command: 'kill_process', label: 'Kill process',
    target: 'powershell.exe (PID 4120)', reason: 'A second source agreed this process is malicious.',
    ruleId: 'sweep:kill_process', consequenceText: 'Ends this process right away. Unsaved work in it is lost.',
    notice: null, result: null, needsPerson: true, createdAt: at(-5 * MIN), expiresAt: at(19 * HOUR + 30_000),
    revertsAt: null, chain: null, canApprove: true, canDeny: true, canConfirmIsolation: false,
    confirmedAt: null, confirmedBy: null,
    ...over,
  };
}

function card(over: Record<string, unknown> = {}) {
  const actions = (over.actions as unknown[]) ?? [line()];
  return {
    id: 'INC-1', host: 'web-01', startedAt: at(-12 * MIN), alertCount: 1,
    deadlineAt: at(19 * HOUR + 30_000), deadlineKind: 'expires', actionCount: actions.length, actions,
    ...over,
  };
}

const page = (items: unknown[], over: Record<string, unknown> = {}) =>
  ({ items, total: items.length, offset: 0, limit: 10, stopped: null, ...over });

function isolated(over: Record<string, unknown> = {}) {
  return line({
    id: 'AO-ISO', state: 'verified', bucket: 'done', command: 'isolate_host', label: 'Isolate host', target: null,
    consequenceText: 'Confirming keeps this computer isolated until you restore it. Without it, the computer returns to the network automatically at {at}.',
    result: 'web-01 is isolated. The connection to the platform stays open.',
    expiresAt: null, revertsAt: at(3 * HOUR + 12 * MIN + 30_000), canApprove: false, canDeny: false, canConfirmIsolation: true,
    ...over,
  });
}

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null,
    shadow: { effective: false, source: null }, stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;
interface Handlers { incidents?: Handler; decision?: Handler; status?: Handler }

function routeFetch(h: Handlers) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (h.status ?? (() => jsonRes(statusPayload())))(url, init);
    if (path === '/api/autonomous-ops/incidents') return (h.incidents ?? (() => jsonRes(page([]))))(url, init);
    if (/^\/api\/autonomous-ops\/actions\/[^/]+\/(approve|deny|confirm-isolation)$/.test(path)) {
      return (h.decision ?? (() => jsonRes({}, 500)))(url, init);
    }
    throw new Error(`unexpected request ${url}`);
  });
}

const callsTo = (re: RegExp) => mockAuthFetch.mock.calls.filter(c => re.test((c[0] as string).split('?')[0]));
const incidentCalls = () => callsTo(/\/incidents$/);
const decisionCalls = () => callsTo(/\/(approve|deny|confirm-isolation)$/);

function view(props: { onDecisionIds?: (ids: ReadonlySet<string>) => void; onDecided?: () => void; refreshSignal?: number } = {}) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: [] } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: () => true, enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>
        <AutonomousOpsDecisions tenantId={null} {...props} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

async function shown(props: Parameters<typeof view>[0] = {}) {
  const out = render(view(props));
  await screen.findByRole('heading', { name: 'Needs your decision' });
  return out;
}

const flush = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });

beforeEach(() => { mockAuthFetch.mockReset(); toast.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

// ── pure functions ──────────────────────────────────────────────────────────

describe('countdown text (never negative)', () => {
  const now = Date.parse('2026-11-02T10:00:00Z');
  const from = (ms: number) => new Date(now + ms).toISOString();

  it('formatReverts: hours and minutes, minutes, under one minute, and a past time', () => {
    expect(formatReverts(from(3 * HOUR + 12 * MIN + 5000), now)).toBe('Reverts in 3 h 12 min');
    expect(formatReverts(from(12 * MIN + 5000), now)).toBe('Reverts in 12 min');
    expect(formatReverts(from(40_000), now)).toBe('Reverts in under 1 min');
    expect(formatReverts(from(0), now)).toBe('Reverts in under 1 min');
    expect(formatReverts(from(-9 * MIN), now)).toBe('Reverts in under 1 min');
    expect(formatReverts('not a date', now)).toBe('Reverts in under 1 min');
  });

  it('formatExpires: hours, minutes, under one minute, and Expired once it has passed', () => {
    expect(formatExpires(from(19 * HOUR + 59 * MIN), now)).toBe('Expires in 19 h');
    expect(formatExpires(from(42 * MIN + 5000), now)).toBe('Expires in 42 min');
    expect(formatExpires(from(30_000), now)).toBe('Expires in under 1 min');
    expect(formatExpires(from(0), now)).toBe('Expired');
    expect(formatExpires(from(-MIN), now)).toBe('Expired');
  });
});

// ── the section ─────────────────────────────────────────────────────────────

describe('Needs your decision: section states', () => {
  it('renders nothing on first load and nothing when there is nothing to decide', async () => {
    let release!: (r: Response) => void;
    routeFetch({ incidents: () => new Promise<Response>(r => { release = r; }) });
    const { container } = render(view());
    await flush();
    expect(container.querySelector('section')).toBeNull();
    expect(container.querySelector('[aria-busy]')).toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();
    await act(async () => { release(jsonRes(page([]))); });
    await flush();
    expect(container.querySelector('section')).toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('one card: heading, count, section line, host, Started, deadline chip and the action line', async () => {
    routeFetch({ incidents: () => jsonRes(page([card()])) });
    await shown();
    expect(screen.getByText(
      'Approvals expire after 24 hours and then count as denied. An isolated computer returns to the network after 4 hours unless you confirm it.',
    )).toBeInTheDocument();
    expect(screen.getByText('1 incident')).toBeInTheDocument();
    const article = screen.getByRole('article', { name: 'web-01' });
    expect(article).toHaveAttribute('id', 'approval-INC-1');
    expect(article).toHaveAttribute('tabindex', '-1');
    expect(within(article).getByText('Started 12 min ago · 1 alert')).toBeInTheDocument();
    expect(within(article).getAllByText('Expires in 19 h').length).toBeGreaterThan(0);
    for (const text of ['Pending', 'Kill process', 'powershell.exe (PID 4120)', 'A second source agreed this process is malicious.',
      'sweep:kill_process', 'Ends this process right away. Unsaved work in it is lost.']) {
      expect(within(article).getByText(text)).toBeInTheDocument();
    }
    expect(incidentCalls()[0][0]).toBe('/api/autonomous-ops/incidents?offset=0&limit=10');
  });

  it('reads many alerts as plural and several incidents as a count', async () => {
    routeFetch({ incidents: () => jsonRes(page([card({ alertCount: 3 }), card({ id: 'INC-2', actions: [line({ id: 'AO-2' })] })])) });
    await shown();
    expect(screen.getByText('2 incidents')).toBeInTheDocument();
    expect(screen.getByText('Started 12 min ago · 3 alerts')).toBeInTheDocument();
  });

  it('reports the incident ids it renders so the Activity list can link to them', async () => {
    const onDecisionIds = vi.fn();
    routeFetch({ incidents: () => jsonRes(page([card(), card({ id: 'INC-2', actions: [line({ id: 'AO-2' })] })])) });
    await shown({ onDecisionIds });
    await waitFor(() => {
      const last = onDecisionIds.mock.calls.at(-1)?.[0] as Set<string>;
      expect([...last].sort()).toEqual(['INC-1', 'INC-2']);
    });
  });

  it('a first-load error shows the heading, the alert and Try again; trying again shows the cards', async () => {
    let n = 0;
    routeFetch({ incidents: () => (n++ === 0 ? jsonRes({}, 500) : jsonRes(page([card()]))) });
    render(view());
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load approvals. Check your connection and try again.");
    expect(screen.getByRole('heading', { name: 'Needs your decision' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('article', { name: 'web-01' });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('a failed background read keeps the cards and shows nothing new', async () => {
    let n = 0;
    routeFetch({ incidents: () => (n++ === 0 ? jsonRes(page([card()])) : jsonRes({}, 500)) });
    await shown();
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(incidentCalls().length).toBe(2));
    await flush();
    expect(screen.getByRole('article', { name: 'web-01' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('pages ten cards, then Show more incidents loads the next page', async () => {
    const first = Array.from({ length: 10 }, (_, i) => card({ id: `INC-${i}`, host: `host-${i}`, actions: [line({ id: `AO-${i}` })] }));
    const rest = [card({ id: 'INC-10', host: 'host-10', actions: [line({ id: 'AO-10' })] })];
    routeFetch({
      incidents: (url) => (url.includes('offset=10') ? jsonRes(page(rest, { total: 11, offset: 10 })) : jsonRes(page(first, { total: 11 }))),
    });
    await shown();
    expect(screen.getAllByRole('article')).toHaveLength(10);
    expect(screen.getByText('11 incidents')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show more incidents' }));
    await screen.findByRole('article', { name: 'host-10' });
    expect(screen.getAllByRole('article')).toHaveLength(11);
    expect(screen.queryByRole('button', { name: 'Show more incidents' })).toBeNull();
  });

  it('announces the count only when it rises after a background read, never on first load', async () => {
    let n = 0;
    routeFetch({
      incidents: () => (n++ === 0
        ? jsonRes(page([card()]))
        : jsonRes(page([card(), card({ id: 'INC-2', actions: [line({ id: 'AO-2' })] })]))),
    });
    await shown();
    const live = document.querySelector('[data-live="decisions"]') as HTMLElement;
    expect(live).not.toBeNull();
    expect(live).toHaveAttribute('role', 'status');
    expect(live.textContent).toBe('');
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(live.textContent).toBe('2 incidents need your decision'));
  });

  it('long text wraps: a hostile or long host is text, never markup or a clamp', async () => {
    const hostile = '<img src=x onerror=alert(1)>';
    routeFetch({ incidents: () => jsonRes(page([card({ host: hostile, actions: [line({ reason: hostile, target: 'C:\\Users\\Public\\' + 'x'.repeat(120) + '.exe' })] })])) });
    const { container } = await shown();
    expect(container.querySelector('img')).toBeNull();
    expect(container.innerHTML).not.toContain('truncate');
    expect(screen.getAllByText(hostile).length).toBeGreaterThan(0);
  });
});

// ── approve and deny ────────────────────────────────────────────────────────

describe('Approve and Deny', () => {
  it('Approve names its target; two clicks send one request; the line pends, then settles and takes focus', async () => {
    let release!: (r: Response) => void;
    let n = 0;
    routeFetch({
      incidents: () => jsonRes(page(n++ === 0 ? [card()] : [])),
      decision: () => new Promise<Response>(r => { release = r; }),
    });
    const onDecided = vi.fn();
    const { container } = await shown({ onDecided });
    const approve = screen.getByRole('button', { name: 'Approve: Kill process powershell.exe on web-01' });
    expect(screen.getByRole('button', { name: 'Deny: Kill process powershell.exe on web-01' })).toBeEnabled();
    fireEvent.click(approve);
    fireEvent.click(approve);
    await flush();
    expect(decisionCalls()).toHaveLength(1);
    expect(decisionCalls()[0][0]).toBe('/api/autonomous-ops/actions/AO-1/approve');
    expect(decisionCalls()[0][1]).toMatchObject({ method: 'POST' });
    expect(screen.getByRole('button', { name: /Approve: Kill process/ })).toHaveTextContent('Approving...');
    expect(screen.getByRole('button', { name: /Approve: Kill process/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Deny: Kill process/ })).toBeDisabled();

    await act(async () => { release(jsonRes({ status: 'dispatched', action: { id: 'AO-1', bucket: 'pending', state: 'approved', resultText: 'Approved. Sent to web-01.' } })); });
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Approved. Sent to web-01.', 'success'));
    const row = container.querySelector('[data-action-id="AO-1"]') as HTMLElement;
    expect(row).toHaveAttribute('role', 'status');
    expect(document.activeElement).toBe(row);
    expect(within(row).getByText('Approved. Sent to web-01.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve:/ })).toBeNull();
    expect(onDecided).toHaveBeenCalledTimes(1);
    // The decision read finds the card gone; the settled card stays in place until the next background read.
    await waitFor(() => expect(incidentCalls().length).toBe(2));
    await flush();
    expect(screen.getByRole('article', { name: 'web-01' })).toBeInTheDocument();
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(screen.queryByRole('article', { name: 'web-01' })).toBeNull());
  });

  it('Deny sends one request, says so in a toast and leaves the other lines of the card alone', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card({ actions: [line(), line({ id: 'AO-2', command: 'isolate_host', label: 'Isolate host', target: null })] })])),
      decision: () => jsonRes({ status: 'denied', action: { id: 'AO-1', bucket: 'refused', state: 'denied', resultText: 'Denied by Pat.' } }),
    });
    await shown();
    fireEvent.click(screen.getByRole('button', { name: 'Deny: Kill process powershell.exe on web-01' }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Denied. Nothing was sent to web-01.', 'success'));
    expect(decisionCalls()[0][0]).toBe('/api/autonomous-ops/actions/AO-1/deny');
    expect(screen.getByRole('button', { name: 'Approve: Isolate host on web-01' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Deny: Isolate host on web-01' })).toBeEnabled();
  });

  it('three waiting lines have three pairs of buttons and no approve-all control', async () => {
    const lines = ['AO-1', 'AO-2', 'AO-3'].map(id => line({ id }));
    routeFetch({ incidents: () => jsonRes(page([card({ actions: lines })])) });
    await shown();
    expect(screen.getAllByRole('button', { name: /^Approve:/ })).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: /^Deny:/ })).toHaveLength(3);
    expect(screen.queryByRole('button', { name: /all/i })).toBeNull();
  });

  it('a 409 expired reads as expired; a 409 already_handled shows the server text', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card({ actions: [line(), line({ id: 'AO-2' })] })])),
      decision: (url) => (url.includes('AO-1')
        ? jsonRes({ detail: 'This request has expired.' }, 409)
        : jsonRes({ detail: 'This decision was already made.' }, 409)),
    });
    await shown();
    fireEvent.click(screen.getAllByRole('button', { name: /^Approve:/ })[0]);
    await screen.findByText('This request has expired and counts as denied.');
    fireEvent.click(screen.getByRole('button', { name: /^Approve:/ }));
    await screen.findByText('This decision was already made.');
    expect(screen.queryByRole('button', { name: /^Approve:/ })).toBeNull();
  });

  it('a failure keeps the line, shows the alert under the buttons and re-enables them', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card()])),
      decision: () => jsonRes({ detail: 'The host did not answer.' }, 500),
    });
    await shown();
    fireEvent.click(screen.getByRole('button', { name: /^Approve:/ }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't approve this action: The host did not answer. Try again.");
    expect(screen.getByRole('button', { name: /^Approve:/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /^Deny:/ })).toBeEnabled();
    expect(toast).not.toHaveBeenCalled();
  });

  it('a failure with no server message uses the fallback, for deny as well', async () => {
    routeFetch({ incidents: () => jsonRes(page([card()])), decision: () => { throw new Error('network'); } });
    await shown();
    fireEvent.click(screen.getByRole('button', { name: /^Deny:/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't deny this action. Check your connection and try again.");
  });

  it('a viewer without approval access sees the waiting line instead of buttons', async () => {
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line({ canApprove: false, canDeny: false })] })])) });
    await shown();
    expect(screen.getByText('Waiting for someone with approval access.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Approve|Deny)/ })).toBeNull();
  });

  it('a stop disables Approve with the reason and the amber block; Deny still works', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card()], { stopped: { scope: 'tenant' } })),
      decision: () => jsonRes({ status: 'denied', action: { id: 'AO-1', bucket: 'refused', state: 'denied', resultText: 'Denied by Pat.' } }),
    });
    await shown();
    const block = screen.getByText(
      'Approving is paused while automatic actions are stopped. You can still deny. Requests keep their 24-hour clock.',
    );
    expect(block.closest('[role="status"]')).not.toBeNull();
    const approve = screen.getByRole('button', { name: /^Approve:/ });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription(/Paused while automatic actions are stopped\./);
    expect(screen.getAllByText('Paused while automatic actions are stopped.').length).toBeGreaterThan(0);
    const deny = screen.getByRole('button', { name: /^Deny:/ });
    expect(deny).toBeEnabled();
    fireEvent.click(deny);
    await waitFor(() => expect(decisionCalls()).toHaveLength(1));
  });

  it('a platform stop names the whole platform, and the status stop disables Approve too', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card()])),
      status: () => jsonRes(statusPayload({ stop: { tenant: null, platform: { scope: 'platform', by: 'Root', at: at(-MIN), reason: null } } })),
    });
    await shown();
    await screen.findByText(
      'Approving is paused while automatic actions are stopped for the whole platform. You can still deny. Requests keep their 24-hour clock.',
    );
    expect(screen.getByRole('button', { name: /^Approve:/ })).toBeDisabled();
  });

  it('shadow mode hides the buttons', async () => {
    routeFetch({
      incidents: () => jsonRes(page([card()])),
      status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'tenant' } })),
    });
    await shown();
    await waitFor(() => expect(mockAuthFetch.mock.calls.some(c => String(c[0]).startsWith('/api/autonomous-ops/status'))).toBe(true));
    await flush();
    expect(screen.queryByRole('button', { name: /^(Approve|Deny)/ })).toBeNull();
  });

  it('more than five lines collapse behind Show n more actions', async () => {
    const six = Array.from({ length: 6 }, (_, i) => line({ id: `AO-${i}`, label: `Action ${i}` }));
    routeFetch({ incidents: () => jsonRes(page([card({ actions: six })])) });
    await shown();
    const article = screen.getByRole('article', { name: 'web-01' });
    expect(within(article).getAllByRole('listitem')).toHaveLength(5);
    const more = screen.getByRole('button', { name: 'Show 1 more actions' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(within(article).getAllByRole('listitem')).toHaveLength(6);
    const fewer = screen.getByRole('button', { name: 'Show fewer actions' });
    expect(fewer).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(fewer);
    expect(within(article).getAllByRole('listitem')).toHaveLength(5);
  });

  it('context lines that already ran have no buttons', async () => {
    const ran = line({
      id: 'AO-CTX', state: 'verified', bucket: 'done', command: 'block_ip', label: 'Block IP address', target: '203.0.113.7',
      needsPerson: false, expiresAt: null, canApprove: false, canDeny: false, consequenceText: null,
      result: 'Blocked for 24 hours. Verified: the firewall rule is in place.',
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line(), ran] })])) });
    await shown();
    const ctx = document.querySelector('[data-action-id="AO-CTX"]') as HTMLElement;
    expect(within(ctx).getByText('Done')).toBeInTheDocument();
    expect(within(ctx).getByText('Blocked for 24 hours. Verified: the firewall rule is in place.')).toBeInTheDocument();
    expect(within(ctx).queryByRole('button')).toBeNull();
    expect(screen.getAllByRole('button', { name: /^Approve:/ })).toHaveLength(1);
  });
});

// ── Task 2: Confirm isolation, kill cards, deadlines ────────────────────────

describe('Confirm isolation and the countdown', () => {
  it('an isolated line shows Done, the result, the Reverts in chip and the consequence with a local time', async () => {
    const iso = isolated();
    routeFetch({ incidents: () => jsonRes(page([card({ deadlineKind: 'reverts', deadlineAt: iso.revertsAt, actions: [iso] })])) });
    await shown();
    const row = document.querySelector('[data-action-id="AO-ISO"]') as HTMLElement;
    expect(within(row).getByText('Done')).toBeInTheDocument();
    expect(within(row).getByText('web-01 is isolated. The connection to the platform stays open.')).toBeInTheDocument();
    expect(within(row).getByText('Reverts in 3 h 12 min')).toBeInTheDocument();
    expect(screen.getAllByText('Reverts in 3 h 12 min').length).toBe(2); // the card header carries the nearest one too
    expect(within(row).getByText(
      `Confirming keeps this computer isolated until you restore it. Without it, the computer returns to the network automatically at ${clock(iso.revertsAt as string)}.`,
    )).toBeInTheDocument();
    expect(within(row).queryByText(/Approve|Deny/)).toBeNull();
    expect(within(row).getByRole('button', { name: 'Confirm isolation' })).toBeEnabled();
  });

  it('Confirm isolation is one click: Confirming..., toast, then Confirmed by the person at a time', async () => {
    let release!: (r: Response) => void;
    const iso = isolated();
    routeFetch({
      incidents: () => jsonRes(page([card({ deadlineKind: 'reverts', deadlineAt: iso.revertsAt, actions: [iso] })])),
      decision: () => new Promise<Response>(r => { release = r; }),
    });
    await shown();
    const button = screen.getByRole('button', { name: 'Confirm isolation' });
    fireEvent.click(button);
    fireEvent.click(button);
    await flush();
    expect(decisionCalls()).toHaveLength(1);
    expect(decisionCalls()[0][0]).toBe('/api/autonomous-ops/actions/AO-ISO/confirm-isolation');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: 'Confirm isolation' })).toHaveTextContent('Confirming...');
    expect(screen.getByRole('button', { name: 'Confirm isolation' })).toBeDisabled();
    await act(async () => { release(jsonRes({ status: 'confirmed', action: { id: 'AO-ISO', bucket: 'done', state: 'verified' } })); });
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Isolation confirmed. web-01 stays isolated until you restore it.', 'success'));
    const row = document.querySelector('[data-action-id="AO-ISO"]') as HTMLElement;
    expect(within(row).getByText(/^Confirmed by Pat at \d\d:\d\d\. The computer stays isolated until a person restores it\.$/)).toBeInTheDocument();
    expect(within(row).queryByRole('button')).toBeNull();
    expect(document.activeElement).toBe(row);
  });

  it('a confirmed line from the server fills its time from confirmedAt', async () => {
    const confirmedAt = at(-20 * MIN);
    const iso = isolated({
      needsPerson: false, canConfirmIsolation: false, confirmedAt, confirmedBy: 'Sam', consequenceText: null,
      result: 'Confirmed by Sam at {at}. The computer stays isolated until a person restores it.',
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line(), iso] })])) });
    await shown();
    expect(screen.getByText(`Confirmed by Sam at ${clock(confirmedAt)}. The computer stays isolated until a person restores it.`)).toBeInTheDocument();
  });

  it('a failed confirm shows the alert, keeps the line and re-enables the button', async () => {
    const iso = isolated();
    routeFetch({
      incidents: () => jsonRes(page([card({ actions: [iso] })])),
      decision: () => jsonRes({ detail: 'The isolation was already returned to the network automatically.' }, 409),
    });
    await shown();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm isolation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't confirm isolation: The isolation was already returned to the network automatically. Try again.",
    );
    expect(screen.getByRole('button', { name: 'Confirm isolation' })).toBeEnabled();
  });

  it('a confirm failure with no message uses the fallback', async () => {
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [isolated()] })])), decision: () => { throw new Error('offline'); } });
    await shown();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm isolation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't confirm isolation. Check your connection and try again.");
  });

  it('Confirm isolation is disabled during a stop with the same reason line', async () => {
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [isolated()] })], { stopped: { scope: 'tenant' } })) });
    await shown();
    const button = screen.getByRole('button', { name: 'Confirm isolation' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/Paused while automatic actions are stopped\./);
  });

  it('a viewer who cannot confirm sees the waiting line, and the chip is still there', async () => {
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [isolated({ canConfirmIsolation: false })] })])) });
    await shown();
    expect(screen.getByText('Waiting for someone with approval access.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm isolation' })).toBeNull();
    expect(screen.getAllByText('Reverts in 3 h 12 min').length).toBeGreaterThan(0);
  });

  it('a deadline in the past shows Expired and disables every button on the card', async () => {
    const past = line({ id: 'AO-OLD', expiresAt: at(-MIN) });
    const live = line({ id: 'AO-LIVE', label: 'Reboot host', command: 'reboot_host', target: null, expiresAt: at(2 * HOUR) });
    routeFetch({ incidents: () => jsonRes(page([card({ deadlineAt: at(-MIN), actions: [past, live] })])) });
    await shown();
    const article = screen.getByRole('article', { name: 'web-01' });
    expect(within(article).getAllByText('Expired').length).toBeGreaterThan(0);
    const old = document.querySelector('[data-action-id="AO-OLD"]') as HTMLElement;
    expect(within(old).getByText('This request has expired and counts as denied.')).toBeInTheDocument();
    expect(within(old).queryByRole('button')).toBeNull();
    expect(screen.getByRole('button', { name: /^Approve: Reboot host/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /^Deny: Reboot host/ })).toBeDisabled();
  });

  it('one timer recomputes the chips every 30 seconds, and the same timer re-reads the cards', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    const iso = isolated({ revertsAt: at(12 * MIN + 10_000) });
    routeFetch({ incidents: () => jsonRes(page([card({ deadlineKind: 'reverts', deadlineAt: iso.revertsAt, actions: [iso] })])) });
    render(view());
    await flush();
    expect(screen.getAllByText('Reverts in 12 min').length).toBeGreaterThan(0);
    expect(incidentCalls()).toHaveLength(1);
    await act(async () => { vi.advanceTimersByTime(30_000); });
    await flush();
    expect(screen.getAllByText('Reverts in 11 min').length).toBeGreaterThan(0);
    expect(incidentCalls()).toHaveLength(2);
    expect(document.querySelectorAll('[aria-live]').length).toBe(0);
  });
});

describe('Kill cards, protected file and restart over budget', () => {
  const chain = (steps: unknown[], mode = 'retry') => ({
    mode, steps, path: 'C:\\Users\\Public\\x.exe', process: { name: 'x.exe', pid: 4120 },
  });

  it('a kill-then-quarantine line is one line with both targets and the blue notice', async () => {
    const notice = "The file couldn't be moved because it is running. Approving ends the process, then tries the quarantine again. Nothing is deleted.";
    const kill = line({
      id: 'AO-K', label: 'Kill process, then quarantine file', target: 'x.exe (PID 4120)', reason: null, notice,
      consequenceText: 'Ends the process, then moves the file to quarantine. Nothing is deleted.',
      chain: chain([{ label: 'Kill process', state: 'pending' }, { label: 'Quarantine file', state: 'pending' }]),
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [kill] })])) });
    await shown();
    const row = document.querySelector('[data-action-id="AO-K"]') as HTMLElement;
    expect(within(row).getByText('Kill process, then quarantine file')).toBeInTheDocument();
    expect(within(row).getByText('x.exe (PID 4120)')).toBeInTheDocument();
    expect(within(row).getByText('C:\\Users\\Public\\x.exe')).toBeInTheDocument();
    expect(within(row).getByText(notice)).toBeInTheDocument();
    expect(within(row).getByText('Ends the process, then moves the file to quarantine. Nothing is deleted.')).toBeInTheDocument();
    expect(within(row).queryByRole('list')).toBeNull(); // no step list before the decision
    expect(screen.getAllByRole('button', { name: /^Approve:/ })).toHaveLength(1);
  });

  it('after approval an ordered step list gives each step its state, and a failed second step shows the result', async () => {
    const done = line({
      id: 'AO-K', state: 'verified', bucket: 'done', label: 'Kill process, then quarantine file', target: 'x.exe (PID 4120)',
      needsPerson: false, expiresAt: null, canApprove: false, canDeny: false, consequenceText: null, notice: null,
      result: 'The process was ended but the file is still in place: the file is still in use.',
      chain: chain([{ label: 'Kill process', state: 'done' }, { label: 'Quarantine file', state: 'failed' }]),
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line({ id: 'AO-2' }), done] })])) });
    await shown();
    const row = document.querySelector('[data-action-id="AO-K"]') as HTMLElement;
    const steps = within(row).getByRole('list', { name: 'Steps' });
    expect(steps.tagName).toBe('OL');
    const items = within(steps).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Kill process');
    expect(items[0]).toHaveTextContent('Done');
    expect(items[1]).toHaveTextContent('Quarantine file');
    expect(items[1]).toHaveTextContent('Failed');
    expect(within(row).getByText('The process was ended but the file is still in place: the file is still in use.')).toBeInTheDocument();
  });

  it('a step that never ran is named as such', async () => {
    const denied = line({
      id: 'AO-K', state: 'failed', bucket: 'failed', needsPerson: false, expiresAt: null, canApprove: false, canDeny: false,
      chain: chain([{ label: 'Kill process', state: 'failed' }, { label: 'Quarantine file', state: 'skipped' }]),
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line({ id: 'AO-2' }), denied] })])) });
    await shown();
    const items = within(screen.getByRole('list', { name: 'Steps' })).getAllByRole('listitem');
    expect(items[1]).toHaveTextContent('Quarantine file');
    expect(items[1]).toHaveTextContent('Not run');
  });

  it('a kill-only line shows its notice and the process, with no step list', async () => {
    const notice = 'The file was moved to quarantine, but its process is still running. Approving ends the process.';
    const kill = line({
      id: 'AO-K', label: 'Kill process', target: 'x.exe (PID 4120)', reason: null, notice, chain: chain([], 'kill_only'),
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [kill] })])) });
    await shown();
    const row = document.querySelector('[data-action-id="AO-K"]') as HTMLElement;
    expect(within(row).getByText(notice)).toBeInTheDocument();
    expect(within(row).getByText('x.exe (PID 4120)')).toBeInTheDocument();
    expect(within(row).queryByRole('list')).toBeNull();
  });

  it('the protected-file and over-budget restart lines show their server text', async () => {
    const protectedFile = line({
      id: 'AO-P', command: 'quarantine_file', label: 'Quarantine file', target: 'C:\\Windows\\System32\\x.dll',
      reason: "This is a protected system file, so it isn't moved automatically. Two sources flagged it.",
      consequenceText: 'Moves this system file to quarantine. If it is needed, this computer may stop working properly until you undo this. Nothing is deleted.',
    });
    const restart = line({
      id: 'AO-R', command: 'restart_service', label: 'Restart service', target: 'nginx',
      reason: 'Restarted nginx 3 times in the last hour. Further restarts need your approval.',
      consequenceText: 'Restarts nginx on this computer. If it fails again it stays down until you act.',
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [protectedFile, restart] })])) });
    await shown();
    for (const text of [protectedFile.reason, protectedFile.consequenceText, restart.reason, restart.consequenceText]) {
      expect(screen.getByText(text as string)).toBeInTheDocument();
    }
  });
});

describe('copy and markup rules', () => {
  it('the new components carry no HTML injection and no truncation', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    for (const file of ['components/AutonomousOpsDecisions.tsx', 'components/AutonomousOpsIncidentCard.tsx']) {
      const text = readFileSync(resolve(__dirname, '../..', file), 'utf-8');
      expect(text).not.toContain('dangerouslySetInnerHTML');
      expect(text).not.toMatch(/\btruncate\b/);
      expect(text).not.toMatch(/TimerIcon|HourglassIcon|UndoIcon/);
      expect(text.split('\n').length).toBeLessThan(500);
    }
  });
});
