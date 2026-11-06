/**
 * Phase 84 / PTCH-01, PTCH-04, PTCH-05 (84-14): the Rollouts tab on the Patching screen. authFetch is mocked with the
 * 84-09 payloads (GET /api/patch-rollouts, /window, /{id}).
 *
 * Value: protects=the operator sees the window state, the assurance line and every rollout on the Patching screen, in
 * every loading, empty, error, stop and shadow case, and the tab badge counts what needs a person; fails_when=the
 * Rollouts tab is missing or out of order, the badge shows at zero, a background poll shows a skeleton or an error,
 * the live region speaks on first load, polling continues while the tab is hidden, or a control renders without its
 * server flag; no_claim=the server payloads (backend/tests/test_patch_rollout_views.py) and the card
 * (PatchRolloutCard.test.tsx).
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
import { fetchRollout, fetchRollouts, fetchWindowStrip } from '../../services/patchRollouts/rollouts';
import { PatchManagementDashboard } from '../../components/PatchManagementDashboard';
import { RolloutsTab } from '../../components/patchRollouts/RolloutsTab';
import type { RolloutsTabProps } from '../../components/patchRollouts/RolloutsTab';
import { UserContext } from '../../contexts/UserContext';
import type { RolloutCard, RolloutPage } from '../../services/patchRollouts/types';
import { card, flags, jsonRes, openWindow, rolloutPage } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => { mockFetch.mockReset(); });

describe('rollouts calls', () => {
  it('fetchRollouts asks for the page, with the viewed organization when given', async () => {
    mockFetch.mockResolvedValue(jsonRes(rolloutPage([card()])));
    await fetchRollouts({ offset: 10, limit: 10, tenantId: 'tenant_x' });
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts?offset=10&limit=10&tenantId=tenant_x');
    mockFetch.mockClear();
    await fetchRollouts({});
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts?offset=0&limit=10');
  });

  it('fetchRollout and fetchWindowStrip use /{id} and /window', async () => {
    mockFetch.mockResolvedValue(jsonRes(card()));
    await fetchRollout('R 1');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R%201');
    mockFetch.mockClear();
    mockFetch.mockResolvedValue(jsonRes({ state: 'none', text: '', closesAt: null, nextOpensAt: null, timeZone: null }));
    await fetchWindowStrip('tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/window?tenantId=tenant_x');
  });

  it('a failed call carries the status and the server sentence', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Rollouts need a maintenance window.' }, 422));
    await expect(fetchRollouts({})).rejects.toMatchObject({ status: 422, detail: 'Rollouts need a maintenance window.' });
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    await expect(fetchRollout('R1')).rejects.toMatchObject({ status: 500, detail: '' });
  });
});

describe('PatchManagementDashboard Rollouts tab', () => {
  const dashboard = (props: Record<string, unknown> = {}) => render(
    <PatchManagementDashboard patches={[]} assets={[]} patchDeploymentJobs={[]} vulnerabilityScanJobs={[]}
      onSchedulePatchDeployment={vi.fn()} onScheduleVulnerabilityScan={vi.fn()} tenantId={null} {...props} />);

  const serve = (attention: number) => mockFetch.mockImplementation((url: string) => Promise.resolve(
    url.startsWith('/api/patch-rollouts')
      ? jsonRes(rolloutPage([card()], { attentionCount: attention }))
      : jsonRes([])));

  const tabNames = () => screen.getAllByRole('button')
    .map(b => b.textContent ?? '')
    .filter(t => /Patches & Deployment|Software Updates|OS Patches|Rollouts|Agent Approvals/.test(t));

  it('lists Rollouts between OS Patches and Agent Approvals, with no emoji', async () => {
    serve(0);
    dashboard();
    const names = tabNames();
    const index = (word: string) => names.findIndex(n => n.includes(word));
    expect(index('Patches & Deployment')).toBeLessThan(index('Software Updates'));
    expect(index('Software Updates')).toBeLessThan(index('OS Patches'));
    expect(index('OS Patches')).toBeLessThan(index('Rollouts'));
    expect(index('Rollouts')).toBeLessThan(index('Agent Approvals'));
    expect(names[index('Rollouts')]).toMatch(/^Rollouts/);
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
  });

  it('shows an amber badge with the number of rollouts that need a person, and hides it at zero', async () => {
    serve(2);
    dashboard();
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(await within(tab).findByText('2')).toBeInTheDocument();
    expect(mockFetch.mock.calls.some(c => c[0] === '/api/patch-rollouts?offset=0&limit=1')).toBe(true);
  });

  it('shows no badge at zero', async () => {
    serve(0);
    dashboard();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(tab.textContent).toBe('Rollouts');
  });

  it('re-reads the badge on window focus', async () => {
    serve(0);
    dashboard();
    await waitFor(() => expect(mockFetch.mock.calls.some(c => String(c[0]).startsWith('/api/patch-rollouts'))).toBe(true));
    serve(3);
    act(() => { window.dispatchEvent(new Event('focus')); });
    const tab = screen.getByRole('button', { name: /^Rollouts/ });
    expect(await within(tab).findByText('3')).toBeInTheDocument();
  });

  it('a failed badge read shows no badge and no error', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'x' }, 500));
    dashboard();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^Rollouts/ }).textContent).toBe('Rollouts');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('selecting the tab renders the Rollouts section', async () => {
    serve(0);
    dashboard();
    fireEvent.click(screen.getByRole('button', { name: /^Rollouts/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Rollouts' })).toBeInTheDocument();
  });

  it('the badge read follows the viewed organization', async () => {
    serve(0);
    dashboard({ tenantId: 'tenant_b' });
    await waitFor(() => expect(mockFetch.mock.calls.some(
      c => c[0] === '/api/patch-rollouts?offset=0&limit=1&tenantId=tenant_b')).toBe(true));
  });
});


// ---------------------------------------------------------------- the tab

const FIRST_LOAD_ERROR = "Couldn't load rollouts. Check your connection and try again.";
const STOP_TENANT =
  'Rollouts are paused while automatic actions are stopped. Nothing new installs or restarts. A revert that is already under way still runs.';
const STOP_PLATFORM =
  'Rollouts are paused while automatic actions are stopped for the whole platform. Nothing new installs or restarts. A revert that is already under way still runs.';
const SHADOW =
  'Shadow mode is on for this organization. A rollout runs as a simulation: it records what it would have done and installs and restarts nothing.';
const ASSURANCE = 'A rollout halts on failure; reverts where supported. Nothing is installed outside your maintenance window.';

/** What the server answers, as a function of the url, so paging reads the right slice. */
interface Served { cards: RolloutCard[]; over: Partial<RolloutPage>; failing: boolean }
let served: Served;

