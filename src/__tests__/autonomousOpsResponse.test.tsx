/**
 * Phase 83 / ACTV-02, RESP-02, RESP-03 (plan 83-10): Undo on Done rows, the Review link on Pending rows,
 * block times in local time, and suggestions that stay readable in volume. authFetch is mocked.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivityList } from '../../components/AutonomousOpsActivityList';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';

const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const NOW = Date.now();
const minutesAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'r1', bucket: 'done', state: 'verified', createdAt: minutesAgo(12),
    actionLabel: 'Block IP address', classLine: 'Automatic',
    reasonText: 'Two sources agree: OTX and VirusTotal.', ruleId: 'sweep:block_ip',
    host: 'web-01.example.com', target: '45.33.32.156', resultText: 'Blocked.', controlEvent: null,
    canUndo: false, undoHint: null, incidentId: null, blockedUntil: null, suggestion: null,
    ...over,
  };
}

const UNDOABLE = row({ canUndo: true, undoHint: 'Removes the block on 45.33.32.156.' });

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: false, canStopPlatform: false, canResumePlatform: false, ...over,
  };
}

type Undo = (url: string, init: RequestInit) => Response | Promise<Response>;

function route(opts: { rows?: unknown[]; undo?: Undo; status?: Record<string, unknown> } = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return jsonRes(statusPayload(opts.status));
    if (path === '/api/autonomous-ops/actions') return jsonRes({ items: opts.rows ?? [], nextCursor: null });
    if (/^\/api\/autonomous-ops\/actions\/[^/]+\/undo$/.test(path)) {
      return (opts.undo ?? (() => jsonRes({ status: 'undone', action: row({ state: 'undone', bucket: 'undone' }), breakerTripped: false })))(url, init);
    }
    throw new Error(`unexpected request ${url}`);
  });
}

const undoPosts = () => mockAuthFetch.mock.calls.filter(c =>
  (c[1] as RequestInit | undefined)?.method === 'POST' && /\/undo$/.test((c[0] as string).split('?')[0]));
const actionFetches = () => mockAuthFetch.mock.calls.filter(c => (c[0] as string).split('?')[0] === '/api/autonomous-ops/actions');

function shell(ui: React.ReactElement, can: (p: string) => boolean = () => true) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'p@example.com', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: [] } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: can as any, enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>{ui}</AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

const list = (props: Partial<React.ComponentProps<typeof AutonomousOpsActivityList>> = {}) => (
  <AutonomousOpsActivityList scope={{ kind: 'tenant', tenantId: null }} {...props} />
);

beforeEach(() => { mockAuthFetch.mockReset(); toast.mockReset(); });

const undoButtons = () => screen.findAllByRole('button', { name: 'Undo: Block IP address on web-01.example.com' });

// ── Task 1: Undo, Review link, block times, Setting chip ─────────────────────

describe('Undo on Done rows', () => {
  it('renders Undo with its hint when the server says canUndo, and nothing on the other rows', async () => {
    route({ rows: [
      UNDOABLE,
      row({ id: 'f', bucket: 'failed', state: 'failed' }),
      row({ id: 'x', bucket: 'refused', state: 'refused' }),
      row({ id: 's', bucket: 'suggested', state: 'suggested' }),
      row({ id: 'm', bucket: 'simulation', state: 'simulation' }),
      row({ id: 'c', bucket: 'control', controlEvent: 'stop_pressed', actionLabel: 'Stopped' }),
      row({ id: 'n', bucket: 'done', canUndo: false }),
    ] });
    render(shell(list()));
    expect((await undoButtons()).length).toBe(2); // the table and the stacked layout each render the one row
    expect(screen.getAllByText('Removes the block on 45.33.32.156.').length).toBe(2);
    expect(screen.queryAllByRole('button', { name: /^Undo:/ }).length).toBe(2);
  });

  it('sends one request for two clicks and shows Undoing... while it is pending', async () => {
    let release: (r: Response) => void = () => {};
    route({ rows: [UNDOABLE], undo: () => new Promise<Response>(res => { release = res; }) });
    render(shell(list()));
    const [button] = await undoButtons();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    expect(within(button).getByText('Undoing...')).toBeInTheDocument();
    expect(undoPosts().length).toBe(1);
    expect(undoPosts()[0][0]).toBe('/api/autonomous-ops/actions/r1/undo');
    await act(async () => { release(jsonRes({ status: 'undone', action: row({ state: 'undone', bucket: 'undone' }), breakerTripped: false })); });
  });

  it('stays available while automatic actions are stopped', async () => {
    const stop = { scope: 'tenant', by: 'Dana', at: minutesAgo(5), reason: null };
    route({ rows: [UNDOABLE], status: { stop: { tenant: stop, platform: null } } });
    render(shell(list()));
    const [button] = await undoButtons();
    expect(button).not.toBeDisabled();
  });

  it('on success shows the toast, swaps in the server row and moves focus to the Result cell', async () => {
    route({
      rows: [UNDOABLE],
      undo: () => jsonRes({ status: 'undone', action: row({ state: 'undone', bucket: 'undone', resultText: 'Block removed.' }), breakerTripped: false }),
    });
    render(shell(list()));
    const [button] = await undoButtons();
    const cell = button.closest('[data-result-cell]') as HTMLElement;
    expect(cell).not.toBeNull();
    expect(cell.getAttribute('tabindex')).toBe('-1');
    fireEvent.click(button);
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Undo sent to web-01.example.com.', 'success'));
    await waitFor(() => expect(screen.queryAllByRole('button', { name: /^Undo:/ }).length).toBe(0));
    expect(screen.getAllByText('Block removed.').length).toBeGreaterThan(0);
    expect(document.activeElement).toBe(cell);
  });

  it('shows the info toast and refreshes the status when the breaker tripped', async () => {
    route({ rows: [UNDOABLE], undo: () => jsonRes({ status: 'undone', action: row({ state: 'undone', bucket: 'undone' }), breakerTripped: true }) });
    render(shell(list()));
    const [button] = await undoButtons();
    const before = mockAuthFetch.mock.calls.filter(c => c[0] === '/api/autonomous-ops/status').length;
    fireEvent.click(button);
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(toast.mock.calls[0][0]).toBe(
      'Undo sent to web-01.example.com. Several automatic actions in a row were undone or failed, so this organization dropped to Suggest only. A person with manage access can restore it.');
    expect(toast.mock.calls[0][1]).toBe('info');
    await waitFor(() => expect(mockAuthFetch.mock.calls.filter(c => c[0] === '/api/autonomous-ops/status').length).toBeGreaterThan(before));
  });

  it('a 409 shows the server text as an alert under the button and refetches the rows', async () => {
    route({ rows: [UNDOABLE], undo: () => jsonRes({ detail: 'This action cannot be undone.' }, 409) });
    render(shell(list()));
    const [button] = await undoButtons();
    const fetchesBefore = actionFetches().length;
    fireEvent.click(button);
    const alert = (await screen.findAllByRole('alert')).find(a => /Couldn't undo/.test(a.textContent ?? ''))!;
    expect(alert).toHaveTextContent("Couldn't undo this action: This action cannot be undone. Try again.");
    await waitFor(() => expect(actionFetches().length).toBeGreaterThan(fetchesBefore));
    expect(toast).not.toHaveBeenCalled();
  });

  it('a network failure shows the fallback and lets the button be used again', async () => {
    route({ rows: [UNDOABLE], undo: () => { throw new Error('offline'); } });
    render(shell(list()));
    const [button] = await undoButtons();
    fireEvent.click(button);
    expect(await screen.findByText("Couldn't undo this action. Check your connection and try again.")).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it('renders the hint and every other server string as text, never as markup', async () => {
    route({ rows: [row({ canUndo: true, undoHint: '<img src=x onerror=alert(1)>' })] });
    const { container } = render(shell(list()));
    await undoButtons();
    expect(screen.getAllByText('<img src=x onerror=alert(1)>').length).toBeGreaterThan(0);
    expect(container.querySelector('img')).toBeNull();
  });
});

describe('Pending rows and the Review link', () => {
  const pending = row({ id: 'p1', bucket: 'pending', state: 'pending', actionLabel: 'Isolate host', classLine: 'Needs approval', incidentId: 'inc-1', resultText: 'Waiting for approval.' });

  it('links to the card only when the card is rendered, and focuses it', async () => {
    route({ rows: [pending] });
    render(shell(<><div id="approval-inc-1" tabIndex={-1}>card</div>{list({ decisionIds: new Set(['inc-1']) })}</>));
    const links = await screen.findAllByRole('button', { name: 'Review in Needs your decision' });
    expect(screen.getAllByText('Waiting for approval.').length).toBeGreaterThan(0);
    fireEvent.click(links[0]);
    expect(document.activeElement).toBe(document.getElementById('approval-inc-1'));
  });

  it('omits the link without the card, and without an incident id', async () => {
    route({ rows: [pending, row({ id: 'p2', bucket: 'pending', state: 'pending', incidentId: null })] });
    render(shell(list({ decisionIds: new Set(['other']) })));
    await screen.findAllByText('Waiting for approval.');
    expect(screen.queryByRole('button', { name: 'Review in Needs your decision' })).toBeNull();
  });
});

describe('Block times and the Setting chip', () => {
  it('fills {until} and {at} from blockedUntil in local time, with the full timestamp in title', async () => {
    const until = new Date(NOW + 3 * 3600_000).toISOString();
    route({ rows: [
      row({ id: 'a', blockedUntil: until, resultText: 'Blocked for 24 hours, until {until}. Verified: the firewall rule is in place.' }),
      row({ id: 'b', blockedUntil: until, resultText: 'Block removed automatically at {at} when its time ran out.' }),
    ] });
    const { container } = render(shell(list()));
    await screen.findAllByText(/Blocked for 24 hours, until /);
    expect(container.textContent).not.toContain('{until}');
    expect(container.textContent).not.toContain('{at}');
    expect(container.textContent).toMatch(/until [A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}\. Verified/);
    expect(container.textContent).toMatch(/automatically at \d{2}:\d{2} when its time ran out/);
    const titled = container.querySelector(`[title="${new Date(until).toLocaleString()}"]`);
    expect(titled).not.toBeNull();
  });

  it('shows a dash instead of a raw token when blockedUntil is missing', async () => {
    route({ rows: [row({ blockedUntil: null, resultText: 'Blocked for 24 hours, until {until}. Verified.' })] });
    const { container } = render(shell(list()));
    await screen.findAllByText(/Blocked for 24 hours/);
    expect(container.textContent).not.toContain('{until}');
  });

  it('gives a settings change the neutral Setting chip, not Resume', async () => {
    route({ rows: [row({ id: 'k', bucket: 'control', controlEvent: 'two_signal_off', actionLabel: 'Two-source rule turned off' })] });
    render(shell(list()));
    expect((await screen.findAllByText('Setting')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Resume')).toBeNull();
  });
});

// ── Task 2: suggestions in volume ────────────────────────────────────────────

const CVES = Array.from({ length: 10 }, (_, i) => ({ cve: `CVE-2026-000${i}`, package: `pkg-${i}` }));
const VULN = row({
  id: 'v1', bucket: 'suggested', state: 'suggested', actionLabel: 'Suggested: patch vulnerabilities', classLine: 'Suggestion only',
  reasonText: '240 known vulnerabilities reported by web-01.example.com. Highest severity: critical.', ruleId: null,
  target: null, resultText: 'No action was taken. Patching is where you apply fixes.',
  suggestion: { kind: 'vulnerability', count: 240, items: CVES, openView: 'patchManagement' },
});
const FILES = row({
  id: 'f1', bucket: 'suggested', state: 'suggested', actionLabel: 'Suggested: review file changes', classLine: 'Suggestion only',
  target: null, resultText: 'No action was taken. Check whether these changes were expected.',
  suggestion: { kind: 'file_change', count: 1, items: [{ path: '/etc/ssh/sshd_config' }], openView: 'fimMonitoring' },
});

describe('Suggested rows in volume', () => {
  it('shows three CVE ids and +237 more in Target, with the link and the toggle in Result', async () => {
    route({ rows: [VULN] });
    const onOpen = vi.fn();
    render(shell(list({ onOpenView: { patchManagement: onOpen } })));
    expect((await screen.findAllByText('CVE-2026-0000')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('CVE-2026-0002').length).toBeGreaterThan(0);
    expect(screen.queryByText('CVE-2026-0003')).toBeNull();
    expect(screen.getAllByText('+237 more').length).toBeGreaterThan(0);
    const open = screen.getAllByRole('button', { name: /Open patching/ });
    fireEvent.click(open[0]);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole('button', { name: 'Show details' }).length).toBeGreaterThan(0);
  });

  it('Show details lists 10 items and Showing 10 of 240 with the link', async () => {
    route({ rows: [VULN] });
    render(shell(list({ onOpenView: { patchManagement: vi.fn() } })));
    const [toggle] = await screen.findAllByRole('button', { name: 'Show details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent('Hide details');
    const region = document.getElementById(toggle.getAttribute('aria-controls')!)!;
    expect(within(region).getAllByRole('listitem').length).toBe(10);
    expect(within(region).getByText('CVE-2026-0009')).toBeInTheDocument();
    expect(region.textContent).toContain('Showing 10 of 240.');
    expect(within(region).getByRole('button', { name: /Open patching/ })).toBeInTheDocument();
  });

  it('renders plain text, not a link, when the viewer cannot open patching', async () => {
    route({ rows: [VULN] });
    render(shell(list({ onOpenView: {} })));
    await screen.findAllByText('+237 more');
    expect(screen.queryByRole('button', { name: /Open patching/ })).toBeNull();
    expect(screen.getAllByText('Open patching').length).toBeGreaterThan(0);
  });

  it('uses Open file integrity for a file-change row and reads 1 file', async () => {
    route({ rows: [FILES] });
    const onOpen = vi.fn();
    render(shell(list({ onOpenView: { fimMonitoring: onOpen } })));
    const links = await screen.findAllByRole('button', { name: /Open file integrity/ });
    fireEvent.click(links[0]);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('/etc/ssh/sshd_config').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Showing 1 of 1/)).toBeNull();
  });

  it('reads 1 vulnerability for a count of one and a dash for a missing field', async () => {
    route({ rows: [row({ ...VULN, id: 'v2', host: null, suggestion: { kind: 'vulnerability', count: 1, items: [], openView: 'patchManagement' } })] });
    render(shell(list()));
    expect((await screen.findAllByText('1 vulnerability')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('keeps a single-signal suggestion as its own row with no disclosure, and shows a correlation text verbatim', async () => {
    route({ rows: [
      row({ id: 'ss', bucket: 'suggested', state: 'suggested', actionLabel: 'Suggested: block IP address', classLine: 'Suggestion only',
        resultText: 'Nothing was done. If a second source agrees within 24 hours this runs on its own. After that it stays a suggestion.',
        suggestion: { kind: 'single_signal', count: 1, items: [], openView: null } }),
      row({ id: 'co', bucket: 'suggested', state: 'suggested', actionLabel: 'Suggested: isolate host', classLine: 'Suggestion only',
        resultText: 'Nothing was done. Correlation rules only suggest actions.',
        suggestion: { kind: 'correlation', count: 1, items: [], openView: null } }),
    ] });
    render(shell(list()));
    expect((await screen.findAllByText(/Correlation rules only suggest actions/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText('45.33.32.156').length).toBe(4); // two rows, two layouts: the ordinary Target
    expect(screen.queryByRole('button', { name: 'Show details' })).toBeNull();
  });

  it('the screen opens a view only for a target the viewer may open', async () => {
    route({ rows: [VULN, FILES] });
    const onOpenView = vi.fn();
    render(shell(
      <AutonomousOpsActivity onOpenView={onOpenView} />,
      p => p === 'view:patching' || p === 'view:autonomous_ops',
    ));
    const patching = await screen.findAllByRole('button', { name: /Open patching/ });
    fireEvent.click(patching[0]);
    expect(onOpenView).toHaveBeenCalledWith('patchManagement');
    expect(screen.queryByRole('button', { name: /Open file integrity/ })).toBeNull();
    expect(screen.getAllByText('Open file integrity').length).toBeGreaterThan(0);
  });
});
