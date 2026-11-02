/**
 * Phase 83 / ACTV-02 (83-19): the Needs your decision section. authFetch is mocked and the payloads follow the
 * 83-18 card contract (83-18-SUMMARY.md). Every control comes from the server's flags.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { formatExpires, formatReverts } from '../../components/AutonomousOpsIncidentCard';
import {
  MIN, HOUR, at, clock, line, card, page, isolated, jsonRes, statusPayload, routeFetch, callsTo, incidentCalls, decisionCalls, view, shown, flush, mockAuthFetch, toast,
} from './_autonomousOpsDecisionsHarness';
import type { Handler } from './_autonomousOpsDecisionsHarness';

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
    // Both clicks land before React re-renders the disabled button: only the ref guard keeps it to one request.
    await act(async () => { approve.click(); approve.click(); });
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

