/**
 * Phase 85 / DESK-01, DESK-02, DESK-04, DESK-05 (85-16): the Service desk settings card of 85-UI-SPEC section 2.
 * authFetch and the toast are mocked; the payloads follow 85-11-SUMMARY.md. Nothing here reaches a real API.
 * This file covers the summary, the status line, the readiness list and the card states (Task 1); the words, Save and the
 * two dialogs are in ServiceDeskSettingsWords.test.tsx (Task 2).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { DeskSettingsCard, formatTypical } from '../../components/serviceDesk/DeskSettingsCard';
import { DESK_SETTINGS_CHANGED } from '../../services/serviceDesk/settingsApi';
import {
  ALL_BLOCKERS, BREAKER, DESK_URL, gets, header, jsonRes, mockAuthFetch, openCard, routeDesk, setStored, view,
} from './_serviceDeskSettingsHarness';

beforeEach(() => { mockAuthFetch.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

const summary = async () => (await screen.findByText(/ · /)).textContent;

describe('Service desk card: collapsed summary', () => {
  it('reads mode, model, typical answer time and word count in one line and renders no form while collapsed', async () => {
    await openCard({ words: ['payroll', 'bonus'] }, {}, false);
    expect(await summary()).toBe('Drafts only · Local model online · Typical answer time 1 min 40 s · 2 extra words');
    expect(screen.getByRole('button', { name: 'Service desk' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('radiogroup')).toBeNull();
  });

  it.each([
    ['off', { mode: 'off', effectiveMode: 'off' }, /^Off · /],
    ['screens off', { mode: 'drafts', effectiveMode: 'off', screensOn: false }, /^Off \(screens not switched on\) · /],
    ['posting', { mode: 'post', effectiveMode: 'post', posting: { posting: true, blockers: [] } }, /^Post answers \(posting\) · /],
    ['drafts for now', { mode: 'post', effectiveMode: 'post', posting: { posting: false, blockers: [{ code: 'stop' }] } }, /^Post answers \(drafts for now\) · /],
    ['restore needed', { mode: 'drafts', breaker: BREAKER }, /^Drafts only \(restore needed\) · /],
    ['offline', { model: { state: 'offline', tag: 'llama3.2:3b' } }, / · Local model offline · /],
    ['not checked', { model: { state: 'not_checked', tag: null } }, / · Local model not checked · /],
    ['not measured', { timing: { medianSeconds: null, samples: 0, measured: false } }, / · Answer time not measured$/],
  ])('shows the %s variant', async (_name, over, pattern) => {
    await openCard(over as any, {}, false);
    expect(await summary()).toMatch(pattern as RegExp);
  });

  it('says 1 extra word, n extra words, and leaves the words part out with none', async () => {
    const one = await openCard({ words: ['payroll'] }, {}, false);
    expect(await summary()).toMatch(/ · 1 extra word$/);
    one.unmount();
    mockAuthFetch.mockReset();
    const none = await openCard({ words: [] }, {}, false);
    expect(await summary()).not.toMatch(/extra word/);
    none.unmount();
  });

  it('formats the typical answer time', () => {
    expect(formatTypical(100)).toBe('1 min 40 s');
    expect(formatTypical(120)).toBe('2 min');
    expect(formatTypical(40)).toBe('40 s');
  });
});

describe('Service desk card: loading and errors', () => {
  it('shows a skeleton under the title while collapsed and three busy skeletons once expanded', async () => {
    let release: (r: Response) => void = () => {};
    mockAuthFetch.mockImplementation(() => new Promise<Response>(resolve => { release = resolve; }));
    const { container } = render(<DeskSettingsCard tenantId={null} />);
    expect(container.querySelector('.h-4.w-64')).not.toBeNull();
    fireEvent.click(header());
    const body = container.querySelector('[aria-busy="true"]') as HTMLElement;
    expect(body.querySelectorAll('.h-16')).toHaveLength(3);
    await act(async () => { release(jsonRes(view())); });
    await screen.findByRole('radiogroup', { name: 'Answers to requesters' });
    expect(container.querySelector('[aria-busy="true"]')).toBeNull();
  });

  it('shows the red load error with Try again, and Try again reads the settings again', async () => {
    setStored(view());
    let fail = true;
    routeDesk({ get: () => (fail ? jsonRes({ detail: 'x' }, 500) : jsonRes(view())) });
    render(<DeskSettingsCard tenantId={null} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load service desk settings. Check your connection and try again.");
    fail = false;
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await summary()).toMatch(/^Drafts only/);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('treats an answer without the expected shape as a load failure', async () => {
    routeDesk({ get: () => jsonRes({ nope: true }) });
    render(<DeskSettingsCard tenantId={null} />);
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load service desk settings");
  });
});

describe('Service desk card: status line', () => {
  it('Online: the green chip, the running text, the model tag, the typical answer time and the queue limit', async () => {
    await openCard();
    const status = screen.getAllByRole('status')[0];
    expect(within(status).getByText('Online')).toBeInTheDocument();
    expect(within(status).getByText('The local model is running.')).toBeInTheDocument();
    expect(within(status).getByText('llama3.2:3b')).toHaveClass('font-mono');
    expect(within(status).getByText('Typical answer time: 1 min 40 s')).toBeInTheDocument();
    expect(within(status).getByText('Median of the last 12 answers.')).toBeInTheDocument();
    expect(within(status).getByText(/^An answer that isn't ready 10 minutes after the ticket arrives is dropped/)).toBeInTheDocument();
  });

  it('Offline: the red chip and both lines of explanation', async () => {
    await openCard({ model: { state: 'offline', tag: 'llama3.2:3b' } });
    const status = screen.getAllByRole('status')[0];
    expect(within(status).getByText('Offline')).toBeInTheDocument();
    expect(within(status).getByText("Offline: the local model isn't running")).toBeInTheDocument();
    expect(within(status).getByText(/^Every ticket goes to a person and is marked "service desk offline" until it is back\. Ticket text never leaves this server\.$/)).toBeInTheDocument();
  });

  it('Not checked: the outline chip', async () => {
    await openCard({ model: { state: 'not_checked', tag: null } });
    expect(within(screen.getAllByRole('status')[0]).getByText('Not checked')).toBeInTheDocument();
  });

  it('with no measurement says so and promises safe defaults', async () => {
    await openCard({ timing: { medianSeconds: null, samples: 0, measured: false } });
    expect(screen.getByText('Answer time not measured yet.')).toBeInTheDocument();
    expect(screen.getByText('Timeouts use safe defaults until an administrator measures this server.')).toBeInTheDocument();
    expect(screen.queryByText(/^Typical answer time:/)).toBeNull();
  });
});

describe('Service desk card: modes and readiness', () => {
  it('offers exactly Off, Drafts only and Post answers in a labelled radiogroup, with the saved one selected', async () => {
    await openCard({ mode: 'drafts' });
    const group = screen.getByRole('radiogroup', { name: 'Answers to requesters' });
    const radios = within(group).getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect(radios.map(r => (r as HTMLInputElement).checked)).toEqual([false, true, false]);
    expect(within(group).getByText('A qualifying answer is posted to the requester with the articles it cites. A person can withdraw it with Undo.')).toBeInTheDocument();
    expect(screen.getByText('Every organization starts at Drafts only. Only tickets a person raised get an answer, and only from your own articles marked Help desk.')).toBeInTheDocument();
  });

  it('hides the readiness list unless the saved mode is Post answers', async () => {
    await openCard({ mode: 'drafts' });
    expect(screen.queryByText('Will answers be posted?')).toBeNull();
  });

  it('with Post answers saved and every condition met shows five met rows and the Posting chip', async () => {
    await openCard({ mode: 'post', effectiveMode: 'post', posting: { posting: true, blockers: [] } });
    const list = screen.getByRole('status', { name: 'Will answers be posted?' });
    expect(within(list).getByText('Posting')).toBeInTheDocument();
    expect(within(list).getAllByRole('listitem').map(li => li.textContent)).toEqual([
      'Autonomous Ops is at Undoable-auto.', 'Shadow mode is lifted.', 'Automatic actions are running.',
      'Fewer than 20 answers posted in the last hour.', 'No answers were withdrawn recently.',
    ]);
  });

  it('shows each unmet condition with its own sentence and the Drafts for now chip, from the server list only', async () => {
    await openCard({ mode: 'post', effectiveMode: 'post', breaker: null, posting: { posting: false, blockers: ALL_BLOCKERS } });
    const list = screen.getByRole('status', { name: 'Will answers be posted?' });
    expect(within(list).getByText('Drafts for now')).toBeInTheDocument();
    const rows = within(list).getAllByRole('listitem').map(li => li.textContent);
    expect(rows).toEqual([
      'Autonomous Ops is at Suggest, so answers stay drafts. Only the level screen changes this.',
      'Shadow mode is on for this organization. The activity list shows what would have been posted; answers stay drafts. Only a platform administrator lifts it.',
      'Automatic actions are stopped, so nothing is posted. Undo still works.',
      '20 answers were posted in the last hour. New answers are drafts until the hour passes.',
      'The service desk dropped to Drafts only. Restore Post answers above.',
    ]);
  });

  it('with only the hourly limit unmet marks just that row', async () => {
    await openCard({ mode: 'post', effectiveMode: 'post', posting: { posting: false, blockers: [{ code: 'hourly_limit' }] } });
    const rows = within(screen.getByRole('status', { name: 'Will answers be posted?' })).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Autonomous Ops is at Undoable-auto.');
    expect(rows[3]).toHaveTextContent('20 answers were posted in the last hour.');
  });
});

describe('Service desk card: breaker, screens off and unreadable', () => {
  it('the tripped breaker shows the amber block, Restore Post answers for canRestore, and locks the Post answers option', async () => {
    await openCard({ mode: 'drafts', breaker: BREAKER, canRestore: true });
    expect(screen.getByText('The service desk dropped to Drafts only. 3 answers were withdrawn within 24 hours. Answers stay drafts until someone restores Post answers.')).toBeInTheDocument();
    expect(screen.getByText('A requester choosing "I still need help" never counts toward this.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Restore Post answers' })).toBeInTheDocument();
    const post = screen.getByRole('radio', { name: /^Post answers/ });
    expect(post).toBeDisabled();
    expect(post).toHaveAccessibleDescription('Restore Post answers first.');
  });

  it('without canRestore the block shows but there is no Restore button', async () => {
    await openCard({ mode: 'drafts', breaker: BREAKER, canRestore: false });
    expect(screen.getByText(/^The service desk dropped to Drafts only\. 3 answers/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Restore Post answers' })).toBeNull();
  });

  it('shows the blue block when Tickets or Knowledge Base is not switched on, and the controls stay editable', async () => {
    await openCard({ screensOn: false, effectiveMode: 'off' });
    expect(screen.getByText("The service desk is off because Tickets or Knowledge Base isn't switched on for this organization. Ask a platform administrator.")).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^Post answers/ })).toBeEnabled();
  });

  it('shows the blue block when the stored settings could not be read, and Save stays off until a change', async () => {
    await openCard({ readable: false });
    expect(screen.getByText("This organization's service desk settings couldn't be read, so answers are drafts until they load.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save service desk settings' })).toBeDisabled();
  });

  it('renders read-only when the server says the viewer cannot manage', async () => {
    await openCard({ canManage: false });
    expect(screen.getByRole('radio', { name: /^Off/ })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save service desk settings' })).toBeNull();
  });
});

describe('Service desk card: reading the settings', () => {
  it('reads on mount, reads again on expand, every 60 s while expanded, and not while collapsed', async () => {
    vi.useFakeTimers();
    setStored(view());
    routeDesk();
    render(<DeskSettingsCard tenantId={null} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(gets()).toHaveLength(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(gets()).toHaveLength(1); // collapsed: no polling
    fireEvent.click(header());
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(gets()).toHaveLength(2); // expanding reads again
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(gets()).toHaveLength(3);
    fireEvent.click(header());
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(gets()).toHaveLength(3); // collapsed again: the poll stopped
  });

  it('reads again when the window event arrives (an Undo that dropped the desk to Drafts only)', async () => {
    await openCard({ mode: 'post', effectiveMode: 'post', posting: { posting: true, blockers: [] } }, {}, false);
    expect(await summary()).toMatch(/^Post answers \(posting\)/);
    setStored(view({ mode: 'drafts', breaker: BREAKER }));
    act(() => { window.dispatchEvent(new Event(DESK_SETTINGS_CHANGED)); });
    await waitFor(() => expect(screen.getByText(/^Drafts only \(restore needed\)/)).toBeInTheDocument());
  });

  it('passes the organization platform staff entered as tenantId', async () => {
    setStored(view());
    routeDesk();
    render(<DeskSettingsCard tenantId="tenant-b" />);
    await summary();
    expect(String(gets()[0][0])).toBe(`${DESK_URL}?tenantId=tenant-b`);
  });
});

describe('Service desk card: who sees it on the Autonomous Ops screen', () => {
  function screenFor(role: string, perms: string[], opts: { tenantId?: string | null; platformTenant?: boolean } = {}) {
    const { tenantId = null, platformTenant = false } = opts;
    mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = url.split('?')[0];
      if (path === '/api/autonomous-ops/status') {
        return jsonRes({
          tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant, eligible: true, levelReadable: true,
          level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null, shadow: { effective: false, source: null },
          stop: { tenant: null, platform: null }, canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
        });
      }
      if (path === '/api/platform/autonomous-ops/status') {
        return jsonRes({ scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true });
      }
      if (path.endsWith('/autonomous-ops/actions')) return jsonRes({ items: [], nextCursor: null });
      if (path === '/api/autonomous-ops/response-settings') {
        return jsonRes({ twoSignal: true, blockHours: 24, watchedServices: [], readable: true, restartAvailable: true });
      }
      if (path === DESK_URL && !init?.method) return jsonRes(view());
      throw new Error(`unexpected request ${url}`);
    });
    return (
      <UserContext.Provider value={{
        currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: perms } as any,
        login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
        hasPermission: ((p: string) => perms.includes('*') || perms.includes(p)) as any, enabledFeatures: [], serverLockedFeatures: {},
      }}>
        <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
          <AutonomousOpsActivity tenantId={tenantId} />
        </AutonomousOpsStatusProvider>
      </UserContext.Provider>
    );
  }
  const deskGets = () => mockAuthFetch.mock.calls.filter(c => String(c[0]).split('?')[0] === DESK_URL);

  it('a Tenant Admin with manage sees it directly under Response settings and before Activity', async () => {
    render(screenFor('Tenant Admin', ['view:autonomous_ops', 'manage:autonomous_ops']));
    const response = await screen.findByRole('button', { name: 'Response settings' });
    const desk = await screen.findByRole('button', { name: 'Service desk' });
    const activity = screen.getByRole('heading', { name: 'Activity' });
    expect(response.compareDocumentPosition(desk) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(desk.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(await screen.findByText(/^Drafts only · Local model online/)).toBeInTheDocument();
  });

  it('a viewer without manage does not see it and makes no request', async () => {
    render(screenFor('Security Analyst', ['view:autonomous_ops', 'control:autonomous_ops']));
    await screen.findByRole('heading', { name: 'Activity' });
    expect(screen.queryByRole('button', { name: 'Service desk' })).toBeNull();
    expect(deskGets()).toHaveLength(0);
  });

  it('Platform Support never sees it', async () => {
    render(screenFor('Platform Support', ['view:autonomous_ops', 'manage:autonomous_ops'], { tenantId: 'tenant-a' }));
    await screen.findByRole('heading', { name: 'Activity' });
    expect(screen.queryByRole('button', { name: 'Service desk' })).toBeNull();
    expect(deskGets()).toHaveLength(0);
  });

  it('the platform organization never sees it', async () => {
    render(screenFor('Tenant Admin', ['view:autonomous_ops', 'manage:autonomous_ops'], { platformTenant: true }));
    await screen.findByRole('heading', { name: 'Activity' });
    expect(screen.queryByRole('button', { name: 'Service desk' })).toBeNull();
    expect(deskGets()).toHaveLength(0);
  });
});
