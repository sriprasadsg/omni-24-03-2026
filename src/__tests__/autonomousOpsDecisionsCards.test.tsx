/**
 * Phase 83 / ACTV-02 (83-19), Task 2: Confirm isolation, the countdown, the kill cards, the times the browser fills
 * and the placement of the section on the Autonomous Ops screen. Fixtures are in _autonomousOpsDecisionsHarness.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import {
  MIN, HOUR, at, clock, line, card, page, isolated, jsonRes, statusPayload, routeFetch, callsTo, incidentCalls, decisionCalls, view, shown, flush, mockAuthFetch, toast,
} from './_autonomousOpsDecisionsHarness';
import type { Handler } from './_autonomousOpsDecisionsHarness';

beforeEach(() => { mockAuthFetch.mockReset(); toast.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

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
      `Confirming keeps this computer isolated until you restore it. Without it, the computer returns to the network automatically at ${clock(String(iso.revertsAt))}.`,
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
    await act(async () => { button.click(); button.click(); });
    await flush();
    expect(decisionCalls()).toHaveLength(1);
    expect(decisionCalls()[0][0]).toBe('/api/autonomous-ops/actions/AO-ISO/confirm-isolation');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: 'Confirming...' })).toBeDisabled();
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

describe('times the browser fills', () => {
  it('a block line that already ran gets its end time from blockedUntil, never a raw token', async () => {
    const until = at(3 * HOUR);
    const ran = line({
      id: 'AO-B', state: 'verified', bucket: 'done', command: 'block_ip', label: 'Block IP address', target: '203.0.113.7',
      needsPerson: false, expiresAt: null, canApprove: false, canDeny: false, consequenceText: null, blockedUntil: until,
      result: 'Blocked for 24 hours, until {until}. Verified: the firewall rule is in place.',
    });
    routeFetch({ incidents: () => jsonRes(page([card({ actions: [line(), ran] })])) });
    const { container } = await shown();
    const text = (container.querySelector('[data-action-id="AO-B"]') as HTMLElement).textContent as string;
    expect(text).not.toContain('{until}');
    expect(text).toMatch(/Blocked for 24 hours, until [A-Z][a-z]{2} \d{1,2}, \d\d:\d\d\. Verified/);
  });
});

// ── placement on the Autonomous Ops screen ──────────────────────────────────

describe('placement on the Autonomous Ops screen', () => {
  const pendingRow = {
    id: 'r-wait', bucket: 'pending', state: 'awaiting_approval', createdAt: at(-5 * MIN), actionLabel: 'Kill process',
    classLine: 'Needs approval', reasonText: 'A second source agreed.', ruleId: 'sweep:kill_process', host: 'web-01',
    target: 'powershell.exe (PID 4120)', resultText: 'Waiting for approval.', controlEvent: null, incidentId: 'INC-1',
  };

  /** Every request the screen makes gets an answer; the ones this test does not care about are empty. */
  function routeScreen(incidents: Handler, status: Handler = () => jsonRes(statusPayload())) {
    mockAuthFetch.mockImplementation(async (url: string) => {
      const path = url.split('?')[0];
      if (path === '/api/autonomous-ops/status') return status(url);
      if (path === '/api/autonomous-ops/incidents') return incidents(url);
      if (path === '/api/autonomous-ops/actions') return jsonRes({ items: [pendingRow], nextCursor: null });
      if (path === '/api/autonomous-ops/response-settings') {
        return jsonRes({ twoSignal: true, blockHours: 24, watchedServices: [], readable: true, restartAvailable: true });
      }
      return jsonRes({}, 404);
    });
  }

  function screenFor(role: string, tenantId: string | null = null) {
    return (
      <UserContext.Provider value={{
        currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions: [] } as any,
        login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
        hasPermission: () => true, enabledFeatures: [], serverLockedFeatures: {},
      }}>
        <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
          <AutonomousOpsActivity tenantId={tenantId} />
        </AutonomousOpsStatusProvider>
      </UserContext.Provider>
    );
  }

  it('sits directly under the status card, above Response settings and Activity, and the Review link focuses its card', async () => {
    routeScreen(() => jsonRes(page([card()])));
    const { container } = render(screenFor('Tenant Admin'));
    const article = await screen.findByRole('article', { name: 'web-01' });
    const status = container.querySelector('[data-slot="autonomous-ops-status"]') as HTMLElement;
    const decisions = container.querySelector('#decisions') as HTMLElement;
    const activity = container.querySelector('#autonomous-ops-activity-title') as HTMLElement;
    expect(status.nextElementSibling).toBe(decisions);
    expect(decisions.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click((await screen.findAllByRole('button', { name: 'Review in Needs your decision' }))[0]);
    expect(document.activeElement).toBe(article);
  });

  it('a decision made on a card reloads the Activity list', async () => {
    routeScreen(() => jsonRes(page([card()])));
    render(screenFor('Tenant Admin'));
    await screen.findByRole('article', { name: 'web-01' });
    await waitFor(() => expect(callsTo(/\/autonomous-ops\/actions$/).length).toBeGreaterThan(0));
    const before = callsTo(/\/autonomous-ops\/actions$/).length;
    mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      const path = url.split('?')[0];
      if (/\/(approve|deny)$/.test(path)) return jsonRes({ status: 'denied', action: { id: 'AO-1', bucket: 'refused', state: 'denied' } });
      if (path === '/api/autonomous-ops/incidents') return jsonRes(page([]));
      if (path === '/api/autonomous-ops/actions') return jsonRes({ items: [], nextCursor: null });
      if (path === '/api/autonomous-ops/status') return jsonRes(statusPayload());
      return jsonRes({}, 404);
    });
    fireEvent.click(screen.getByRole('button', { name: /^Deny:/ }));
    await waitFor(() => expect(callsTo(/\/autonomous-ops\/actions$/).length).toBeGreaterThan(before));
  });

  it('does not render, and does not ask, for the platform organization or in platform scope', async () => {
    routeScreen(() => jsonRes(page([card()])), () => jsonRes(statusPayload({ platformTenant: true })));
    const first = render(screenFor('Tenant Admin'));
    await screen.findByRole('heading', { level: 1, name: 'Autonomous Ops' });
    await waitFor(() => expect(mockAuthFetch.mock.calls.some(c => String(c[0]).startsWith('/api/autonomous-ops/status'))).toBe(true));
    await flush();
    expect(first.container.querySelector('#decisions')).toBeNull();
    expect(incidentCalls()).toHaveLength(0);
    first.unmount();

    mockAuthFetch.mockReset();
    routeScreen(() => jsonRes(page([card()])));
    const second = render(screenFor('Super Admin'));
    await screen.findByRole('heading', { level: 1, name: 'Autonomous Ops' });
    await flush();
    expect(second.container.querySelector('#decisions')).toBeNull();
    expect(incidentCalls()).toHaveLength(0);
  });

  it('platform staff inside an organization read that organization\'s cards', async () => {
    routeScreen(() => jsonRes(page([card()])));
    render(screenFor('Super Admin', 'tenant-b'));
    await screen.findByRole('article', { name: 'web-01' });
    expect(incidentCalls()[0][0]).toBe('/api/autonomous-ops/incidents?offset=0&limit=10&tenantId=tenant-b');
  });
});

