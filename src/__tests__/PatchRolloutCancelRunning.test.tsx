/**
 * Phase 84 / PTCH-04, D-16 (gap plan 84-28): Cancel of a RUNNING rollout. The server decides who is offered Cancel
 * (canCancel) and what the dialog says (cancelNote: nothing is reverted); the browser adds no copy of its own.
 *
 * Value: protects=a running rollout can be cancelled from its card with the server's sentence in the dialog, a halted
 * one shows no note, and a "cancelling" answer closes the dialog and reads the card again; fails_when=no Cancel
 * rollout button on a running card with canCancel, a button without the flag, the note missing or shown for a halted
 * rollout, or a cancelling answer leaving the dialog open or the card unread; no_claim=the server rules
 * (backend/tests/test_patch_rollout_cancel_running.py).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { CancelDialog } from '../../components/patchRollouts/RolloutDialogs';
import { RolloutCard } from '../../components/patchRollouts/RolloutCard';
import { card, jsonRes } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;
const NOTE = 'Cancelling stops new installs now. Computers that already installed keep the patches; nothing is reverted. The rollout ends when the installs in progress finish.';

beforeEach(() => {
  mockFetch.mockReset();
  toast.mockReset();
});

describe('Cancel on a running rollout', () => {
  it('shows Cancel rollout on a running card only with the server flag', () => {
    const off = render(<RolloutCard card={card({ status: 'running', canCancel: false, cancelNote: NOTE })} onChanged={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Cancel rollout' })).toBeNull();
    off.unmount();
    render(<RolloutCard card={card({ status: 'running', canCancel: true, cancelNote: NOTE })} onChanged={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Cancel rollout' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume rollout' })).toBeNull();
  });

  it('renders the server note in the dialog and nothing extra when it is null', () => {
    render(<RolloutCard card={card({ status: 'running', canCancel: true, cancelNote: NOTE })} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    const dialog = screen.getByRole('dialog', { name: 'Cancel this rollout?' });
    expect(dialog).toHaveTextContent(NOTE);
  });

  it('a dialog with no note renders exactly as before', () => {
    render(<CancelDialog rolloutId="R1" rolloutName="November security" revertRunning={false} note={null} tenantId={null} onClose={vi.fn()} onDone={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Cancel this rollout?' });
    expect(dialog).not.toHaveTextContent('nothing is reverted');
    expect(dialog.querySelectorAll('p')).toHaveLength(1);
  });

  it('a cancelling answer closes the dialog, says the rollout ends when the installs finish and reads the card again', async () => {
    const onChanged = vi.fn();
    render(<RolloutCard card={card({ id: 'R1', status: 'running', canCancel: true, cancelNote: NOTE })} onChanged={onChanged} tenantId="tenant_x" />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    mockFetch.mockResolvedValue(jsonRes({ status: 'cancelling', reason: null, ring: 'Early' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Cancel this rollout?' })).getByRole('button', { name: 'Cancel rollout' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/R1/cancel?tenantId=tenant_x');
    expect(toast).toHaveBeenCalledWith('Cancelling "November security". It ends when the installs in progress finish.', 'success');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a halted card shows its Cancel in the halt block and the dialog has no running note', () => {
    render(<RolloutCard card={card({ status: 'halted', canCancel: true, cancelNote: null, halt: { ringName: 'Early', reason: 'a computer failed.', reverts: [] } })} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel rollout' }));
    expect(screen.getByRole('dialog', { name: 'Cancel this rollout?' })).not.toHaveTextContent('nothing is reverted');
  });
});