function serveRollouts(cards: RolloutCard[], over: Partial<RolloutPage> = {}) {
  served = { cards, over, failing: false };
  mockFetch.mockImplementation((url: string) => {
    const q = new URL(url, 'http://x');
    // The Rollout rings card (84-17) reads its own settings once; it is not part of the polled list.
    if (q.pathname === '/api/patch-rollouts/rings') return Promise.resolve(jsonRes({ rings: [], readable: true, groups: [] }));
    if (served.failing) return Promise.resolve(jsonRes({ detail: 'down' }, 500));
    const offset = Number(q.searchParams.get('offset') ?? 0);
    const limit = Number(q.searchParams.get('limit') ?? 10);
    return Promise.resolve(jsonRes(rolloutPage(served.cards.slice(offset, offset + limit),
      { total: served.cards.length, offset, limit, ...served.over })));
  });
}

const names = (n: number) => Array.from({ length: n }, (_, i) => card({ id: `R${i + 1}`, name: `Rollout ${i + 1}` }));
const rolloutCalls = () => mockFetch.mock.calls.filter(c => String(c[0]).startsWith('/api/patch-rollouts?'));

const show = (props: Partial<RolloutsTabProps> = {}, user: Record<string, unknown> = {}) => render(
  <UserContext.Provider value={{
    currentUser: null, login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
    hasPermission: () => false, enabledFeatures: [], serverLockedFeatures: {}, ...user,
  } as never}>
    <RolloutsTab tenantId={null} {...props} />
  </UserContext.Provider>);

const setVisibility = (state: 'visible' | 'hidden') =>
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });

