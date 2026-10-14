/**
 * Pending agents panel (spec C3).
 * protects=super admins see every waiting agent with its host details and can approve,
 * approve-and-raise-the-limit after a 409 no_free_seat, reject (after confirming) and bulk
 * approve; tenant users get the same list read-only; nothing renders while none wait;
 * fails_when=a tenant user is offered decisions, the raise-limit path is lost, or reject
 * fires without confirmation; no_claim=the backend (authFetch is mocked) and styling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { PendingAgentsPanel } from '../../components/PendingAgentsPanel';

const AGENT = {
  id: 'agent-9', tenantId: 'tenant-a', hostname: 'FIN-LT-042', status: 'Pending', pendingReason: 'seat_limit',
  pendingSince: '2026-10-14T08:00:00Z', lastSeen: '2026-10-14T08:05:00Z', ipAddress: '10.1.2.3',
  sourceIp: '203.0.113.7', version: '2.1.13', loggedInUser: 'CORP\\jdoe',
  hardware: { serialNumber: 'PF3ABC12', smbiosUuid: '4c4c4544-0042', macAddresses: ['3c:52:82:aa:bb:cc'], osFamily: 'windows' },
};
const list = (canDecide: boolean, agents: unknown[] = [AGENT]) => ({
  ok: true, status: 200,
  json: async () => ({ agents, canDecide,
    tenants: { 'tenant-a': { name: 'Acme', license: { maxAgents: 5, seatsUsed: 5, seatsAvailable: 0 } } } }),
});
const ok = (body: unknown = {}) => ({ ok: true, status: 200, json: async () => body });

describe('PendingAgentsPanel', () => {
  beforeEach(() => authFetch.mockReset());

  it('renders nothing while no agent is waiting', async () => {
    authFetch.mockResolvedValue(list(true, []));
    const { container } = render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending', { method: 'GET' }));
    expect(container.innerHTML).toBe('');
  });

  it('shows host details and offers to raise the limit when no seat is free', async () => {
    authFetch
      .mockResolvedValueOnce(list(true))
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({
        error: 'no_free_seat: the tenant has no free agent seat', license: { maxAgents: 5, seatsUsed: 5, seatsAvailable: 0 } }) })
      .mockResolvedValueOnce(ok({ status: 'Offline' }))
      .mockResolvedValueOnce(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    expect(screen.getByText('S/N PF3ABC12')).toBeTruthy();
    expect(screen.getByText('Acme')).toBeTruthy();
    expect(screen.getByText('License limit reached')).toBeTruthy();

    fireEvent.click(screen.getByText('Approve'));
    await waitFor(() => screen.getByText('Approve and raise limit by 1'));
    expect(screen.getByRole('alert').textContent).toContain('5/5 in use');
    fireEvent.click(screen.getByText('Approve and raise limit by 1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-9/approve',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ raiseLimitBy: 1 }) })));
  });

  it('rejects only after confirmation', async () => {
    authFetch.mockResolvedValueOnce(list(true)).mockResolvedValueOnce(ok()).mockResolvedValueOnce(list(true, []));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<PendingAgentsPanel tenantId="tenant-a" />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    fireEvent.click(screen.getByText('Reject'));
    expect(authFetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Reject'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-9/reject', { method: 'POST' }));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(authFetch.mock.calls[0][0]).toBe('/api/agents/pending?tenantId=tenant-a');
  });

  it('bulk-approves the selected agents, adding seats on request', async () => {
    authFetch.mockResolvedValueOnce(list(true)).mockResolvedValueOnce(ok({ succeeded: 1, failed: 0 }))
      .mockResolvedValueOnce(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    fireEvent.click(screen.getByLabelText('Select FIN-LT-042'));
    fireEvent.click(screen.getByText('Approve 1 and add seats'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/bulk', expect.objectContaining({
      body: JSON.stringify({ action: 'approve', agentIds: ['agent-9'], raiseLimit: true }) })));
  });

  it('is read-only for tenant users', async () => {
    authFetch.mockResolvedValue(list(false));
    render(<PendingAgentsPanel tenantId="tenant-a" />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
    expect(screen.queryByLabelText('Select FIN-LT-042')).toBeNull();
    expect(screen.getByText(/Contact your provider to add seats/)).toBeTruthy();
  });
});
