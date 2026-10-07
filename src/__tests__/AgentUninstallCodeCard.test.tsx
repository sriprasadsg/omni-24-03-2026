/**
 * Uninstall protection card:
 *  1. The code stays hidden until an administrator asks for it.
 *  2. "Show uninstall code" fetches GET /agents/{id}/uninstall-code and shows it.
 *  3. "Replace" asks first, then POSTs to /rotate and shows the new code.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { AgentUninstallCodeCard } from '../../components/AgentUninstallCodeCard';

const reply = (code: string, version: number) =>
  ({ ok: true, json: async () => ({ code, version, createdAt: '2026-10-07T00:00:00Z' }) });

describe('AgentUninstallCodeCard', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows the code only after it is requested', async () => {
    authFetch.mockResolvedValue(reply('ABCD-EFGH-JKMN', 1));
    render(<AgentUninstallCodeCard agentId="agent-1" />);
    expect(screen.queryByText('ABCD-EFGH-JKMN')).toBeNull();
    expect(authFetch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('Show uninstall code'));
    await waitFor(() => expect(screen.getByText('ABCD-EFGH-JKMN')).toBeTruthy());
    expect(authFetch).toHaveBeenCalledWith('/api/agents/agent-1/uninstall-code', { method: 'GET' });
  });

  it('replaces the code after confirmation', async () => {
    authFetch.mockResolvedValueOnce(reply('ABCD-EFGH-JKMN', 1)).mockResolvedValueOnce(reply('PQRS-TUVW-XYZ2', 2));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<AgentUninstallCodeCard agentId="agent-1" />);
    fireEvent.click(screen.getByText('Show uninstall code'));
    await waitFor(() => screen.getByText('ABCD-EFGH-JKMN'));

    fireEvent.click(screen.getByText('Replace'));
    await waitFor(() => expect(screen.getByText('PQRS-TUVW-XYZ2')).toBeTruthy());
    expect(authFetch).toHaveBeenLastCalledWith('/api/agents/agent-1/uninstall-code/rotate', { method: 'POST' });
  });
});
