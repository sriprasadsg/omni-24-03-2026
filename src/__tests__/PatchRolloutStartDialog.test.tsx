/**
 * Phase 84 / PTCH-01, PTCH-05, PTCH-07, D-03, D-11, D-12, D-13 (84-17): the Start a rollout dialog. authFetch is mocked
 * with the 84-09 payloads (GET /pending-patches and /draft, POST /preflight and POST /api/patch-rollouts).
 *
 * Value: protects=the operator sees every reason a rollout cannot start, and exactly what will happen, before pressing
 * Start, and nothing is stored until then; fails_when=Start is enabled with a blocker, no patch, a blank name, a stop or
 * before the first check returned, the check runs on every keystroke, a request in flight can be dismissed with Esc, a
 * failed Start is silent, a 409 leaves the old check on screen, a draft starts anything by itself, or server text is
 * rendered as markup; no_claim=the checks themselves (backend/tests/test_patch_rollout_start.py) and the tab wiring
 * (PatchRolloutsTab.test.tsx).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { PREFLIGHT_DEBOUNCE_MS, StartDialog } from '../../components/patchRollouts/StartDialog';
import type { StartDialogProps } from '../../components/patchRollouts/StartDialog';
import type { DraftPayload, PendingPatch, Preflight, PreflightRow } from '../../services/patchRollouts/types';
import { jsonRes } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const patch = (id: string, over: Partial<PendingPatch> = {}): PendingPatch =>
  ({ patchId: id, title: `Title of ${id}`, os: 'windows', computers: 3, ...over });
const row = (check: PreflightRow['check'], detail: string, over: Partial<PreflightRow> = {}): PreflightRow => ({
  check, ok: true, blocker: false, title: check === 'window' ? 'Window' : check === 'rings' ? 'Rings' : check === 'canary' ? 'Canary ring' : 'Left out',
  detail, link: null, hosts: [], hostTotal: 0, ...over,
});
const OK_ROWS: PreflightRow[] = [
  row('window', 'Next window: Sat 7 Nov, 03:00 (Asia/Kolkata).'),
  row('rings', '6 computers in 3 rings: Canary 1, Pilot 2, Everyone else 3.'),
  row('canary', 'The canary ring has a Windows computer.'),
];
const pre = (rows: PreflightRow[] = OK_ROWS): Preflight => ({
  rows, canStart: !rows.some(r => r.blocker), firstBlocker: rows.find(r => r.blocker)?.detail ?? null, nextWindowText: null,
});
const NO_WINDOW = row('window', 'Add a maintenance window first.', { ok: false, blocker: true, link: 'maintenance' });
const NO_CANARY_LINUX = row('canary', 'The canary ring has no Linux host; add one to the Canary group.', { ok: false, blocker: true, link: 'agentGroups' });
const NO_CANARY_COMPUTERS = row('rings', 'The canary ring has no computers. Pick a group for it in Rollout rings.', { ok: false, blocker: true, link: 'rings' });

let patches: PendingPatch[];
let preflightFor: (ids: string[]) => Preflight | Promise<Preflight>;
let startReply: () => Promise<Response>;
let draftReply: () => Promise<Response>;

const calls = (method: string, startsWith: string) =>
  mockFetch.mock.calls.filter(c => String(c[0]).startsWith(startsWith) && (c[1]?.method ?? 'GET') === method);
const preflightCalls = () => calls('POST', '/api/patch-rollouts/preflight');
const startCalls = () => mockFetch.mock.calls.filter(c => /^\/api\/patch-rollouts(\?|$)/.test(String(c[0])) && c[1]?.method === 'POST');
const bodyOf = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));

function serve(list: PendingPatch[] = [patch('KB5001'), patch('KB5002', { os: 'linux', computers: 1, title: 'openssl' })]) {
  patches = list;
  preflightFor = () => pre();
  startReply = () => Promise.resolve(jsonRes({ id: 'R9', name: 'Rollout x', simulation: false }, 201));
  draftReply = () => Promise.resolve(jsonRes({ name: 'Patches for CVE-2026-1 on web-01', patchIds: [], removedCount: 0, host: 'web-01', cves: ['CVE-2026-1'] }));
  mockFetch.mockReset();
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://x');
    if (u.pathname === '/api/patch-rollouts/pending-patches') {
      const search = (u.searchParams.get('search') ?? '').toLowerCase();
      const offset = Number(u.searchParams.get('offset') ?? 0);
      const limit = Number(u.searchParams.get('limit') ?? 50);
      const hits = patches.filter(p => !search || p.patchId.toLowerCase().includes(search) || p.title.toLowerCase().includes(search));
      return Promise.resolve(jsonRes({ items: hits.slice(offset, offset + limit), total: hits.length, offset, limit }));
    }
    if (u.pathname === '/api/patch-rollouts/preflight') {
      const ids = JSON.parse(String(init?.body)).patchIds as string[];
      return Promise.resolve(preflightFor(ids)).then(p => jsonRes(p));
    }
    if (u.pathname === '/api/patch-rollouts/draft') return draftReply();
    if (u.pathname === '/api/patch-rollouts' && init?.method === 'POST') return startReply();
    return Promise.resolve(jsonRes({}, 404));
  });
}

const show = (props: Partial<StartDialogProps> = {}) => {
  const handlers = { onClose: vi.fn(), onStarted: vi.fn() };
  const view = render(<StartDialog open stopped={false} {...handlers} {...props} />);
  return { ...handlers, ...view };
};

const startBtn = () => screen.getByRole('button', { name: /^(Start rollout|Starting\.\.\.)$/ });
const nameInput = () => screen.getByLabelText('Rollout name') as HTMLInputElement;
const tick = (id: string) => fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(id) }));
const ready = async () => { await screen.findByRole('checkbox', { name: /KB5001/ }); await screen.findByText(/Next window:/); };
const describedText = (button: HTMLElement) => {
  const id = button.getAttribute('aria-describedby');
  return id ? document.getElementById(id)?.textContent : null;
};

beforeEach(() => { toast.mockReset(); serve(); });
afterEach(() => { vi.useRealTimers(); });

describe('StartDialog: the form', () => {
  it('renders nothing and calls nothing while closed', () => {
    render(<StartDialog open={false} stopped={false} onClose={vi.fn()} onStarted={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('opens with the title, the name defaulted to Rollout {D Mon} with focus on it, and no close button', async () => {
    show();
    expect(screen.getByRole('dialog', { name: 'Start a rollout' })).toBeInTheDocument();
    expect(nameInput().value).toMatch(/^Rollout \d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$/);
    expect(document.activeElement).toBe(nameInput());
    expect(screen.queryByRole('button', { name: 'Close dialog' })).toBeNull();
    expect(screen.getByText('Shown in the list and when a computer is left out of another rollout.')).toBeInTheDocument();
    await ready();
  });

  it('the rollout name is capped at 60 characters', async () => {
    show();
    expect(nameInput()).toHaveAttribute('maxlength', '60');
    await ready();
  });

  it('a blank name shows Enter a name for this rollout. and disables Start', async () => {
    show();
    await ready();
    tick('KB5001');
    fireEvent.change(nameInput(), { target: { value: '   ' } });
    expect(screen.getByText('Enter a name for this rollout.')).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
    expect(describedText(startBtn())).toBe('Enter a name for this rollout.');
  });

  it('patch rows show the mono id, the title, the OS chip and the computer count; the counter follows the ticks', async () => {
    show();
    await ready();
    const first = screen.getByRole('checkbox', { name: /KB5001/ }).closest('li') as HTMLElement;
    expect(within(first).getByText('KB5001').className).toMatch(/font-mono/);
    expect(within(first).getByText('Title of KB5001').className).toMatch(/break-words/);
    expect(within(first).getByText('Windows')).toBeInTheDocument();
    expect(within(first).getByText('3 computers')).toBeInTheDocument();
    const second = screen.getByRole('checkbox', { name: /KB5002/ }).closest('li') as HTMLElement;
    expect(within(second).getByText('Linux')).toBeInTheDocument();
    expect(within(second).getByText('1 computer')).toBeInTheDocument();
    expect(screen.getByText('0 selected')).toBeInTheDocument();
    tick('KB5001'); tick('KB5002');
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('the patch list scrolls inside max-h-72 and says what it is', async () => {
    show();
    await ready();
    expect(screen.getByText('These are the updates your computers are waiting for.')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Patches to install' }).parentElement?.className).toMatch(/max-h-72/);
  });

  it('nothing pending: Nothing is waiting to be installed. and Start is disabled with that reason', async () => {
    serve([]);
    show();
    expect(await screen.findByText('Nothing is waiting to be installed.')).toBeInTheDocument();
    await screen.findByText(/Next window:/);
    expect(startBtn()).toBeDisabled();
    expect(describedText(startBtn())).toBe('Nothing is waiting to be installed.');
  });

  it('zero patches ticked keeps Start disabled with the pick-a-patch reason', async () => {
    show();
    await ready();
    expect(startBtn()).toBeDisabled();
    expect(describedText(startBtn())).toBe('Pick at least one patch to install.');
  });

  it('search asks the server, debounced, and keeps the ticks', async () => {
    show();
    await ready();
    tick('KB5001');
    fireEvent.change(screen.getByLabelText('Search patches'), { target: { value: 'openssl' } });
    await waitFor(() => expect(screen.queryByRole('checkbox', { name: /KB5001/ })).toBeNull());
    expect(screen.getByRole('checkbox', { name: /KB5002/ })).toBeInTheDocument();
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(calls('GET', '/api/patch-rollouts/pending-patches').some(c => String(c[0]).includes('search=openssl'))).toBe(true);
  });

  it('a search with no match says so', async () => {
    show();
    await ready();
    fireEvent.change(screen.getByLabelText('Search patches'), { target: { value: 'zzz' } });
    expect(await screen.findByText('No patches match your search.')).toBeInTheDocument();
  });

  it('shows 50 patches then Show more patches, which reads the next page', async () => {
    serve(Array.from({ length: 60 }, (_, i) => patch(`KB${1000 + i}`)));
    show();
    await screen.findByRole('checkbox', { name: /KB1000/ });
    expect(screen.getAllByRole('checkbox').length).toBe(50);
    fireEvent.click(screen.getByRole('button', { name: 'Show more patches' }));
    await waitFor(() => expect(screen.getAllByRole('checkbox').length).toBe(60));
    expect(screen.queryByRole('button', { name: 'Show more patches' })).toBeNull();
    expect(calls('GET', '/api/patch-rollouts/pending-patches').some(c => String(c[0]).includes('offset=50'))).toBe(true);
  });

  it('a failed patch read shows an alert with Try again', async () => {
    mockFetch.mockImplementation((url: string, init?: RequestInit) => (String(url).includes('pending-patches')
      ? Promise.resolve(jsonRes({}, 500))
      : Promise.resolve(jsonRes(pre()))));
    show();
    const alert = await screen.findByText("Couldn't load the patches. Check your connection and try again.");
    expect(alert).toBeInTheDocument();
    serve();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('checkbox', { name: /KB5001/ })).toBeInTheDocument();
  });

  it('server text is rendered as text only', async () => {
    serve([patch('KB1', { title: '<img src=x onerror=alert(1)>' })]);
    const { baseElement } = show();
    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(baseElement.querySelector('img')).toBeNull();
  });

  it('the What will happen block closes the form with the four lines and the platform note', async () => {
    show();
    await ready();
    expect(screen.getByText('Installs and restarts run only inside your maintenance window.')).toBeInTheDocument();
    expect(screen.getByText('Only the canary ring installs on its own, and only patches that can be reversed on that computer. That is checked just before each install.')).toBeInTheDocument();
    expect(screen.getByText('Every other install and every restart waits for your approval, one ring at a time.')).toBeInTheDocument();
    expect(screen.getByText('A rollout halts on failure; reverts where supported. Nothing is installed outside your maintenance window.')).toBeInTheDocument();
    expect(screen.getByText("The platform's own server is never patched by a rollout.")).toBeInTheDocument();
  });
});

describe('StartDialog: the check before starting', () => {
  it('reads the server preflight with the ticked ids, debounced 300 ms into one call', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    show();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(PREFLIGHT_DEBOUNCE_MS); });
    const afterOpen = preflightCalls().length;
    expect(afterOpen).toBe(1);
    expect(bodyOf(preflightCalls()[0])).toEqual({ patchIds: [] });
    tick('KB5001'); tick('KB5002');
    await act(async () => { await vi.advanceTimersByTimeAsync(PREFLIGHT_DEBOUNCE_MS - 10); });
    expect(preflightCalls().length).toBe(afterOpen);
    await act(async () => { await vi.advanceTimersByTimeAsync(20); });
    expect(preflightCalls().length).toBe(afterOpen + 1);
    expect(bodyOf(preflightCalls()[afterOpen])).toEqual({ patchIds: ['KB5001', 'KB5002'] });
  });

  it('shows Checking... while a check is in flight and keeps the previous result visible', async () => {
    show();
    await ready();
    let release: (p: Preflight) => void = () => {};
    preflightFor = () => new Promise<Preflight>(resolve => { release = resolve; });
    tick('KB5001');
    expect(await screen.findByText('Checking...')).toBeInTheDocument();
    expect(screen.getByText('Next window: Sat 7 Nov, 03:00 (Asia/Kolkata).')).toBeInTheDocument();
    await act(async () => { release(pre([row('window', 'Next window: Sun 8 Nov, 03:00 (Asia/Kolkata).')])); });
    expect(await screen.findByText('Next window: Sun 8 Nov, 03:00 (Asia/Kolkata).')).toBeInTheDocument();
    expect(screen.queryByText('Checking...')).toBeNull();
  });

  it('the check area is a polite status region', async () => {
    show();
    await ready();
    const region = screen.getByRole('status', { name: 'Check before starting' });
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(within(region).getByText('Canary ring')).toBeInTheDocument();
  });

  it('Start is disabled until the first check returns', async () => {
    let release: (p: Preflight) => void = () => {};
    preflightFor = () => new Promise<Preflight>(resolve => { release = resolve; });
    show();
    await screen.findByRole('checkbox', { name: /KB5001/ });
    tick('KB5001');
    await waitFor(() => expect(preflightCalls().length).toBeGreaterThan(0));
    expect(startBtn()).toBeDisabled();
    expect(describedText(startBtn())).toBe('Checking...');
    await act(async () => { release(pre()); });
    await waitFor(() => expect(startBtn()).not.toBeDisabled());
  });

  it('a passing check enables Start once a patch is ticked', async () => {
    show();
    await ready();
    tick('KB5001');
    await waitFor(() => expect(startBtn()).not.toBeDisabled());
    expect(startBtn().className).toMatch(/bg-primary-600/);
  });

  it('a blocker disables Start with aria-describedby on the first blocker text', async () => {
    preflightFor = () => pre([NO_WINDOW, NO_CANARY_LINUX]);
    show();
    await screen.findByRole('checkbox', { name: /KB5001/ });
    tick('KB5001');
    await screen.findByText('Add a maintenance window first.');
    await waitFor(() => expect(startBtn()).toBeDisabled());
    expect(describedText(startBtn())).toBe('Add a maintenance window first.');
  });

  it('the maintenance link calls the handler, and is plain text without one', async () => {
    preflightFor = () => pre([NO_WINDOW]);
    const onOpenMaintenance = vi.fn();
    const first = show({ onOpenMaintenance });
    fireEvent.click(await screen.findByRole('button', { name: 'Open maintenance windows' }));
    expect(onOpenMaintenance).toHaveBeenCalledTimes(1);
    first.unmount();
    show();
    expect(await screen.findByText('Open maintenance windows')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open maintenance windows' })).toBeNull();
  });

  it('a canary gap links to Open agent groups and a missing canary group links to Open rollout rings', async () => {
    preflightFor = () => pre([NO_CANARY_LINUX, NO_CANARY_COMPUTERS]);
    const onOpenAgentGroups = vi.fn();
    const onOpenRings = vi.fn();
    show({ onOpenAgentGroups, onOpenRings });
    fireEvent.click(await screen.findByRole('button', { name: 'Open agent groups' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open rollout rings' }));
    expect(onOpenAgentGroups).toHaveBeenCalledTimes(1);
    expect(onOpenRings).toHaveBeenCalledTimes(1);
  });

  it('a stop disables Start with the paused reason', async () => {
    show({ stopped: true });
    await ready();
    tick('KB5001');
    await waitFor(() => expect(preflightCalls().length).toBeGreaterThan(1));
    expect(startBtn()).toBeDisabled();
    expect(describedText(startBtn())).toBe('Paused while automatic actions are stopped.');
  });

  it('Left out reads 1 host singular and plural, for one rollout per line', async () => {
    preflightFor = () => pre([
      ...OK_ROWS,
      row('left_out', '1 host is in "Oct security" and was left out.', { hosts: ['db-01'], hostTotal: 1 }),
      row('left_out', '3 hosts are in "November security" and were left out.', { hosts: ['a', 'b', 'c'], hostTotal: 3 }),
    ]);
    show();
    expect(await screen.findByText('1 host is in "Oct security" and was left out.')).toBeInTheDocument();
    expect(screen.getByText('3 hosts are in "November security" and were left out.')).toBeInTheDocument();
  });

  it('Left out lists three lines then and {k} more, and the reasons use the server sentences', async () => {
    const lines = ['A', 'B', 'C', 'D', 'E'].map(n => row('left_out', `2 hosts are in "${n}" and were left out.`, { hosts: ['x', 'y'], hostTotal: 2 }));
    preflightFor = () => pre([...OK_ROWS, ...lines, row('left_out', 'The agent on this computer is too old to take a rollout.', { hosts: ['old-01'], hostTotal: 1 })]);
    show();
    await screen.findByText('2 hosts are in "A" and were left out.');
    expect(screen.getByText('2 hosts are in "C" and were left out.')).toBeInTheDocument();
    expect(screen.queryByText('2 hosts are in "D" and were left out.')).toBeNull();
    expect(screen.getByText('and 3 more')).toBeInTheDocument();
  });

  it('a computer that cannot take a rollout is listed with the server reason', async () => {
    preflightFor = () => pre([...OK_ROWS, row('left_out', 'This computer is on the never-touch list.', { hosts: ['vault-01'], hostTotal: 1 })]);
    show();
    expect(await screen.findByText('This computer is on the never-touch list.')).toBeInTheDocument();
  });

  it('Show hosts lists the names in mono and says Showing 10 of {n}.', async () => {
    const names = Array.from({ length: 10 }, (_, i) => `host-${i}`);
    preflightFor = () => pre([...OK_ROWS, row('left_out', '14 hosts are in "Nov" and were left out.', { hosts: names, hostTotal: 14 })]);
    show();
    const toggle = await screen.findByRole('button', { name: 'Show hosts' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('host-0')).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('host-0').className).toMatch(/font-mono/);
    expect(screen.getAllByText(/^host-\d$/)).toHaveLength(10);
    expect(screen.getByText('Showing 10 of 14.')).toBeInTheDocument();
  });

  it('offline computers get the info row', async () => {
    preflightFor = () => pre([...OK_ROWS, row('offline', '2 computers are offline now. They get the patches in a later window if they come back online.', { title: 'Offline now', hosts: ['p', 'q'], hostTotal: 2 })]);
    show();
    expect(await screen.findByText('2 computers are offline now. They get the patches in a later window if they come back online.')).toBeInTheDocument();
  });

  it('a failed check keeps Start disabled and offers Try again', async () => {
    mockFetch.mockImplementation((url: string) => (String(url).includes('/preflight')
      ? Promise.resolve(jsonRes({}, 500))
      : Promise.resolve(jsonRes({ items: [patch('KB5001')], total: 1, offset: 0, limit: 50 }))));
    show();
    expect(await screen.findByText("Couldn't check this rollout. Check your connection and try again.")).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
    serve();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/Next window:/)).toBeInTheDocument();
  });
});

describe('StartDialog: Start', () => {
  const startReady = async (props: Partial<StartDialogProps> = {}) => {
    const out = show(props);
    await ready();
    tick('KB5001');
    await waitFor(() => expect(startBtn()).not.toBeDisabled());
    return out;
  };

  it('nothing is stored before Start: only reads and the check ran', async () => {
    await startReady();
    expect(startCalls()).toHaveLength(0);
  });

  it('Start sends the trimmed name and the ticked ids, toasts, calls onStarted and closes', async () => {
    const { onStarted, onClose } = await startReady();
    fireEvent.change(nameInput(), { target: { value: '  November patches  ' } });
    startReply = () => Promise.resolve(jsonRes({ id: 'R9', name: 'November patches', simulation: false }, 201));
    fireEvent.click(startBtn());
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('R9'));
    expect(bodyOf(startCalls()[0])).toEqual({ name: 'November patches', patchIds: ['KB5001'] });
    expect(toast).toHaveBeenCalledWith('Rollout "November patches" started. The canary ring goes first.', 'success');
    expect(onClose).toHaveBeenCalled();
  });

  it('a simulation says nothing will be installed', async () => {
    const { onStarted } = await startReady();
    startReply = () => Promise.resolve(jsonRes({ id: 'R9', name: 'Sim', simulation: true }, 201));
    fireEvent.click(startBtn());
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith('Rollout "Sim" started as a simulation. Nothing will be installed.', 'success');
  });

  it('shows Starting... and ignores Esc and the Close button while the request is in flight', async () => {
    const { onClose } = await startReady();
    let finish: (r: Response) => void = () => {};
    startReply = () => new Promise<Response>(resolve => { finish = resolve; });
    fireEvent.click(startBtn());
    expect(startBtn()).toHaveTextContent('Starting...');
    expect(startBtn()).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Close without starting' })).toBeDisabled();
    await act(async () => { finish(jsonRes({ id: 'R9', name: 'x', simulation: false }, 201)); });
  });

  it('Esc and Close without starting close the dialog when nothing is in flight', async () => {
    const first = show();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(first.onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Close without starting' }));
    expect(first.onClose).toHaveBeenCalledTimes(2);
    await ready();
  });

  it('a failed Start shows the red alert with the server message and keeps the form', async () => {
    const { onStarted } = await startReady();
    startReply = () => Promise.resolve(jsonRes({ detail: 'Rollouts need a maintenance window.' }, 500));
    fireEvent.click(startBtn());
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't start the rollout: Rollouts need a maintenance window. Try again.");
    expect(onStarted).not.toHaveBeenCalled();
    expect(startBtn()).not.toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /KB5001/ })).toBeChecked();
  });

  it('a failed Start with no message shows the fallback', async () => {
    await startReady();
    startReply = () => Promise.resolve(jsonRes({}, 500));
    fireEvent.click(startBtn());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't start the rollout. Check your connection and try again.");
  });

  it('a network error shows the fallback', async () => {
    await startReady();
    startReply = () => Promise.reject(new Error('offline'));
    fireEvent.click(startBtn());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't start the rollout. Check your connection and try again.");
  });

  it('a 409 already_in_rollout reads the check again at once and shows the Left out row', async () => {
    await startReady();
    const before = preflightCalls().length;
    preflightFor = () => pre([...OK_ROWS, row('left_out', '2 hosts are in "Other rollout" and were left out.', { hosts: ['a', 'b'], hostTotal: 2 })]);
    startReply = () => Promise.resolve(jsonRes({ detail: 'One or more of these computers are already in another rollout.', code: 'already_in_rollout' }, 409));
    fireEvent.click(startBtn());
    expect(await screen.findByText('2 hosts are in "Other rollout" and were left out.')).toBeInTheDocument();
    expect(preflightCalls().length).toBeGreaterThan(before);
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't start the rollout: One or more of these computers are already in another rollout. Try again.");
  });

  it('a 422 with rows reads the check again and shows its blocker', async () => {
    await startReady();
    preflightFor = () => pre([NO_WINDOW]);
    startReply = () => Promise.resolve(jsonRes({ detail: 'Add a maintenance window first.', rows: [NO_WINDOW] }, 422));
    fireEvent.click(startBtn());
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("Couldn't start the rollout: Add a maintenance window first. Try again."));
    await waitFor(() => expect(startBtn()).toBeDisabled());
  });

  it('sends the viewed organization on every call', async () => {
    const { onStarted } = await startReady({ tenantId: 'tenant_x' });
    fireEvent.click(startBtn());
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    for (const call of mockFetch.mock.calls) expect(String(call[0])).toContain('tenantId=tenant_x');
  });
});

describe('StartDialog: a draft from a vulnerability suggestion', () => {
  const draft = (over: Partial<DraftPayload> = {}) => {
    draftReply = () => Promise.resolve(jsonRes({
      name: 'Patches for CVE-2026-1 on web-01', patchIds: ['KB5001'], removedCount: 0, host: 'web-01', cves: ['CVE-2026-1'], ...over,
    }));
  };

  it('pre-ticks the suggested patches, sets the name and shows the blue block; nothing starts by itself', async () => {
    draft();
    show({ draftSuggestionId: 's1' });
    expect(await screen.findByText('Filled in from the vulnerabilities reported by web-01. Nothing starts until you press Start rollout.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /KB5001/ })).toBeChecked());
    expect(nameInput().value).toBe('Patches for CVE-2026-1 on web-01');
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(calls('GET', '/api/patch-rollouts/draft')[0][0]).toBe('/api/patch-rollouts/draft?suggestion=s1');
    expect(startCalls()).toHaveLength(0);
  });

  it('says how many suggested patches were dropped, singular and plural', async () => {
    draft({ removedCount: 3 });
    const first = show({ draftSuggestionId: 's1' });
    expect(await screen.findByText('3 patches are no longer needed and were removed.')).toBeInTheDocument();
    first.unmount();
    draft({ removedCount: 1 });
    show({ draftSuggestionId: 's1' });
    expect(await screen.findByText('1 patch is no longer needed and was removed.')).toBeInTheDocument();
  });

  it('with none still pending the dialog opens with nothing ticked and Start disabled', async () => {
    draft({ patchIds: [], removedCount: 2 });
    show({ draftSuggestionId: 's1' });
    await screen.findByText('2 patches are no longer needed and were removed.');
    await ready();
    expect(screen.getByText('0 selected')).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
  });

  it('a draft that cannot be read opens the dialog without the block and with nothing ticked', async () => {
    draftReply = () => Promise.resolve(jsonRes({ detail: 'Suggestion not found.' }, 404));
    show({ draftSuggestionId: 's1' });
    await ready();
    await waitFor(() => expect(calls('GET', '/api/patch-rollouts/draft').length).toBe(1));
    expect(screen.queryByText(/Filled in from the vulnerabilities/)).toBeNull();
    expect(screen.getByText('0 selected')).toBeInTheDocument();
  });

  it('without a draft id nothing is fetched for a draft', async () => {
    show();
    await ready();
    expect(calls('GET', '/api/patch-rollouts/draft')).toHaveLength(0);
  });
});
