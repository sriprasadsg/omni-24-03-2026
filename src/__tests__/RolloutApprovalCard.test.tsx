/**
 * Phase 84 / PTCH-06 (84-15): the rollout approval card of Needs your decision and its merge into the section.
 * authFetch is mocked; the payloads follow the 84-10 card contract (services/patchRollouts/types.ts, ApprovalCard).
 *
 * Value: protects=each line of a waiting ring can be approved or denied on its own with its consequences printed
 * first, and rollout cards sit in the one list beside incident cards; fails_when=a card shows an approve-all, an
 * Approve without its target in the label, a stop that does not disable Approve, a failed decision that loses the
 * line, or a rollout fetch that disturbs the incident list; no_claim=the server wording of the lines
 * (backend/tests/test_patch_rollout_cards.py) and the incident cards (autonomousOpsDecisions tests).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { RolloutApprovalCard } from '../../components/patchRollouts/RolloutApprovalCard';
import type { ApprovalCard, ApprovalLine } from '../../services/patchRollouts/types';
import { mockAuthFetch, toast, jsonRes, at, HOUR, MIN, flush } from './_autonomousOpsDecisionsHarness';

// ── fixtures ────────────────────────────────────────────────────────────────

const names = (n: number) => Array.from({ length: n }, (_, i) => `host-${String(i + 1).padStart(2, '0')}`);

export const installLine = (over: Partial<ApprovalLine> = {}): ApprovalLine => ({
  line: 'install', state: 'pending', label: 'Install 4 patches on 12 computers',
  targetText: 'KB5034441, KB5034123, KB5033375 +1 more',
  why: 'Early passed its health check at Thu 5 Nov, 14:02. Pilot is next.',
  whatHappens: 'Installs these patches inside your maintenance window (open now, closes 04:00). The ring halts if more than 10% of its computers fail or a check has no data.',
  computers: names(10), computerTotal: 12, canApprove: true, canDeny: true, resultText: null,
  expiresAt: at(19 * HOUR + 30_000), ...over,
});

export const rebootLine = (over: Partial<ApprovalLine> = {}): ApprovalLine => ({
  line: 'reboot', state: 'pending', label: 'Restart 3 computers', targetText: '',
  why: 'A restart is needed on host-01, host-02 and host-03 to finish installing.',
  whatHappens: 'Restarts these computers with a 5-minute warning ("Restarting in 5 minutes for updates"). Anyone using them loses unsaved work. Runs now if your window is open, otherwise when it next opens at 22:00.',
  computers: names(3), computerTotal: 3, canApprove: true, canDeny: true, resultText: null,
  expiresAt: at(20 * HOUR), ...over,
});

export const rolloutCard = (over: Partial<ApprovalCard> = {}): ApprovalCard => ({
  kind: 'rollout', rolloutId: 'R1', ring: '1', anchorId: 'approval-rollout-R1-1', name: 'November security',
  subtitle: 'Ring 2 of 4: Pilot · 12 computers', expiresAt: at(19 * HOUR + 30_000), lines: [installLine()], ...over,
});

const noop = () => {};
function show(card: ApprovalCard, props: Partial<React.ComponentProps<typeof RolloutApprovalCard>> = {}) {
  return render(<RolloutApprovalCard card={card} stopped={false} shadow={false} onDecided={noop} {...props} />);
}

const result = (over: Record<string, unknown> = {}) => ({
  status: 'approved', when: 'now', windowOpensAt: null, approved: 12, refused: [],
  message: 'Approved. Installing now.', ...over,
});

beforeEach(() => { mockAuthFetch.mockReset(); toast.mockReset(); });

// ── the card ────────────────────────────────────────────────────────────────

describe('RolloutApprovalCard: header', () => {
  it('is an article named by the rollout with the ring subtitle, the anchor id and the nearest expiry', () => {
    show(rolloutCard());
    const article = screen.getByRole('article', { name: 'November security' });
    expect(article.id).toBe('approval-rollout-R1-1');
    expect(article.getAttribute('tabindex')).toBe('-1');
    expect(screen.getByText('Ring 2 of 4: Pilot · 12 computers')).toBeTruthy();
    expect(screen.getByText('Expires in 19 h')).toBeTruthy();
  });

  it('takes the nearest expiry of the lines still waiting', () => {
    show(rolloutCard({ lines: [installLine({ expiresAt: at(5 * HOUR + 30_000) }), rebootLine({ expiresAt: at(2 * HOUR + 30_000) })] }));
    expect(screen.getByText('Expires in 2 h')).toBeTruthy();
  });

  it('wraps a long rollout name and keeps patch ids mono with break-all', () => {
    show(rolloutCard({ name: 'N'.repeat(120) }));
    expect(screen.getByRole('heading', { name: 'N'.repeat(120) }).className).toContain('break-words');
    const target = screen.getByText('KB5034441, KB5034123, KB5033375 +1 more');
    expect(target.className).toContain('font-mono');
    expect(target.className).toContain('break-all');
  });

  it('renders rollout text as text, never markup', () => {
    show(rolloutCard({ name: '<img src=x onerror=alert(1)>' }));
    expect(screen.getByRole('heading').textContent).toBe('<img src=x onerror=alert(1)>');
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('RolloutApprovalCard: lines', () => {
  it('shows the Install line with its target, why and what happens before any click', () => {
    show(rolloutCard());
    expect(screen.getByText('Install 4 patches on 12 computers')).toBeTruthy();
    expect(screen.getByText('Early passed its health check at Thu 5 Nov, 14:02. Pilot is next.')).toBeTruthy();
    expect(screen.getByText(/^Installs these patches inside your maintenance window \(open now, closes 04:00\)\./)).toBeTruthy();
  });

  it('shows the Restart line with the 5-minute warning text and the window timing', () => {
    show(rolloutCard({ lines: [installLine(), rebootLine()] }));
    const text = screen.getByText(/^Restarts these computers with a 5-minute warning/).textContent as string;
    expect(text).toContain('("Restarting in 5 minutes for updates")');
    expect(text).toContain('Anyone using them loses unsaved work.');
    expect(text).toContain('otherwise when it next opens at 22:00.');
    expect(screen.getByText('Restart 3 computers')).toBeTruthy();
  });

  it('shows the Revert restart line when the server sends it', () => {
    show(rolloutCard({ lines: [{ ...rebootLine(), line: 'revert_reboot', label: 'Restart 3 computers to finish the revert' }] }));
    expect(screen.getByText('Restart 3 computers to finish the revert')).toBeTruthy();
  });

  it('renders exactly one Approve and one Deny per pending line and no approve-all', () => {
    show(rolloutCard({ lines: [installLine(), rebootLine()] }));
    expect(screen.getAllByRole('button', { name: /^Approve/ })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /^Deny/ })).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /\ball\b/i })).toBeNull();
  });

  it('names the target and the rollout in every Approve and Deny label', () => {
    show(rolloutCard({ lines: [installLine(), rebootLine()] }));
    expect(screen.getByRole('button', { name: 'Approve: Install 4 patches on 12 computers in Pilot, November security' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Deny: Install 4 patches on 12 computers in Pilot, November security' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Approve: Restart 3 computers in Pilot, November security' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Deny: Restart 3 computers in Pilot, November security' })).toBeTruthy();
  });

  it('opens Show computers with aria-expanded, lists ten names and says how many are shown', () => {
    show(rolloutCard());
    const toggle = screen.getByRole('button', { name: 'Show computers' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('host-01')).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const list = document.getElementById(toggle.getAttribute('aria-controls') as string) as HTMLElement;
    expect(within(list).getAllByRole('listitem')).toHaveLength(10);
    expect(within(list).getByText('Showing 10 of 12.')).toBeTruthy();
    expect(within(list).getByText('host-01').className).toContain('font-mono');
  });

  it('says nothing about a total when every computer is listed', () => {
    show(rolloutCard({ lines: [rebootLine()] }));
    fireEvent.click(screen.getByRole('button', { name: 'Show computers' }));
    expect(screen.queryByText(/^Showing /)).toBeNull();
  });
});

// ── deciding ────────────────────────────────────────────────────────────────

describe('RolloutApprovalCard: approving and denying', () => {
  it('approves one line through its line route, shows the pending label on that line only and the server result after', async () => {
    let release!: (r: Response) => void;
    mockAuthFetch.mockImplementation(() => new Promise<Response>(r => { release = r; }));
    const onDecided = vi.fn();
    show(rolloutCard({ lines: [installLine(), rebootLine()] }), { onDecided });
    const install = screen.getByRole('button', { name: /^Approve: Install/ });
    fireEvent.click(install);
    await waitFor(() => expect(screen.getByRole('button', { name: /^Approve: Install/ }).textContent).toBe('Approving...'));
    expect((screen.getByRole('button', { name: /^Approve: Install/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^Deny: Install/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^Approve: Restart/ }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: /^Deny: Restart/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(mockAuthFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockAuthFetch.mock.calls[0];
    expect(url).toBe('/api/autonomous-ops/rollout-lines/R1/1/install/approve');
    expect((init as RequestInit).method).toBe('POST');
    await act(async () => { release(jsonRes(result())); });
    await flush();
    expect(screen.getByText('Approved. Installing now.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Approve: Install/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Approve: Restart/ })).toBeTruthy();
    expect(onDecided).toHaveBeenCalledTimes(1);
  });

  it('sends a tenant id only when platform staff entered an organization', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes(result()));
    show(rolloutCard(), { tenantId: 'tenant b' });
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Install/ }));
    await flush();
    expect(mockAuthFetch.mock.calls[0][0]).toBe('/api/autonomous-ops/rollout-lines/R1/1/install/approve?tenantId=tenant%20b');
  });

  it('toasts the install approval with the patch and computer counts and when it runs', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes(result()));
    show(rolloutCard());
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Install/ }));
    await flush();
    expect(toast).toHaveBeenCalledWith('Approved. 4 patches will install on 12 computers now.', 'success');
  });

  it('toasts the time the window opens when the install waits for it', async () => {
    const opens = new Date(Date.now() + 3 * HOUR).toISOString();
    const hhmm = new Date(opens).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    mockAuthFetch.mockResolvedValue(jsonRes(result({ when: 'window', windowOpensAt: opens })));
    show(rolloutCard());
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Install/ }));
    await flush();
    expect(toast).toHaveBeenCalledWith(`Approved. 4 patches will install on 12 computers when your window opens at ${hhmm}.`, 'success');
  });

  it('toasts the restart approval with the 5-minute warning and uses singular forms', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes(result({ message: 'Approved. Restarting now.' })));
    show(rolloutCard({ lines: [rebootLine()] }));
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Restart/ }));
    await flush();
    expect(toast).toHaveBeenCalledWith('Approved. 3 computers restart now with a 5-minute warning.', 'success');
    mockAuthFetch.mockResolvedValue(jsonRes(result({ message: 'Approved. Restarting now.' })));
    toast.mockReset();
    show(rolloutCard({ rolloutId: 'R2', lines: [rebootLine({ label: 'Restart 1 computer', computerTotal: 1, computers: ['host-01'] })] }));
    fireEvent.click(screen.getAllByRole('button', { name: /^Approve: Restart 1 computer/ })[0]);
    await flush();
    expect(toast).toHaveBeenCalledWith('Approved. 1 computer restarts now with a 5-minute warning.', 'success');
  });

  it('denies one line through its line route and says nothing was sent', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes(result({
      status: 'denied', approved: 0, message: 'Denied by Pat. The rollout halts at Pilot.',
    })));
    const onDecided = vi.fn();
    show(rolloutCard({ lines: [installLine(), rebootLine()] }), { onDecided });
    fireEvent.click(screen.getByRole('button', { name: /^Deny: Restart/ }));
    await flush();
    expect(mockAuthFetch.mock.calls[0][0]).toBe('/api/autonomous-ops/rollout-lines/R1/1/reboot/deny');
    expect(screen.getByText('Denied by Pat. The rollout halts at Pilot.')).toBeTruthy();
    expect(toast).toHaveBeenCalledWith('Denied. Nothing was sent to 3 computers.', 'success');
    expect(onDecided).toHaveBeenCalledTimes(1);
  });

  it('keeps the line, shows the 83 copy in an alert and re-enables the buttons when the call fails', async () => {
    mockAuthFetch.mockRejectedValue(new Error('network'));
    const onDecided = vi.fn();
    show(rolloutCard(), { onDecided });
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Install/ }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("Couldn't approve this action. Check your connection and try again.");
    expect((screen.getByRole('button', { name: /^Approve: Install/ }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: /^Deny: Install/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(onDecided).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
  });

  it('shows the server sentence on a 409 and asks the section to read again', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes({ status: 'already_handled', detail: 'This step was already decided.' }, 409));
    const onStale = vi.fn();
    const onDecided = vi.fn();
    show(rolloutCard(), { onStale, onDecided });
    fireEvent.click(screen.getByRole('button', { name: /^Deny: Install/ }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("Couldn't deny this action: This step was already decided.");
    expect(onStale).toHaveBeenCalledTimes(1);
    expect(onDecided).not.toHaveBeenCalled();
    expect((screen.getByRole('button', { name: /^Deny: Install/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('sends one request for a double click', async () => {
    let release!: (r: Response) => void;
    mockAuthFetch.mockImplementation(() => new Promise<Response>(r => { release = r; }));
    show(rolloutCard());
    const button = screen.getByRole('button', { name: /^Approve: Install/ });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(mockAuthFetch).toHaveBeenCalledTimes(1);
    await act(async () => { release(jsonRes(result())); });
  });
});

// ── states ──────────────────────────────────────────────────────────────────

describe('RolloutApprovalCard: stop, shadow, access and settled lines', () => {
  it('disables Approve but not Deny during a stop and says why', () => {
    // The server reports canApprove false during a stop; the person who can deny still sees Approve, disabled.
    show(rolloutCard({ lines: [installLine({ canApprove: false, canDeny: true })] }), { stopped: true });
    expect((screen.getByRole('button', { name: /^Approve: Install/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^Deny: Install/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText('Paused while automatic actions are stopped.')).toBeTruthy();
  });

  it('renders no buttons in shadow mode', () => {
    show(rolloutCard(), { shadow: true });
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Deny/ })).toBeNull();
  });

  it('says who can decide when the viewer has no approval access', () => {
    show(rolloutCard({ lines: [installLine({ canApprove: false, canDeny: false })] }));
    expect(screen.getByText('Waiting for someone with approval access.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Deny/ })).toBeNull();
  });

  it('shows a denied line and an expired line with the server result and no buttons', () => {
    show(rolloutCard({ lines: [
      installLine({ state: 'denied', canApprove: false, canDeny: false, expiresAt: null, resultText: 'Denied by Asha. The rollout halts at Pilot.' }),
      rebootLine({ state: 'expired', canApprove: false, canDeny: false, expiresAt: null, resultText: 'Expired after 24 hours, counted as denied. The rollout halts at Pilot.' }),
    ] }));
    expect(screen.getByText('Denied by Asha. The rollout halts at Pilot.')).toBeTruthy();
    expect(screen.getByText('Expired after 24 hours, counted as denied. The rollout halts at Pilot.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(screen.queryByText(/^Installs these patches/)).toBeNull();
    expect(screen.queryByText(/^Expires in/)).toBeNull();
  });

  it('keeps Deny and disables Approve once a line deadline has passed on this clock', () => {
    show(rolloutCard({ lines: [installLine({ expiresAt: at(-MIN) })] }));
    expect((screen.getByRole('button', { name: /^Approve: Install/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^Deny: Install/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText('Expired after 24 hours, counted as denied. The rollout halts at Pilot.')).toBeTruthy();
  });

  it('lets the server text replace a local result once the line is no longer pending', async () => {
    mockAuthFetch.mockResolvedValue(jsonRes(result({ message: 'Approved. Installing now.' })));
    const view = show(rolloutCard());
    fireEvent.click(screen.getByRole('button', { name: /^Approve: Install/ }));
    await flush();
    expect(screen.getByText('Approved. Installing now.')).toBeTruthy();
    view.rerender(<RolloutApprovalCard
      card={rolloutCard({ lines: [installLine({ state: 'approved', canApprove: false, canDeny: false, expiresAt: null, resultText: 'Approved. Installing when your window opens at 22:00.' })] })}
      stopped={false} shadow={false} onDecided={noop}
    />);
    expect(screen.getByText('Approved. Installing when your window opens at 22:00.')).toBeTruthy();
    expect(screen.queryByText('Approved. Installing now.')).toBeNull();
  });
});
