/**
 * Phase 84 / PTCH-01, D-16 (84-18): Resume and Cancel for a halted rollout. authFetch is mocked with the 84-16 answers
 * (POST /api/patch-rollouts/{id}/resume and /cancel; errors 403, 404, 409, 422 with a detail sentence).
 *
 * Value: protects=a halted rollout can only be resumed with a typed reason and a green check, or cancelled, each behind
 * its own confirmation that says what it does, and the person is told whether the check passed; fails_when=Resume is
 * enabled without a reason, a request in flight can be dismissed, a failure closes the dialog or is silent, a red check
 * reads as a resume, a 403 leaves the dialog open, a dialog button is labelled just Cancel, Keep rollout is not the
 * first focus, or server text is rendered as markup; no_claim=the routes themselves
 * (backend/tests/test_patch_rollout_lifecycle.py) and the look of the dialogs in both themes.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { cancelRollout, resumeRollout } from '../../services/patchRollouts/lifecycle';
import { CancelDialog, ResumeDialog } from '../../components/patchRollouts/RolloutDialogs';
import { RolloutCard } from '../../components/patchRollouts/RolloutCard';
import { RolloutsTab } from '../../components/patchRollouts/RolloutsTab';
import { UserContext } from '../../contexts/UserContext';
import type { RolloutCard as RolloutCardData } from '../../services/patchRollouts/types';
import { card, flags, jsonRes, rolloutPage } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
  toast.mockReset();
});

const bodyOf = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));

/** A reply the test settles by hand, so the in-flight state can be inspected. */
function deferred() {
  let settle!: (res: Response) => void;
  let fail!: (e: unknown) => void;
  const promise = new Promise<Response>((resolve, reject) => { settle = resolve; fail = reject; });
  return { promise, settle, fail };
}

describe('lifecycle calls', () => {
  it('resumeRollout posts the reason to /{id}/resume, with the viewed organization when given', async () => {
    mockFetch.mockResolvedValue(jsonRes({ status: 'resumed', reason: '', ring: 'Early' }));
    const result = await resumeRollout('R 1', 'Fixed the disk', 'tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R%201/resume?tenantId=tenant_x');
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('POST');
    expect(bodyOf(mockFetch.mock.calls[0])).toEqual({ reason: 'Fixed the disk' });
    expect(result).toEqual({ status: 'resumed', reason: '', ring: 'Early' });
  });

  it('cancelRollout posts to /{id}/cancel', async () => {
    mockFetch.mockResolvedValue(jsonRes({ status: 'cancelled', reason: '', ring: 'Early' }));
    const result = await cancelRollout('R1');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R1/cancel');
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('POST');
    expect(result.status).toBe('cancelled');
  });

  it('403, 409 and 422 carry the status and the server sentence', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Not allowed.' }, 403));
    await expect(resumeRollout('R1', 'x')).rejects.toMatchObject({ status: 403, detail: 'Not allowed.' });
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Wait for the revert to finish.' }, 409));
    await expect(resumeRollout('R1', 'x')).rejects.toMatchObject({ status: 409, detail: 'Wait for the revert to finish.' });
    mockFetch.mockResolvedValue(jsonRes({ detail: 'A reason is required, up to 500 characters.' }, 422));
    await expect(resumeRollout('R1', 'x')).rejects.toMatchObject({ status: 422, detail: 'A reason is required, up to 500 characters.' });
    mockFetch.mockResolvedValue(jsonRes({ detail: 'This rollout is not halted.' }, 409));
    await expect(cancelRollout('R1')).rejects.toMatchObject({ status: 409, detail: 'This rollout is not halted.' });
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    await expect(cancelRollout('R1')).rejects.toMatchObject({ status: 500, detail: '' });
  });
});

