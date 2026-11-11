/**
 * Moved agents list (88-14; LIC-06; D-37, D-38, D-43).
 * protects=platform deciders see agents retired because their computer moved (organization, host,
 * date, how) and can restore one only after confirmation; a refused or empty list renders nothing;
 * a failed restore is shown and reloads; the list refetches when the host panel's refreshKey moves.
 * fails_when=Restore fires without confirmation, a 403 or empty answer renders a block, a failed
 * restore is silent, or a refreshKey change leaves the list stale; no_claim=the backend (authFetch
 * is mocked) and styling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();
const showToast = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { PendingMovedAgents } from '../../components/PendingMovedAgents';

const ROW = { id: 'agent-o', tenantId: 'tenant-b', tenantName: 'Globex', hostname: 'FIN-LT-042',
  replacedReason: 'moved_silent', movedAt: '2026-10-14T12:00:00Z', lastSeen: '2026-10-14T11:00:00Z' };
const ROW2 = { ...ROW, id: 'agent-p', hostname: 'HR-LT-7', tenantName: 'Initech', replacedReason: 'moved' };
const moved = (agents: unknown[]) => ({ ok: true, status: 200, json: async () => ({ agents }) });
const fail = (status: number, error: string) => ({ ok: false, status, json: async () => ({ error }) });

describe('PendingMovedAgents', () => {
  beforeEach(() => { authFetch.mockReset(); showToast.mockReset(); });

  it('lists moved agents with organization, host, date and how they moved', async () => {
    authFetch.mockResolvedValue(moved([ROW, ROW2]));
    render(<PendingMovedAgents />);
    await waitFor(() => screen.getByText('Agents retired by a move (2)'));
    expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/moved', { method: 'GET' });
    expect(screen.getByText('FIN-LT-042 in Globex, moved Oct 14, 2026 (silent copy)')).toBeTruthy();
    expect(screen.getByText('HR-LT-7 in Initech, moved Oct 14, 2026 (approved move)')).toBeTruthy();
    expect(screen.getByText(/Restoring one brings it back as Inactive/)).toBeTruthy();
  });

  it('restores only after confirmation, removes the row and says so', async () => {
    authFetch.mockResolvedValueOnce(moved([ROW, ROW2])).mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: 'Inactive' }) });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<PendingMovedAgents />);
    await waitFor(() => screen.getByText('Agents retired by a move (2)'));
    fireEvent.click(screen.getByLabelText('Restore FIN-LT-042 in Globex'));
    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenLastCalledWith(
      'Restore FIN-LT-042 in Globex? It takes a seat again at its next check-in, unless the computer is live in another organization.');
    fireEvent.click(screen.getByLabelText('Restore FIN-LT-042 in Globex'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-o/restore', { method: 'POST' }));
    await waitFor(() => expect(screen.queryByLabelText('Restore FIN-LT-042 in Globex')).toBeNull());
    expect(screen.getByText('Agents retired by a move (1)')).toBeTruthy();
    expect(showToast).toHaveBeenCalledWith('FIN-LT-042 restored. It takes a seat again at its next check-in.', 'success');
  });

  it('shows a refused restore and reloads the list', async () => {
    authFetch.mockResolvedValueOnce(moved([ROW])).mockResolvedValueOnce(fail(409, 'not_moved: the agent is not a moved agent'))
      .mockResolvedValueOnce(moved([]));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { container } = render(<PendingMovedAgents />);
    await waitFor(() => screen.getByText('Agents retired by a move (1)'));
    fireEvent.click(screen.getByLabelText('Restore FIN-LT-042 in Globex'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Restore failed: not_moved: the agent is not a moved agent', 'error'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(container.innerHTML).toBe(''));
  });

  it('renders nothing when no agent moved, on a 403 and on a failed load', async () => {
    for (const answer of [moved([]), fail(403, 'forbidden'), fail(500, 'boom')]) {
      authFetch.mockReset();
      authFetch.mockResolvedValue(answer);
      const { container, unmount } = render(<PendingMovedAgents />);
      await waitFor(() => expect(authFetch).toHaveBeenCalled());
      await new Promise(r => setTimeout(r, 0));
      expect(container.innerHTML).toBe('');
      unmount();
    }
  });

  it('refetches when the host panel moves its refreshKey', async () => {
    authFetch.mockResolvedValueOnce(moved([])).mockResolvedValueOnce(moved([ROW]));
    const { rerender } = render(<PendingMovedAgents refreshKey={0} />);
    await waitFor(() => expect(authFetch).toHaveBeenCalledTimes(1));
    rerender(<PendingMovedAgents refreshKey={1} />);
    await waitFor(() => screen.getByText('Agents retired by a move (1)'));
  });

  it('falls back when the organization or host is missing and scrolls a long list', async () => {
    const many = Array.from({ length: 9 }, (_, i) => ({ ...ROW, id: `a${i}`, hostname: `H${i}` }));
    authFetch.mockResolvedValue(moved([{ ...ROW, tenantName: undefined, movedAt: undefined }, ...many]));
    const { container } = render(<PendingMovedAgents />);
    await waitFor(() => screen.getByText('Agents retired by a move (10)'));
    expect(screen.getByText('FIN-LT-042 in another organization, moved — (silent copy)')).toBeTruthy();
    expect(container.querySelector('ul')?.className).toContain('max-h-72');
  });
});