describe('RolloutsTab', () => {
  afterEach(() => { vi.useRealTimers(); setVisibility('visible'); });

  it('first load shows three h-24 skeleton cards, aria-busy on the section, and the assurance line', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { container } = show();
    expect(container.querySelector('section[aria-busy="true"]')).not.toBeNull();
    expect(container.querySelectorAll('.h-24')).toHaveLength(3);
    expect(screen.getByText(ASSURANCE)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Rollouts' })).toBeInTheDocument();
  });

  it('after the first read there is no skeleton and the section is not busy', async () => {
    serveRollouts(names(2));
    const { container } = show();
    expect(await screen.findByText('Rollout 1')).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
    expect(container.querySelectorAll('.h-24')).toHaveLength(0);
  });

  it('a first-load failure shows the red alert with Try again, keeps the assurance line, and Try again reads again', async () => {
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    show();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(FIRST_LOAD_ERROR);
    expect(screen.getByText(ASSURANCE)).toBeInTheDocument();
    serveRollouts(names(1));
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Rollout 1')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('cards appear in the order the server sends them', async () => {
    serveRollouts([card({ id: 'a', name: 'Halted one', status: 'halted' }), card({ id: 'b', name: 'Running one' }),
      card({ id: 'c', name: 'Done one', status: 'completed' })]);
    show();
    await screen.findByText('Halted one');
    const order = screen.getAllByRole('article').map(a => a.id);
    expect(order).toEqual(['rollout-a', 'rollout-b', 'rollout-c']);
  });

  it('a background poll every 30 s shows no skeleton, no spinner and no busy state while it is in flight', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serveRollouts(names(1));
    const { container } = show();
    await screen.findByText('Rollout 1');
    mockFetch.mockClear();
    mockFetch.mockReturnValue(new Promise(() => {}));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(rolloutCalls()).toHaveLength(1);
    expect(screen.getByText('Rollout 1')).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
    expect(container.querySelectorAll('.h-24')).toHaveLength(0);
  });

  it('a failed background poll keeps the last cards and shows nothing new', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serveRollouts(names(2));
    show();
    await screen.findByText('Rollout 2');
    served.failing = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByText('Rollout 1')).toBeInTheDocument();
    expect(screen.getByText('Rollout 2')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(FIRST_LOAD_ERROR)).toBeNull();
  });

  it('polling stops while the document is hidden and while the tab is not active', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serveRollouts(names(1));
    const view = show();
    await screen.findByText('Rollout 1');
    mockFetch.mockClear();
    setVisibility('hidden');
    await act(async () => { await vi.advanceTimersByTimeAsync(95_000); });
    expect(rolloutCalls()).toHaveLength(0);
    setVisibility('visible');
    view.rerender(<UserContext.Provider value={{ hasPermission: () => false } as never}><RolloutsTab tenantId={null} active={false} /></UserContext.Provider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(95_000); });
    expect(rolloutCalls()).toHaveLength(0);
  });

  it('reads again on window focus and on Refresh', async () => {
    serveRollouts(names(1));
    show();
    await screen.findByText('Rollout 1');
    const before = rolloutCalls().length;
    act(() => { window.dispatchEvent(new Event('focus')); });
    await waitFor(() => expect(rolloutCalls().length).toBe(before + 1));
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }));
    await waitFor(() => expect(rolloutCalls().length).toBe(before + 2));
  });

  it('reads again straight away when the parent bumps refreshSignal', async () => {
    serveRollouts(names(1));
    const view = show({ refreshSignal: 0 });
    await screen.findByText('Rollout 1');
    const before = rolloutCalls().length;
    view.rerender(<UserContext.Provider value={{ hasPermission: () => false } as never}><RolloutsTab tenantId={null} refreshSignal={1} /></UserContext.Provider>);
    await waitFor(() => expect(rolloutCalls().length).toBe(before + 1));
  });

  it('sends the viewed organization', async () => {
    serveRollouts(names(1));
    show({ tenantId: 'tenant_b' });
    await screen.findByText('Rollout 1');
    expect(String(rolloutCalls()[0][0])).toBe('/api/patch-rollouts?offset=0&limit=10&tenantId=tenant_b');
  });

  // ---- empty states

  it('no rollouts and no rings: No rollouts yet with the set-up-your-rings body and a Start rollout CTA', async () => {
    serveRollouts([], { ringsSet: false });
    show({ onStartRequested: vi.fn() });
    expect(await screen.findByRole('heading', { name: 'No rollouts yet' })).toBeInTheDocument();
    expect(screen.getByText('Set up your rings, then start a rollout from the patches your computers are waiting for.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Start rollout' }).length).toBeGreaterThanOrEqual(2);
  });

  it('no rollouts, rings set: the pick-your-patches body', async () => {
    serveRollouts([], { ringsSet: true });
    show({ onStartRequested: vi.fn() });
    expect(await screen.findByText('Pick the patches your computers are waiting for and roll them out ring by ring.')).toBeInTheDocument();
  });

  it('no rollouts without canStart: no Start button anywhere, and the ask-someone line', async () => {
    serveRollouts([], { flags: flags({ canStart: false }) });
    show({ onStartRequested: vi.fn() });
    expect(await screen.findByRole('heading', { name: 'No rollouts yet' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start rollout' })).toBeNull();
    expect(screen.getByText('Ask someone with patching access to start a rollout.')).toBeInTheDocument();
  });

  it('the platform organization shows its own empty state and no buttons', async () => {
    serveRollouts([], { flags: flags({ platformTenant: true, canStart: false }) });
    show({ onStartRequested: vi.fn() });
    expect(await screen.findByRole('heading', { level: 2, name: "Rollouts aren't available for the platform organization" })).toBeInTheDocument();
    expect(screen.getByText("Patches are never rolled out to the platform's own server. Open a customer organization to start a rollout.")).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  // ---- header and Start

  it('Start rollout is rendered with canStart, tells the handler when given, and opens the Start dialog', async () => {
    serveRollouts(names(1));
    const onStartRequested = vi.fn();
    const view = show({ onStartRequested });
    fireEvent.click(await screen.findByRole('button', { name: 'Start rollout' }));
    expect(onStartRequested).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('dialog', { name: 'Start a rollout' })).toBeInTheDocument();
    view.unmount();
    show();
    expect(await screen.findByRole('button', { name: 'Start rollout' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('without canStart there is no button and the muted line says who to ask', async () => {
    serveRollouts(names(1), { flags: flags({ canStart: false }) });
    show({ onStartRequested: vi.fn() });
    await screen.findByText('Rollout 1');
    expect(screen.queryByRole('button', { name: 'Start rollout' })).toBeNull();
    expect(screen.getByText('Ask someone with patching access to start a rollout.')).toBeInTheDocument();
  });

  // ---- window strip (PTCH-05)

  it('window open: the green chip, the closing sentence, and the time zone in mono', async () => {
    serveRollouts(names(1));
    show();
    expect(await screen.findByText('Window open')).toBeInTheDocument();
    expect(screen.getByText('Closes at 04:00 (Asia/Kolkata).')).toBeInTheDocument();
    const zone = screen.getByText('Asia/Kolkata');
    expect(zone.className).toContain('font-mono');
    expect(zone.closest('div')?.textContent).toContain('Time zone:');
  });

  it('window closed: the outline chip and the next opening sentence', async () => {
    serveRollouts(names(1), { window: openWindow({ state: 'closed', text: 'Next window opens Sat 7 Nov, 03:00 (Asia/Kolkata).', closesAt: null, nextOpensAt: at0() }) });
    show();
    expect(await screen.findByText('Window closed')).toBeInTheDocument();
    expect(screen.getByText('Next window opens Sat 7 Nov, 03:00 (Asia/Kolkata).')).toBeInTheDocument();
  });

  it('no window: the amber block, Start disabled with the same words, and the link only for someone who can open Settings', async () => {
    serveRollouts(names(1), { window: openWindow({ state: 'none', text: '', closesAt: null, nextOpensAt: null, timeZone: null }) });
    const onOpenView = vi.fn();
    show({ onStartRequested: vi.fn(), onOpenView });
    const found = await screen.findAllByText('Add a maintenance window first.');
    const block = found.map(f => f.closest('[role="status"]')).find(Boolean) as HTMLElement;
    expect(block).toBeTruthy();
    expect(within(block).queryByRole('button', { name: 'Open maintenance windows' })).toBeNull();
    expect(within(block).getByText('Open maintenance windows')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Start rollout' });
    expect(start).toBeDisabled();
    expect(document.getElementById(start.getAttribute('aria-describedby') ?? '')?.textContent).toBe('Add a maintenance window first.');
    expect(screen.getByText('No time zone set. Windows use UTC.')).toBeInTheDocument();
  });

  it('the Open maintenance windows link opens Settings for a person who can manage settings', async () => {
    serveRollouts(names(1), { window: openWindow({ state: 'none', text: '', closesAt: null, nextOpensAt: null, timeZone: null }) });
    const onOpenView = vi.fn();
    show({ onOpenView }, { hasPermission: (p: string) => p === 'manage:settings' });
    fireEvent.click(await screen.findByRole('button', { name: 'Open maintenance windows' }));
    expect(onOpenView).toHaveBeenCalledWith('settings');
  });

  it('a long time zone name wraps instead of being cut off, and the strip wraps', async () => {
    serveRollouts(names(1), { window: openWindow({ timeZone: 'America/Argentina/ComodRivadavia' }) });
    show();
    const zone = await screen.findByText('America/Argentina/ComodRivadavia');
    expect(zone.className).toContain('break-all');
    expect(zone.closest('.card')?.className).toContain('flex-wrap');
  });

  // ---- stop and shadow

  it('a stop shows the amber paused block above the list and disables Start with the reason line', async () => {
    serveRollouts(names(1), { flags: flags({ stopped: true, stopScope: 'tenant' }) });
    show({ onStartRequested: vi.fn() });
    expect(await screen.findByText(STOP_TENANT)).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Start rollout' });
    expect(start).toBeDisabled();
    expect(document.getElementById(start.getAttribute('aria-describedby') ?? '')?.textContent).toBe('Paused while automatic actions are stopped.');
  });

  it('a platform-wide stop says so', async () => {
    serveRollouts(names(1), { flags: flags({ stopped: true, stopScope: 'platform' }) });
    show();
    expect(await screen.findByText(STOP_PLATFORM)).toBeInTheDocument();
    expect(screen.queryByText(STOP_TENANT)).toBeNull();
  });

  it('shadow mode shows the blue simulation block', async () => {
    serveRollouts(names(1), { flags: flags({ shadow: true }) });
    show();
    const block = (await screen.findByText(SHADOW)).closest('[role="status"]');
    expect(block).not.toBeNull();
  });

  it('no stop and no shadow: neither block is shown', async () => {
    serveRollouts(names(1));
    show({ onStartRequested: vi.fn() });
    await screen.findByText('Rollout 1');
    expect(screen.queryByText(STOP_TENANT)).toBeNull();
    expect(screen.queryByText(SHADOW)).toBeNull();
    expect(screen.getByRole('button', { name: 'Start rollout' })).toBeEnabled();
  });

  // ---- paging

  it('shows 10 cards then Show more rollouts, which appends the rest with Loading... while pending', async () => {
    serveRollouts(names(12));
    show();
    await screen.findByText('Rollout 10');
    expect(screen.getAllByRole('article')).toHaveLength(10);
    expect(screen.queryByText('Rollout 11')).toBeNull();
    let release: (r: Response) => void = () => {};
    const rest = new Promise<Response>(r => { release = r; });
    mockFetch.mockImplementationOnce(() => rest);
    fireEvent.click(screen.getByRole('button', { name: 'Show more rollouts' }));
    expect(await screen.findByRole('button', { name: 'Loading...' })).toBeDisabled();
    release(jsonRes(rolloutPage(names(12).slice(10), { total: 12, offset: 10 })));
    expect(await screen.findByText('Rollout 12')).toBeInTheDocument();
    expect(screen.getAllByRole('article')).toHaveLength(12);
    expect(screen.queryByRole('button', { name: /Show more rollouts/ })).toBeNull();
    expect(String(rolloutCalls()[1][0])).toBe('/api/patch-rollouts?offset=10&limit=10');
  });

  // ---- live region and badge

  const live = (container: HTMLElement) => container.querySelector('[data-live="rollouts"]') as HTMLElement;

  it('the live region is silent on first load and announces only when the count rises after a poll', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serveRollouts(names(2), { attentionCount: 1 });
    const { container } = show();
    await screen.findByText('Rollout 1');
    expect(live(container)).toHaveAttribute('role', 'status');
    expect(live(container).textContent).toBe('');
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(live(container).textContent).toBe('');
    served.over = { attentionCount: 3 };
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(live(container).textContent).toBe('3 rollouts need your attention');
  });

  it('reports the attention count to the parent after each read', async () => {
    serveRollouts(names(1), { attentionCount: 4 });
    const onAttentionCount = vi.fn();
    show({ onAttentionCount });
    await waitFor(() => expect(onAttentionCount).toHaveBeenCalledWith(4));
  });

  // ---- extension points

  it('renders the rings card and the start dialog the parent supplies', async () => {
    serveRollouts(names(1));
    show({ renderRingsCard: () => <div>RINGS CARD</div>, renderStartDialog: () => <div>START DIALOG</div> });
    expect(await screen.findByText('RINGS CARD')).toBeInTheDocument();
    expect(screen.getByText('START DIALOG')).toBeInTheDocument();
  });

  it('passes the ring detail and the actions through to each card', async () => {
    const halt = { ringName: 'Early', reason: 'a computer failed its health check.', reverts: [] };
    serveRollouts([card({ id: 'a', name: 'Alpha', status: 'halted', halt })]);
    show({
      renderRingDetail: (ring) => <div>DETAIL OF {ring.name}</div>,
      renderActions: (c) => <button type="button">Act on {c.name}</button>,
    });
    expect(await screen.findByRole('button', { name: 'Act on Alpha' })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Show details/ })[1]);
    expect(screen.getByText('DETAIL OF Early')).toBeInTheDocument();
  });
});

function at0() { return new Date(Date.now() + 3600_000).toISOString(); }