describe('ResumeDialog', () => {
  const setup = (over: Partial<React.ComponentProps<typeof ResumeDialog>> = {}) => {
    const onClose = vi.fn();
    const onDone = vi.fn();
    render(<ResumeDialog rolloutId="R1" ringName="Early" tenantId={null} onClose={onClose} onDone={onDone} {...over} />);
    return { onClose, onDone };
  };
  const type = (text: string) => fireEvent.change(screen.getByLabelText('Reason for resuming'), { target: { value: text } });
  const resumeButton = () => screen.getByRole('button', { name: /^(Resume rollout|Resuming\.\.\.)$/ });

  it('asks the question, says what Resuming does and that failed computers are not skipped', () => {
    setup();
    expect(screen.getByRole('dialog', { name: 'Resume this rollout?' })).toBeInTheDocument();
    expect(screen.getByText(
      'Resuming runs the health check for Early again. The rollout continues only if every check passes. Computers that failed are not skipped.',
    )).toBeInTheDocument();
    expect(screen.getByText('Recorded in the activity list and the audit log with your name.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep halted' })).toBeInTheDocument();
  });

  it('the reason field is required, holds at most 500 characters and counts them', () => {
    setup();
    const field = screen.getByLabelText('Reason for resuming') as HTMLTextAreaElement;
    expect(field).toHaveAttribute('aria-required', 'true');
    expect(field).toHaveAttribute('maxlength', '500');
    expect(field).toHaveAttribute('rows', '3');
    expect(screen.getByText('0/500')).toBeInTheDocument();
    type('Disk was full');
    expect(screen.getByText('13/500')).toBeInTheDocument();
  });

  it('Resume rollout stays disabled until the reason has a non-space character', () => {
    setup();
    expect(resumeButton()).toBeDisabled();
    type('   \n  ');
    expect(resumeButton()).toBeDisabled();
    type('Replaced the disk');
    expect(resumeButton()).toBeEnabled();
  });

  it('sends the typed reason and, when the check passed, says the rollout continues', async () => {
    const { onClose, onDone } = setup({ tenantId: 'tenant_x' });
    mockFetch.mockResolvedValue(jsonRes({ status: 'resumed', reason: '', ring: 'Early' }));
    type('  Replaced the disk  ');
    fireEvent.click(resumeButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R1/resume?tenantId=tenant_x');
    expect(bodyOf(mockFetch.mock.calls[0])).toEqual({ reason: 'Replaced the disk' });
    expect(toast).toHaveBeenCalledWith('Resuming. Early passed its check and the rollout continues.', 'success');
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('when the check still fails it closes with an info toast and reads the card again', async () => {
    const { onClose, onDone } = setup();
    mockFetch.mockResolvedValue(jsonRes({ status: 'still_halted', reason: 'a computer failed its health check.', ring: 'Early' }));
    type('Tried again');
    fireEvent.click(resumeButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith('The health check for Early still fails. The rollout stays halted.', 'info');
    expect(toast).not.toHaveBeenCalledWith(expect.stringContaining('passed its check'), expect.anything());
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('names the ring the server judged when it differs from the one on the card', async () => {
    const { onClose } = setup();
    mockFetch.mockResolvedValue(jsonRes({ status: 'resumed', reason: '', ring: 'Broad' }));
    type('Go');
    fireEvent.click(resumeButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith('Resuming. Broad passed its check and the rollout continues.', 'success');
  });

  it('shows Resuming... while the request is in flight, and neither Esc nor the backdrop nor Keep halted closes it', async () => {
    const reply = deferred();
    mockFetch.mockReturnValue(reply.promise);
    const { onClose, onDone } = setup();
    type('Go');
    fireEvent.click(resumeButton());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Resuming...' })).toBeDisabled());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(screen.getByRole('button', { name: 'Keep halted' })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => { reply.settle(jsonRes({ status: 'resumed', reason: '', ring: 'Early' })); });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalled();
  });

  it('sends one request when Resume rollout is pressed twice', async () => {
    const reply = deferred();
    mockFetch.mockReturnValue(reply.promise);
    setup();
    type('Go');
    fireEvent.click(resumeButton());
    fireEvent.click(resumeButton());
    expect(mockFetch).toHaveBeenCalledTimes(1);
    await act(async () => { reply.settle(jsonRes({ status: 'resumed', reason: '', ring: 'Early' })); });
  });

  it('the backdrop never closes it and Esc closes it only before a request is sent', () => {
    const { onClose } = setup();
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('Keep halted closes without sending anything', () => {
    const { onClose, onDone } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Keep halted' }));
    expect(onClose).toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('a failed request keeps the dialog open with the server message and the typed reason', async () => {
    const { onClose } = setup();
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Wait for the revert to finish.' }, 409));
    type('Because');
    fireEvent.click(resumeButton());
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't resume the rollout: Wait for the revert to finish. Try again.");
    expect(onClose).not.toHaveBeenCalled();
    expect((screen.getByLabelText('Reason for resuming') as HTMLTextAreaElement).value).toBe('Because');
    expect(resumeButton()).toBeEnabled();
  });

  it('a failure with no server message shows the connection fallback', async () => {
    setup();
    mockFetch.mockRejectedValue(new Error('network'));
    type('Because');
    fireEvent.click(resumeButton());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't resume the rollout. Check your connection and try again.");
  });

  it('a 403 closes it with the no-permission toast and reads the card again', async () => {
    const { onClose, onDone } = setup();
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Forbidden' }, 403));
    type('Because');
    fireEvent.click(resumeButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith("You don't have permission to resume rollouts.", 'error');
    expect(onDone).toHaveBeenCalled();
  });

  it('has no button labelled just Cancel', () => {
    setup();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    expect(screen.getAllByRole('button').map(b => b.textContent)).toEqual(['Keep halted', 'Resume rollout']);
  });

  it('wraps a long ring name and renders it as text', () => {
    const name = '<b>Ring</b> '.concat('x'.repeat(200));
    setup({ ringName: name });
    const body = screen.getByText(/Resuming runs the health check for/);
    expect(body.className).toContain('break-words');
    expect(body.textContent).toContain(name);
    expect(document.querySelector('b')).toBeNull();
  });
});

describe('CancelDialog', () => {
  const setup = (over: Partial<React.ComponentProps<typeof CancelDialog>> = {}) => {
    const onClose = vi.fn();
    const onDone = vi.fn();
    render(<CancelDialog rolloutId="R1" rolloutName="November security" revertRunning={false} tenantId={null} onClose={onClose} onDone={onDone} {...over} />);
    return { onClose, onDone };
  };
  const cancelButton = () => screen.getByRole('button', { name: /^(Cancel rollout|Cancelling\.\.\.)$/ });

  it('says what it ends and what stays, and that it cannot be started again', () => {
    setup();
    expect(screen.getByRole('dialog', { name: 'Cancel this rollout?' })).toBeInTheDocument();
    expect(screen.getByText(
      'This ends "November security". Computers that already have the patches keep them, and nothing further installs. A cancelled rollout can\'t be started again; start a new one instead.',
    )).toBeInTheDocument();
  });

  it('puts first focus on Keep rollout, which comes before the red Cancel rollout', async () => {
    setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Keep rollout' })).toHaveFocus());
    expect(screen.getAllByRole('button').map(b => b.textContent)).toEqual(['Keep rollout', 'Cancel rollout']);
    expect(cancelButton().className).toContain('bg-red-600');
  });

  it('adds the amber revert line only while a revert runs', () => {
    const { unmount } = render(
      <CancelDialog rolloutId="R1" rolloutName="X" revertRunning tenantId={null} onClose={vi.fn()} onDone={vi.fn()} />);
    expect(screen.getByText('A revert is still running. It finishes on its own.')).toBeInTheDocument();
    unmount();
    setup();
    expect(screen.queryByText('A revert is still running. It finishes on its own.')).toBeNull();
  });

  it('cancels, shows the toast with the name, closes and reads the card again', async () => {
    const { onClose, onDone } = setup({ tenantId: 'tenant_x' });
    mockFetch.mockResolvedValue(jsonRes({ status: 'cancelled', reason: '', ring: 'Early' }));
    fireEvent.click(cancelButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R1/cancel?tenantId=tenant_x');
    expect(toast).toHaveBeenCalledWith('Rollout "November security" cancelled.', 'success');
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('shows Cancelling... in flight and cannot be dismissed meanwhile', async () => {
    const reply = deferred();
    mockFetch.mockReturnValue(reply.promise);
    const { onClose } = setup();
    fireEvent.click(cancelButton());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Cancelling...' })).toBeDisabled());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(screen.getByRole('button', { name: 'Keep rollout' })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => { reply.settle(jsonRes({ status: 'cancelled', reason: '', ring: 'Early' })); });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('Keep rollout closes without sending anything, and so does Esc before a request', () => {
    const { onClose } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Keep rollout' }));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('a failed request keeps the dialog open with the server message', async () => {
    const { onClose, onDone } = setup();
    mockFetch.mockResolvedValue(jsonRes({ detail: 'This rollout is not halted.' }, 409));
    fireEvent.click(cancelButton());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't cancel the rollout: This rollout is not halted. Try again.");
    expect(onClose).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(cancelButton()).toBeEnabled();
  });

  it('a failure with no server message shows the connection fallback', async () => {
    setup();
    mockFetch.mockRejectedValue(new Error('network'));
    fireEvent.click(cancelButton());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't cancel the rollout. Check your connection and try again.");
  });

  it('a 403 closes it with a no-permission toast', async () => {
    const { onClose, onDone } = setup();
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Forbidden' }, 403));
    fireEvent.click(cancelButton());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith("You don't have permission to cancel rollouts.", 'error');
    expect(onDone).toHaveBeenCalled();
  });

  it('has no button labelled just Cancel', () => {
    setup();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
  });

  it('wraps a long rollout name in the body and renders it as text', () => {
    const name = '<i>Nov</i> '.concat('y'.repeat(200));
    setup({ rolloutName: name });
    const body = screen.getByText(/This ends/);
    expect(body.className).toContain('break-words');
    expect(body.textContent).toContain(name);
    expect(document.querySelector('i')).toBeNull();
  });
});

// ---------------------------------------------------------------- the halt block's actions on the card (Task 3)

const HALT = { ringName: 'Early', reason: 'a computer failed its health check.', reverts: [] as string[] };
const halted = (over: Partial<RolloutCardData> = {}) =>
  card({ id: 'R1', name: 'November security', status: 'halted', halt: HALT, ...over });
const WAIT = 'Wait for the revert to finish.';

describe('Halt block actions on the card', () => {
  const show = (c: RolloutCardData, onChanged = vi.fn(), tenantId: string | null = null) => {
    render(<RolloutCard card={c} onChanged={onChanged} tenantId={tenantId} />);
    return { onChanged };
  };
  const haltButtons = () => within(screen.getByRole('alert')).queryAllByRole('button').map(b => b.textContent);

  it('renders Resume rollout and Cancel rollout in the halt block only with the server flags', () => {
    const { unmount } = render(<RolloutCard card={halted()} onChanged={vi.fn()} />);
    expect(haltButtons()).toEqual([]);
    unmount();
    const resumeOnly = render(<RolloutCard card={halted({ canResume: true })} onChanged={vi.fn()} />);
    expect(haltButtons()).toEqual(['Resume rollout']);
    resumeOnly.unmount();
    const cancelOnly = render(<RolloutCard card={halted({ canCancel: true })} onChanged={vi.fn()} />);
    expect(haltButtons()).toEqual(['Cancel rollout']);
    cancelOnly.unmount();
    render(<RolloutCard card={halted({ canResume: true, canCancel: true })} onChanged={vi.fn()} />);
    expect(haltButtons()).toEqual(['Resume rollout', 'Cancel rollout']);
  });

  it('offers nothing else in the halt block: no skip-failed-computers control', () => {
    show(halted({ canResume: true, canCancel: true }));
    expect(screen.queryByRole('button', { name: /skip|exclude|ignore|remove/i })).toBeNull();
    expect(haltButtons()).toHaveLength(2);
  });

  it('renders no buttons on a card that is not halted, whatever the flags say', () => {
    render(<RolloutCard card={card({ status: 'running', canResume: true, canCancel: true })} onChanged={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Resume rollout' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel rollout' })).toBeNull();
  });

  it('both are secondary buttons at least 40px high', () => {
    show(halted({ canResume: true, canCancel: true }));
    for (const name of ['Resume rollout', 'Cancel rollout']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-10');
      expect(button.className).toContain('bg-white');
    }
  });

  it('while a revert runs Resume is disabled with the reason line that describes it, and Cancel stays enabled', () => {
    // 84-16: canResume is false while a computer is being reverted, and resumeBlockedReason carries the sentence.
    show(halted({ canResume: false, canCancel: true, revertRunning: true, resumeBlockedReason: WAIT }));
    const resume = screen.getByRole('button', { name: 'Resume rollout' });
    expect(resume).toBeDisabled();
    const described = document.getElementById(resume.getAttribute('aria-describedby') ?? 'none');
    expect(described).toHaveTextContent(WAIT);
    expect(screen.getByRole('button', { name: 'Cancel rollout' })).toBeEnabled();
    fireEvent.click(resume);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps Resume disabled while a revert runs even when the flag reads true', () => {
    show(halted({ canResume: true, canCancel: true, revertRunning: true, resumeBlockedReason: null }));
    const resume = screen.getByRole('button', { name: 'Resume rollout' });
    expect(resume).toBeDisabled();
    expect(document.getElementById(resume.getAttribute('aria-describedby') ?? 'none')).toHaveTextContent(WAIT);
  });

  it('does not show the revert reason line when no revert runs', () => {
    show(halted({ canResume: true, canCancel: true }));
    expect(screen.queryByText(WAIT)).toBeNull();
    expect(screen.getByRole('button', { name: 'Resume rollout' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Resume rollout' })).not.toHaveAttribute('aria-describedby');
  });

  it('Resume rollout opens the Resume dialog for the halted ring, and Keep halted closes it', () => {
    show(halted({ canResume: true, canCancel: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Resume rollout' }));
    const dialog = screen.getByRole('dialog', { name: 'Resume this rollout?' });
    expect(within(dialog).getByText(/health check for Early again/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep halted' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Cancel rollout opens the Cancel dialog with the rollout name, and the revert line when one runs', () => {
    show(halted({ canResume: false, canCancel: true, revertRunning: true, resumeBlockedReason: WAIT }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    const dialog = screen.getByRole('dialog', { name: 'Cancel this rollout?' });
    expect(within(dialog).getByText(/This ends "November security"/)).toBeInTheDocument();
    expect(within(dialog).getByText('A revert is still running. It finishes on its own.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep rollout' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('tells the parent to read the card again after Resume or Cancel succeeds, and sends the viewed organization', async () => {
    const { onChanged } = show(halted({ canResume: true, canCancel: true }), vi.fn(), 'tenant_x');
    mockFetch.mockResolvedValue(jsonRes({ status: 'resumed', reason: '', ring: 'Early' }));
    fireEvent.click(screen.getByRole('button', { name: 'Resume rollout' }));
    fireEvent.change(screen.getByLabelText('Reason for resuming'), { target: { value: 'Fixed' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Resume rollout' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R1/resume?tenantId=tenant_x');
    expect(screen.queryByRole('dialog')).toBeNull();

    mockFetch.mockResolvedValue(jsonRes({ status: 'cancelled', reason: '', ring: 'Early' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel rollout' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    expect(mockFetch.mock.calls[1][0]).toBe('/api/patch-rollouts/R1/cancel?tenantId=tenant_x');
  });

  it('does not read the card again when the dialog is only closed', () => {
    const { onChanged } = show(halted({ canResume: true, canCancel: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep rollout' }));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('a card with no onChanged and no actions has no buttons (the card alone is read-only)', () => {
    render(<RolloutCard card={halted({ canResume: true, canCancel: true })} />);
    expect(screen.queryByRole('button', { name: 'Resume rollout' })).toBeNull();
  });
});

describe('Halt block actions on the Rollouts tab', () => {
  const ctx = { currentUser: { role: 'Admin' }, hasPermission: () => true } as any;
  let pageFlags = flags();
  const serve = (c: RolloutCardData) => mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return Promise.resolve(jsonRes({ status: 'resumed', reason: '', ring: 'Early' }));
    return Promise.resolve(url.startsWith('/api/patch-rollouts') ? jsonRes(rolloutPage([c], { flags: pageFlags })) : jsonRes({}));
  });
  const reads = () => mockFetch.mock.calls.filter(call => (call[1] as RequestInit | undefined)?.method !== 'POST'
    && String(call[0]).startsWith('/api/patch-rollouts?'));
  const open = () => render(<UserContext.Provider value={ctx}><RolloutsTab /></UserContext.Provider>);
  beforeEach(() => { pageFlags = flags(); });

  it('shows Resume and Cancel on a halted card from the server flags', async () => {
    serve(halted({ canResume: true, canCancel: true }));
    open();
    expect(await screen.findByRole('button', { name: 'Resume rollout' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel rollout' })).toBeEnabled();
  });

  it('shows no Resume or Cancel to someone the server did not allow', async () => {
    serve(halted());
    open();
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: 'Resume rollout' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel rollout' })).toBeNull();
  });

  it('keeps Resume enabled while automatic actions are stopped', async () => {
    pageFlags = flags({ stopped: true, stopScope: 'tenant' });
    serve(halted({ canResume: true, canCancel: true }));
    open();
    expect(await screen.findByRole('button', { name: 'Resume rollout' })).toBeEnabled();
  });

  it('reads the list again after a Resume without a skeleton or a busy state', async () => {
    serve(halted({ canResume: true, canCancel: true }));
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Resume rollout' }));
    expect(reads()).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Reason for resuming'), { target: { value: 'Fixed the disk' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Resume rollout' }));
    await waitFor(() => expect(reads()).toHaveLength(2));
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(screen.getByRole('heading', { name: 'November security' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
